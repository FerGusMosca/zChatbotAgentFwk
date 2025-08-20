from typing import Dict, Optional
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
from logic.intents.base_intent_logic_demo import BaseIntentLogicDemo
import json


class MoneyTransferIntentLogicDemo(BaseIntentLogicDemo):
    """
    Demo intent: 'send_transfer'.
    - Required slots: amount, recipient.
    - GPT handles slot extraction and the follow-up question in the user's language.
    - No regex/keywords: only structured prompts + JSON mode.
    """
    name = "send_transfer"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__(logger)
        # Force JSON to reduce parsing errors
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        # Slot extraction prompt (braces escaped). Keeps short few-shots; model returns ONLY JSON.
        self.extract_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a data extractor. Return ONLY valid JSON (no extra text). "
             "Do not hallucinate: if a field is not explicitly present, omit it."),
            # Few-shot: vague amount → omit
            ("user",
             "User message:\nQuiero transferirle unos mangos a Maria\n\n"
             "Extract fields if present:\n- amount\n- recipient\n\n"
             "JSON shape:\n{{\"slots\": {{\"amount\": <optional string>, \"recipient\": <optional string>}}}}"),
            ("assistant", "{{\"slots\": {{\"recipient\": \"Maria\"}}}}"),
            # Few-shot: concrete amount → include
            ("user",
             "User message:\nPasale USD 250 a @maria\n\n"
             "Extract fields if present:\n- amount\n- recipient\n\n"
             "JSON shape:\n{{\"slots\": {{\"amount\": <optional string>, \"recipient\": <optional string>}}}}"),
            ("assistant", "{{\"slots\": {{\"amount\": \"USD 250\", \"recipient\": \"@maria\"}}}}"),
            # Actual input
            ("user",
             "User message:\n{user_text}\n\n"
             "Extract the following fields if present:\n"
             "- amount: e.g., '1000', '10,000 ARS', 'USD 250'.\n"
             "- recipient: name or handle, e.g., 'John', '@maria'.\n\n"
             "Respond EXACT JSON with:\n"
             "{{\"slots\": {{\"amount\": <optional string>, \"recipient\": <optional string>}}}}"),
        ])

        # Reprompt builder: ask in the user's language; return ONLY {"reprompt": "..."}.
        self.reprompt_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a dialogue assistant. Return ONLY valid JSON. "
             "Write a SHORT, friendly follow-up question in the SAME language as the user's message "
             "to collect the missing fields. Keep it concise (1–3 lines)."),
            ("user",
             "User message:\n{user_text}\n\n"
             "Missing fields (keys): {missing_keys}\n"
             "Human hints:\n{hints}\n\n"
             "Return EXACT JSON:\n{{\"reprompt\": <string>}}")
        ])

    # ---- Base contract ----

    def required_slots(self) -> Dict[str, str]:
        # Human-friendly hints are used to craft the reprompt message.
        return {
            "amount": "monto / cantidad (con o sin moneda, ej. 10.000 ARS o USD 100)",
            "recipient": "destinatario (nombre o alias, ej. Juan, @maria)",
        }

    def try_extract(self, user_text: str) -> Dict[str, str]:
        """Ask GPT to extract any slots present (possibly partial)."""
        try:
            messages = self.extract_prompt.format_messages(user_text=user_text)
            resp = self.llm.invoke(messages)
            raw = (resp.content or "").strip()
            data = json.loads(raw)  # JSON mode should guarantee valid JSON
            slots = data.get("slots", {}) or {}
            out: Dict[str, str] = {}
            if isinstance(slots.get("amount"), str) and slots["amount"].strip():
                out["amount"] = slots["amount"].strip()
            if isinstance(slots.get("recipient"), str) and slots["recipient"].strip():
                out["recipient"] = slots["recipient"].strip()
            return out
        except Exception as ex:
            self.logger.exception("slot_extraction_error", extra={"error": str(ex)})
            return {}

    def build_prompt_for_missing(self, missing: Dict[str, str], user_text: Optional[str] = None) -> str:
        """
        Build the follow-up question USING GPT so it's in the same language as the user.
        """
        try:
            missing_keys = ", ".join(missing.keys())
            hints = "\n".join(f"- {k}: {v}" for k, v in missing.items())
            messages = self.reprompt_prompt.format_messages(
                user_text=user_text or "",
                missing_keys=missing_keys,
                hints=hints,
            )
            resp = self.llm.invoke(messages)
            raw = (resp.content or "").strip()
            data = json.loads(raw)
            reprompt = (data.get("reprompt") or "").strip()
            if not reprompt:
                # Minimal, safe fallback
                return "Necesito un dato más para continuar. ¿Podés indicarme el monto y/o destinatario?"
            return reprompt
        except Exception as ex:
            self.logger.exception("reprompt_build_error", extra={"error": str(ex)})
            return "Necesito un dato más para continuar. ¿Podés indicarme el monto y/o destinatario?"

    def execute(self, filled_slots: Dict[str, str]) -> str:
        """Simulate the transfer (demo) and return a confirmation."""
        self.logger.info("demo_money_transfer_execute", extra=filled_slots)
        return f"✅ Transferencia enviada: {filled_slots['amount']} a {filled_slots['recipient']}. (Demo)"
