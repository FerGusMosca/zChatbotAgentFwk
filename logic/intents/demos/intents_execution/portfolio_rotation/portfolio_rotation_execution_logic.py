# logic/portfolio/portfolio_rotation_execution_logic.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Optional

from langchain_community.chat_models import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from twilio.rest import Client

from common.util.formatter.whatsapp_utils import WhatsAppUtils
from common.util.settings.env_deploy_reader import EnvDeployReader
from common.util.loader.intent_prompt_loader import IntentPromptLoader
from logic.intents.demos.intents_execution.hooks.generic_wa_hook import set_conversation_context


class PortfolioRotationExecutionLogic:
    """
    Execution logic for sending portfolio rotation recommendations.
    Reads recommendations from file and builds a WhatsApp message with style from a prompt.
    """

    INTENT_NAME = "portfolio_rotation"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.2):
        self.logger = logger
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)

        # Twilio configuration from env
        self.tw_sid = EnvDeployReader.get("TWILIO_ACCOUNT_SID")
        self.tw_token = EnvDeployReader.get("TWILIO_AUTH_TOKEN")
        self.wa_from = EnvDeployReader.get("TWILIO_WHATSAPP_FROM")

        # Prompt for formatting portfolio messages
        self._msg_prompt: ChatPromptTemplate = IntentPromptLoader.get_prompt(
            EnvDeployReader.get("CONVERSATION_PROMPT")
        )

    def _twilio_client(self) -> Client:
        return Client(self.tw_sid, self.tw_token)

    def _ensure_wa_prefix(self, num: str) -> str:
        """Guarantee Twilio-ready WhatsApp number with 'whatsapp:' prefix."""
        clean_num = self._format_phone_with_llm(num)
        return clean_num if clean_num.startswith("whatsapp:") else f"whatsapp:{clean_num}"

    def _format_phone_with_llm(self, num: str) -> str:
        """Format arbitrary phone strings to E.164 (Argentina, +54)."""
        msgs = [
            {"role": "system",
             "content": "You are a formatter of phone numbers. Convert any phone string to valid E.164 format for Argentina (country code +54). Only return the number without spaces or symbols."},
            {"role": "user", "content": num}
        ]
        resp = self.llm.invoke(msgs)
        clean_num = getattr(resp, "content", "").strip()
        # fallback sanitize: remove spaces, parentheses, dashes
        clean_num = clean_num.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
        return f"whatsapp:{clean_num}"

    def execute(self, contact: Dict[str, str], rec_text: str, user_message: str = "") -> str:
        """
        Build and send portfolio rotation message to a given contact.
        contact: {"name": ..., "phone": ...}
        rec_text: weekly recommendation text
        user_message: last message received from the client (optional)
        """
        try:
            # --- Build message with LLM ---
            # Prepare prompt messages with injected variables (contact name + recommendation + user input)
            msgs = self._msg_prompt.format_messages(
                contact_name=contact["name"],
                recommendation=rec_text.strip(),
                user_message=user_message.strip()
            )
            resp = self.llm.invoke(msgs)
            body = getattr(resp, "content", "").strip()
            to=self._ensure_wa_prefix(contact["phone"])

            # 🔹 Save context for WhatsApp hook (so conversation can continue there)
            set_conversation_context(
                WhatsAppUtils.extract_number(to),
                {
                    "initial_prompt": [m.content for m in msgs],  # store full prompt texts
                }
            )

            # Debug log to verify what the LLM produced
            self.logger.info(f"[portfolio_rotation_llm_body] generated={body[:120]}")

            # --- Send via Twilio ---
            client = self._twilio_client()
            self.logger.info(f"[twilio_send_debug] to={to}, from={self.wa_from}, body={body[:50]}")
            msg = client.messages.create(from_=self.wa_from, to=to, body=body)

            return json.dumps({
                "answer": f"✅ Portfolio rotation sent to {contact['name']} ({contact['phone']})",
                "intent": self.INTENT_NAME,
                "sid": msg.sid,
            }, ensure_ascii=False)

        except Exception as ex:
            if self.logger:
                self.logger.exception("portfolio_rotation_send_error", extra={"error": str(ex)})
            return json.dumps({
                "answer": f"❌ Error sending portfolio rotation to {contact.get('name')}",
                "intent": self.INTENT_NAME
            }, ensure_ascii=False)

