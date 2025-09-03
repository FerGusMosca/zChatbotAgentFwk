from __future__ import annotations
import json
import os
from dataclasses import dataclass
from typing import Dict, Optional

from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from twilio.rest import Client

from common.util.loader.intent_prompt_loader import IntentPromptLoader

# Optional: if your WhatsApp agent webhook is present, we store minimal context.
try:
    from logic.whatsapp.wa_sales_agent import set_sales_context  # type: ignore
except Exception:  # noop if missing
    def set_sales_context(*_args, **_kwargs):  # type: ignore
        pass


# --------------------------- Twilio configuration ---------------------------

@dataclass
class TwilioCfg:
    """Twilio / WhatsApp env config."""
    account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token:  str = os.getenv("TWILIO_AUTH_TOKEN", "")
    wa_from:     str = os.getenv("WHATSAPP_FROM", "whatsapp:+14155238886")
    # First version targets your own WhatsApp number (sandbox or approved sender)
    wa_to_default: str = os.getenv("WHATSAPP_TO", "whatsapp:+5491140781745")


# ------------------------------- Executor -----------------------------------

class OutboundSalesIntentLogic:
    """
    Execution logic for the OUTBOUND_SALES_CALL intent.

    Exposes:
      - self.llm                           -> shared LLM instance
      - required_slots() -> Dict[str,str]  -> mandatory slots
      - try_extract(text) -> Dict[str,str] -> extract slots with LLM
      - build_prompt_for_missing(missing)  -> user reprompt
      - execute(slots) -> JSON str         -> sends first WA message, returns bot JSON

    Notes:
      - No regex/heuristics; all slot extraction is LLM + prompt.
      - WhatsApp send is handled by Twilio API.
      - If you wired a WA webhook agent, we persist {product,target_name}
        via set_sales_context(to, ctx) so the agent can “keep talking”.
    """

    INTENT_NAME = "outbound_sales_call"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        self.logger = logger
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            response_format={"type": "json_object"},  # force JSON
        )
        self.tw = TwilioCfg()

        # One prompt used for classification + slot extraction
        self._slot_prompt: ChatPromptTemplate = IntentPromptLoader.get_prompt(
            "outbound_sales_intent_cmd_detect"  # file in input/intent_prompts
        )

    # ------------------------- Slots API (LLM-based) -------------------------

    def required_slots(self) -> Dict[str, str]:
        # product is mandatory; target_name optional
        return {"product": "¿Qué producto querés vender?"}

    def try_extract(self, text: str) -> Dict[str, str]:
        """
        Use the LLM+prompt to extract slots.
        Expected model JSON:
          {"outbound_sales_call": true/false, "target_name": "...", "product": "..."}
        """
        try:
            msgs = self._slot_prompt.format_messages(user_text=text)
            resp = self.llm.invoke(msgs)
            raw = getattr(resp, "content", None)

            if self.logger:
                self.logger.error(f"[outbound_extract] raw_type={type(raw).__name__} raw={raw!r}")

            data = json.loads(raw) if isinstance(raw, str) else (
                raw if isinstance(raw, dict) else {}
            )
            if not bool(data.get("outbound_sales_call")):
                return {}

            slots = {
                "target_name": (data.get("target_name") or None),
                "product": (data.get("product") or None),
            }
            # drop falsy values
            return {k: v for k, v in slots.items() if v}
        except Exception as ex:
            if self.logger:
                self.logger.error(f"[outbound_extract_error] {ex!r}")
            return {}

    def build_prompt_for_missing(self, missing: Dict[str, str]) -> str:
        """Short, natural reprompt for any missing slots."""
        hints = [q for q in missing.values()]
        return "Para iniciar la venta necesito un dato: " + "; ".join(hints)

    # ------------------------------ Execution --------------------------------

    def _twilio_client(self) -> Client:
        return Client(self.tw.account_sid, self.tw.auth_token)

    @staticmethod
    def _ensure_wa_prefix(num: str) -> str:
        """Guarantee 'whatsapp:' prefix and E.164-like shape (best-effort)."""
        num = (num or "").strip()
        if not num:
            return num
        return num if num.startswith("whatsapp:") else f"whatsapp:{num}"

    def _build_pitch(self, target_name: Optional[str], product: str) -> str:
        name = target_name or "¿cómo estás?"
        return (
            f"Hola {name} 👋\n"
            f"Te contacto por *{product}*. "
            f"¿Querés que te comparta 3 beneficios y el precio estimado?"
        )

    def execute(self, slots: Dict[str, str]) -> str:
        """Send the first WhatsApp message and persist minimal context for the webhook agent."""
        product = (slots.get("product") or "").strip()
        target_name = (slots.get("target_name") or "").strip() or None

        if not product:
            return json.dumps({
                "answer": "Falta el producto a vender.",
                "intent": self.INTENT_NAME,
                "specific_flag": "ERROR",
            }, ensure_ascii=False)

        to = self._ensure_wa_prefix(self.tw.wa_to_default)
        wa_from = self._ensure_wa_prefix(self.tw.wa_from)

        if not to:
            return json.dumps({
                "answer": "WHATSAPP_TO no está configurado.",
                "intent": self.INTENT_NAME,
                "specific_flag": "ERROR",
            }, ensure_ascii=False)

        if not wa_from:
            return json.dumps({
                "answer": "WHATSAPP_FROM no está configurado.",
                "intent": self.INTENT_NAME,
                "specific_flag": "ERROR",
            }, ensure_ascii=False)

        # Persist context for your WA agent (if present)
        try:
            set_sales_context(to, {"product": product, "target_name": target_name})
        except Exception as e:
            if self.logger:
                self.logger.error("set_sales_context_error", extra={"error": str(e)})

        body = self._build_pitch(target_name, product)

        try:
            client = self._twilio_client()
            msg = client.messages.create(from_=wa_from, to=to, body=body)
            return json.dumps({
                "answer": "OK, inicié la venta por WhatsApp y seguiré la conversación allí.",
                "intent": self.INTENT_NAME,
                "specific_flag": "EXECUTED",
                "sid": msg.sid,
            }, ensure_ascii=False)
        except Exception as e:
            if self.logger:
                self.logger.exception("twilio_send_error", extra={"error": str(e)})
            return json.dumps({
                "answer": "No pude enviar el WhatsApp (revisá credenciales/ventana de 24h).",
                "intent": self.INTENT_NAME,
                "specific_flag": "ERROR",
            }, ensure_ascii=False)


# ------------------------------ Quick manual test ---------------------------
if __name__ == "__main__":
    # Minimal smoke test without the bot, adjust env vars before running.
    execu = OutboundSalesIntentLogic(logger=None)
    print(execu.execute({"product": "seguro médico", "target_name": "Fernando"}))
