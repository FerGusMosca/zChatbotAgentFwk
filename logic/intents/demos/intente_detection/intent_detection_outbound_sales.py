from __future__ import annotations
from typing import Dict, Optional, Tuple
import json, re

from langchain_core.prompts import ChatPromptTemplate

from common.util.loader.intent_prompt_loader import IntentPromptLoader
from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intents_execution.outbound_sales.outbound_sales_intent_logic import (
    OutboundSalesIntentLogic,
)


class IntentDetectionLogicOutboundSales(BaseInentDetect):
    """
    Detects and executes the 'outbound_sales_call' intent (WhatsApp).
    - 100% LLM-based (no regex)
    - Multi-turn slot filling when needed
    """

    INTENT_NAME = "outbound_sales_call"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__(logger)

        # Executor used for slot extraction and final action
        self.exec = OutboundSalesIntentLogic(
            logger, model_name=model_name, temperature=temperature
        )

        # Binary classifier prompt (loaded from input/intent_prompts/*.md)
        self._classifier: ChatPromptTemplate = IntentPromptLoader.get_prompt(
            "outbound_sales_intent_cmd_detect"
        )

        # In-flight state for multi-turn slot filling
        # {"slots": dict, "missing": dict, "last_reprompt": str}
        self._active: Optional[Dict] = None

    # ---------------------- HybridBot contract ---------------------- #

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Attempt to detect and start the intent.
        Returns: (handled, message, intent_name, stage)
        stage ∈ {"REPROMPT","EXECUTED"} when handled is True.
        """
        if not self._looks_like_outbound(user_text):
            return False, "", None, None

        extracted = self.exec.try_extract(user_text) or {}
        required = self.exec.required_slots()

        filled = {k: v for k, v in extracted.items() if v}
        missing = {k: hint for k, hint in required.items() if k not in filled}

        if missing:
            reprompt = self.exec.build_prompt_for_missing(missing)
            self._active = {"slots": filled, "missing": missing, "last_reprompt": reprompt}
            return True, reprompt, self.INTENT_NAME, "REPROMPT"

        msg = self._safe_execute(filled)
        self._active = None
        return True, msg, self.INTENT_NAME, "EXECUTED"

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """Continue slot filling for an in-flight intent."""
        if not self._active:
            return False, "", None, None

        prev = dict(self._active.get("slots") or {})
        newly = self.exec.try_extract(user_text) or {}
        merged = {**prev, **{k: v for k, v in newly.items() if v}}

        required = self.exec.required_slots()
        missing = {k: hint for k, hint in required.items() if k not in merged}

        if missing:
            reprompt = self.exec.build_prompt_for_missing(missing)
            self._active.update({"slots": merged, "missing": missing, "last_reprompt": reprompt})
            return True, reprompt, self.INTENT_NAME, "REPROMPT"

        msg = self._safe_execute(merged)
        self._active = None
        return True, msg, self.INTENT_NAME, "EXECUTED"

    # ------------------------------ Helpers ------------------------------ #

    def _looks_like_outbound(self, text: str) -> bool:
        """
        LLM-based yes/no classifier.
        - Calls the classifier prompt
        - Tolerates ```json fences and extra prose
        - Never indexes dicts directly (avoids KeyError)
        """
        raw = None  # keep for logging if an exception happens early
        try:
            msgs = self._classifier.format_messages(user_text=text)
            resp = self.exec.llm.invoke(msgs)
            raw = getattr(resp, "content", None)

            # Parse model output into a dict robustly
            if isinstance(raw, str):
                s = raw.strip()
                if s.startswith("```"):  # strip code fences
                    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
                m = re.search(r"\{.*\}", s, flags=re.DOTALL)  # grab the first JSON object
                if m:
                    s = m.group(0)
                data = json.loads(s)
            elif isinstance(raw, dict):
                data = raw
            else:
                data = getattr(resp, "additional_kwargs", {}) or {}

            # Accept several key names from the classifier
            for k in (
                "outbound_sales_call",  # canonical
                "outbound_call", "start_whatsapp_sales", "is_outbound", "should_call",
            ):
                v = data.get(k)
                if v is None:
                    continue
                if isinstance(v, str):
                    v = v.strip().lower() == "true"
                return bool(v)

            return False
        except Exception as ex:
            if self.logger:
                self.logger.error(f"[outbound_detection_llm_error] {ex!r} | raw={raw!r}")
            return False

    def _safe_execute(self, filled_slots: Dict[str, str]) -> str:
        """Run the executor and never break the bot."""
        try:
            return self.exec.execute(filled_slots)
        except Exception as ex:
            if self.logger:
                self.logger.exception("outbound_sales_execute_error", extra={"error": str(ex)})
            return (
                '{"answer":"❌ Ocurrió un error al iniciar la venta por WhatsApp.",'
                '"intent":"outbound_sales_call","specific_flag":"ERROR"}'
            )
