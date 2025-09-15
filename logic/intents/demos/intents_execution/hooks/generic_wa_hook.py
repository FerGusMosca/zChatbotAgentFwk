# logic/whatsapp/generic_wa_hook.py
from __future__ import annotations

import json
import os
from urllib.parse import parse_qs
from typing import Dict, Any, List

from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse

# Use the variant you already adopted (langchain_openai if migrated)
from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from common.util.app_logger import AppLogger
from common.util.formatter.whatsapp_utils import WhatsAppUtils
from common.util.loader.intent_prompt_loader import IntentPromptLoader
from common.util.settings.env_deploy_reader import EnvDeployReader

# ---------------------------------------------------------------------------
# Module-level logger (do NOT override __name__)
# ---------------------------------------------------------------------------
LOG = AppLogger.get_logger("wa.generic")

# In-memory per-process state (enough for demo purposes)
_STATE: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Context bridge (called by the intent executor before first WA message)
# ---------------------------------------------------------------------------
def set_conversation_context(user_wa: str, ctx: Dict[str, Any]) -> None:
    """
    Persist minimal context for the WhatsApp thread:
    - Stores/updates keys under _STATE[user_wa]
    - ctx puede contener: initial_prompt, history, product, etc.
    """
    user_wa = (user_wa or "").strip()
    if not user_wa:
        return

    bucket = _STATE.get(user_wa) or {}
    bucket.setdefault("history", [])  # ensure history exists

    for k, v in (ctx or {}).items():
        if v is not None:
            bucket[k] = v

    _STATE[user_wa] = bucket

    # 🔎 Detailed log of what we saved
    LOG.info(
        "wa.ctx.set",
        extra={
            "user_tail": user_wa[-6:],   # última parte del WA
            "keys_saved": list((ctx or {}).keys()),  # claves nuevas
            "bucket_size": len(bucket),  # total keys en bucket
        },
    )

def get_conversation_context(user_wa: str) -> dict:
    """
    Retrieve full context for a given WhatsApp user.
    Returns {} if nothing stored.
    """
    user_wa = (user_wa or "").strip()
    if not user_wa:
        return {}
    return _STATE.get(user_wa, {})


# ---------------------------------------------------------------------------
# Load SYSTEM prompt from .md (strict; fail fast if missing)
# ---------------------------------------------------------------------------
def _load_system_md(name: str) -> str:
    try:
        md = IntentPromptLoader.get_text(name)
        LOG.info("wa.prompt_loaded", extra={"prompt_name": name})
        return md
    except Exception as e:
        LOG.error("wa.prompt_missing", extra={"prompt_name": name, "error": str(e)})
        raise

system_md = _load_system_md(EnvDeployReader.get("CONVERSATION_PROMPT"))

GENERIC_WA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", system_md),            # can use placeholders like {product}, {target_name}
        MessagesPlaceholder("history"),   # injected minimal chat history
        ("human", "{user_text}"),         # user's latest message
    ]
)

# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------
router = APIRouter()

def _llm() -> ChatOpenAI:
    """Factory for the LLM client (no shared state)."""
    return ChatOpenAI(
        model_name=os.getenv("OPENAI_MODEL_NAME", "gpt-4o"),
        temperature=0.3,
    )

def _coerce_str(d: Dict[str, Any], key: str) -> str:
    """Return a single string value from dict/list/None, trimmed."""
    v = d.get(key, "")
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return (v or "").strip()

@router.post("/wa/webhook")
async def wa_webhook(request: Request) -> Response:
    """
    WhatsApp webhook handler:
    - Parses incoming request from Twilio
    - Keeps context per WA thread
    - Calls the LLM with system prompt + history + user message
    - Replies with TwiML (so Twilio stops retries)
    """
    try:
        raw = await request.body()
        ctype = request.headers.get("content-type", "")
        sig   = request.headers.get("X-Twilio-Signature", None)

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
    ctx = get_conversation_context(WhatsAppUtils.extract_number(from_wa))
    history: List[Dict[str, str]] = ctx.setdefault("history", [])

    # -------- Build minimal history for the agent --------
    history_msgs: List[Any] = []

    initial_prompts = ctx.get("initial_prompt")
    if initial_prompts and not history:
        for p in initial_prompts:
            history_msgs.append(("system", p))

    for turn in history[-10:]:  # solo las últimas N interacciones
        role = turn.get("role")
        content = turn.get("content", "")
        if role == "user":
            history_msgs.append(("human", content))
        elif role == "assistant":
            history_msgs.append(("assistant", content))

    # -------- Call the LLM --------
    try:
        LOG.info("wa.llm.start", extra={"hist_used": len(history_msgs)})
        prompt = GENERIC_WA_PROMPT.partial(
            product=ctx.get("product"),
            target_name=ctx.get("target_name"),
            contact_name=ctx.get("contact_name"),
            recommendation=ctx.get("recommendation"),
        )
        msgs = prompt.format_messages(history=history_msgs, user_text=body)
        reply = (_llm().invoke(msgs).content or "").strip()
        LOG.info("wa.llm.done", extra={"reply_len": len(reply)})
    except Exception as ex:
        LOG.error("wa.llm.error", extra={"err": str(ex)}, exc_info=True)
        reply = "Lo siento, hubo un problema técnico al procesar tu mensaje."

    # -------- Persist memory & reply TwiML --------
    if body:
        history.append({"role": "user", "content": body})
    history.append({"role": "assistant", "content": reply})
    set_conversation_context(WhatsAppUtils.extract_number(from_wa), ctx)

    twiml = MessagingResponse()
    twiml.message(reply)

    return Response(content=str(twiml), media_type="application/xml")

# ---------------------------------------------------------------------------
# Installation helper (call once at startup; hardcoded path for now)
# ---------------------------------------------------------------------------
def install_generic_wa_hook(app) -> None:
    """
    Idempotently mounts the WA hook router on the given FastAPI app.
    Exposes POST /wa/webhook (path is declared on the router).
    """
    if getattr(app.state, "_wa_agent_installed", False):
        return
    app.include_router(router)  # POST /wa/webhook
    app.state._wa_agent_installed = True
    LOG.info("wa.install", extra={"path": "/wa/webhook"})
