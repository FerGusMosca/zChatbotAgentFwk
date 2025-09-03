# logic/whatsapp/wa_sales_agent.py
from __future__ import annotations

import json
import os
from urllib.parse import parse_qs
from typing import Dict, Any, List

from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse

# Usa la variante que venís usando. Si ya migraste a langchain_openai, cambiá el import.
from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from common.util.app_logger import AppLogger
from common.util.loader.intent_prompt_loader import IntentPromptLoader

# ---------------------------------------------------------------------------
# Module-level logger (do NOT override __name__)
# ---------------------------------------------------------------------------
LOG = AppLogger.get_logger("wa.sales_agent")

# In-memory per-process state (good enough for demo)
_STATE: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Context bridge (called by the intent executor before first WA message)
# ---------------------------------------------------------------------------
def set_sales_context(user_wa: str, ctx: Dict[str, Any]) -> None:
    """
    Persist minimal context for the WhatsApp thread:
    - product
    - target_name (optional)
    - an empty history list if absent
    """
    user_wa = (user_wa or "").strip()
    if not user_wa:
        return

    bucket = _STATE.get(user_wa) or {}
    bucket.setdefault("history", [])  # list of {"role": "...", "content": "..."}
    for k, v in (ctx or {}).items():
        if v is not None:
            bucket[k] = v
    _STATE[user_wa] = bucket

    LOG.info("wa.ctx.set", extra={"user_tail": user_wa[-6:], "keys": list((ctx or {}).keys())})

# ---------------------------------------------------------------------------
# Load SYSTEM prompt from .md (strict; fail fast if missing)
# ---------------------------------------------------------------------------
def _load_system_md(name: str) -> str:
    try:
        md = IntentPromptLoader.get_text(name)
        LOG.info("wa.prompt_loaded", extra={"prompt_name": name})   # <— antes: {"name": name}
        return md
    except Exception as e:
        LOG.error("wa.prompt_missing", extra={"prompt_name": name, "error": str(e)})  # <— antes: {"name": name, ...}
        raise


system_md = _load_system_md("wa_sales_agent_system")

SALES_AGENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", system_md),            # uses {product} and {target_name}
        MessagesPlaceholder("history"),   # injected minimal chat history
        ("human", "{user_text}"),         # user's latest message
    ]
)

# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------
router = APIRouter()

def _llm() -> ChatOpenAI:
    """One-liner LLM factory; no shared state kept here."""
    return ChatOpenAI(
        model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"),
        temperature=0.3,
    )

def _coerce_str(d: Dict[str, Any], key: str) -> str:
    """Return a single string value from dict/list/None, trimmed (no regex)."""
    v = d.get(key, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return (v or "").strip()

@router.post("/wa/webhook")
async def wa_webhook(request: Request) -> Response:
    """
    Twilio WA webhook handler (defensive):
    - Accepts x-www-form-urlencoded (default Twilio) or JSON.
    - Never raises uncaught exceptions: always returns TwiML to stop retries.
    - Minimal, LLM-driven sales agent with tiny per-thread memory.
    """
    # Lightweight latency marker
    t0 = getattr(os.times(), "elapsed", None)

    # -------- Parse request safely (no python-multipart required) --------
    try:
        ctype = request.headers.get("content-type", "")
        sig   = request.headers.get("X-Twilio-Signature", None)
        raw   = await request.body()  # bytes

        LOG.info("wa.recv", extra={"ctype": ctype, "clen": len(raw), "tw_sig": bool(sig)})

        if "application/x-www-form-urlencoded" in ctype or not raw.strip().startswith(b"{"):
            q = parse_qs(raw.decode("utf-8", errors="ignore"), keep_blank_values=True)
            data: Dict[str, Any] = {k: (v[0] if isinstance(v, list) else v) for k, v in q.items()}
        else:
            data = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception as ex:
        LOG.error("wa.parse_error", extra={"err": str(ex)})
        data = {}

    from_wa = _coerce_str(data, "From")   # user's WA number
    to_wa   = _coerce_str(data, "To")     # your sandbox/sender
    body    = _coerce_str(data, "Body")   # message text

    LOG.info(
        "wa.parsed",
        extra={"from_tail": from_wa[-6:], "to_tail": to_wa[-6:], "body_len": len(body or "")},
    )

    # -------- Load / init conversation context --------
    ctx = _STATE.get(from_wa) or _STATE.get(to_wa) or {
        "history": [],
        "product": "producto",
        "target_name": None,
        "closed": False,
    }
    history: List[Dict[str, str]] = ctx.setdefault("history", [])

    LOG.info(
        "wa.ctx",
        extra={
            "product": ctx.get("product"),
            "target": ctx.get("target_name"),
            "closed": bool(ctx.get("closed")),
            "history_len": len(history),
        },
    )

    # -------- Stop words / close thread --------
    lower = (body or "").lower()
    if any(x in lower for x in ("detener venta", "stop", "baja", "no quiero")):
        msg = "Entendido, detengo la conversación. ¡Gracias por tu tiempo!"
        twiml = MessagingResponse()
        twiml.message(msg)
        ctx["closed"] = True
        _STATE[from_wa or to_wa or ""] = ctx
        LOG.info("wa.stop", extra={"reply": msg})
        return Response(content=str(twiml), media_type="application/xml")

    if ctx.get("closed"):
        twiml = MessagingResponse()
        msg = "Ya detuvimos la conversación. Si querés retomar, escribí 'quiero info'."
        twiml.message(msg)
        LOG.info("wa.closed_reply", extra={"reply": msg})
        return Response(content=str(twiml), media_type="application/xml")

    # -------- Build minimal history for the agent --------
    history_msgs: List[Any] = []
    for turn in history[-10:]:  # last N turns only
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "user":
            history_msgs.append(("human", content))
        elif role == "assistant":
            history_msgs.append(("assistant", content))

    # -------- Call the LLM (guarded) --------
    try:
        LOG.info("wa.llm.start", extra={"hist_used": len(history_msgs)})
        prompt = SALES_AGENT_PROMPT.partial(
            product=ctx.get("product"),
            target_name=ctx.get("target_name"),
        )
        msgs  = prompt.format_messages(history=history_msgs, user_text=body)
        reply = (_llm().invoke(msgs).content or "").strip()
        if not reply:
            reply = "Gracias. ¿Te comparto 3 beneficios y un precio estimado?"
        LOG.info("wa.llm.done", extra={"reply_len": len(reply)})
    except Exception as ex:
        LOG.error("wa.llm.error", extra={"err": str(ex)})
        reply = "Estoy con problemas técnicos. ¿Querés que te escriba más tarde?"

    # -------- Persist memory & reply TwiML --------
    if body:
        history.append({"role": "user", "content": body})
    history.append({"role": "assistant", "content": reply})
    _STATE[from_wa or to_wa or ""] = ctx

    twiml = MessagingResponse()
    twiml.message(reply)

    # Best-effort latency metric
    try:
        t1 = getattr(os.times(), "elapsed", None)
        if t0 is not None and t1 is not None:
            LOG.info("wa.reply", extra={"latency_s": round(t1 - t0, 3), "reply_len": len(reply)})
    except Exception:
        pass

    return Response(content=str(twiml), media_type="application/xml")

# ---------------------------------------------------------------------------
# Installation helper (call once at startup; hardcoded path for now)
# ---------------------------------------------------------------------------
def install_wa_sales_agent(app) -> None:
    """
    Idempotently mounts the WA sales agent router on the given FastAPI app.
    Exposes POST /wa/webhook (path is declared on the router).
    """
    if getattr(app.state, "_wa_agent_installed", False):
        return
    app.include_router(router)  # POST /wa/webhook
    app.state._wa_agent_installed = True
    LOG.info("wa.install", extra={"path": "/wa/webhook"})
