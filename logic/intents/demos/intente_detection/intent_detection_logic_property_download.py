from __future__ import annotations
from typing import Dict, Optional, Tuple
import json

from langchain_core.prompts import ChatPromptTemplate

from common.util.loader.intent_prompt_loader import IntentPromptLoader
from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intents_execution.download_property_portals_demo import DownloadPropertyPortalsIntentLogicDemo


class IntentDetectionLogicPropertyDownload(BaseInentDetect):
    """
    Intent manager with state for 'download_property_portals'.

    Responsibilities:
      - Detect if the user is requesting a property download intent.
      - Manage slot-filling with multiple turns (neighborhood, operation).
      - If slots are complete, execute the download and clear state.
      - Always use LLMs (no regex/heuristics).
    """

    INTENT_NAME = "download_property_portals"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__(logger)

        self.demo = DownloadPropertyPortalsIntentLogicDemo(
            logger, model_name=model_name, temperature=temperature
        )
        # Active state of the ongoing intent, if any
        # {"slots": dict, "missing": dict, "last_reprompt": str}
        self._active: Optional[Dict] = None

        self._propdl_classifier: ChatPromptTemplate = IntentPromptLoader.get_prompt(
            "property_download_intent_cmd_detect"  # archivo .md en input/intent_prompts
        )

    # ---------------------- API expected by HybridBot -----------------------

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Try to DETECT and START the intent:
          - If not related to property download -> (False, "", None, None)
          - If some slots are missing -> save state and return a reprompt
          - If all slots are complete -> execute and clear state
        """
        if not self._looks_like_property_download(user_text):
            return False, "", None, None

        extracted = self.demo.try_extract(user_text)
        required = self.demo.required_slots()

        filled = {k: v for k, v in (extracted or {}).items() if v}
        missing = {k: hint for k, hint in required.items() if k not in filled}

        if missing:
            reprompt = self.demo.build_prompt_for_missing(missing, user_text=user_text)
            self._active = {"slots": filled, "missing": missing, "last_reprompt": reprompt}
            return True, reprompt, self.INTENT_NAME, "REPROMPT"

        # Complete -> execute
        msg = self._safe_execute(filled)
        self._active = None
        return True, msg, self.INTENT_NAME, "EXECUTED"

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Continue the intent if there is an active session:
          - Merge previously filled slots with new ones
          - If still missing -> reprompt
          - If complete -> execute and clear state
        """
        if not self._active:
            return False, "", None, None

        prev_slots = dict(self._active.get("slots") or {})
        newly = self.demo.try_extract(user_text) or {}
        merged = {**prev_slots, **{k: v for k, v in newly.items() if v}}

        required = self.demo.required_slots()
        missing = {k: hint for k, hint in required.items() if k not in merged}

        if missing:
            reprompt = self.demo.build_prompt_for_missing(missing, user_text=user_text)
            self._active.update({"slots": merged, "missing": missing, "last_reprompt": reprompt})
            return True, reprompt, self.INTENT_NAME, "REPROMPT"

        # Complete -> execute
        msg = self._safe_execute(merged)
        self._active = None
        return True, msg, self.INTENT_NAME, "EXECUTED"

    # ------------------------------ Helpers ---------------------------------

    def _looks_like_property_download(self, text: str) -> bool:
        """
        Strict binary classification via LLM
        True si el usuario pide descargar listados inmobiliarios (CABA).
        """
        try:
            msgs = self._propdl_classifier.format_messages(user_text=text)
            resp = self.demo.llm.invoke(msgs)

            raw = getattr(resp, "content", None)
            if self.logger:
                self.logger.error(f"[propdl_classify] raw_type={type(raw).__name__} raw={raw!r}")

            if isinstance(raw, str):
                data = json.loads(raw)
            elif isinstance(raw, dict):
                data = raw
            else:
                data = getattr(resp, "additional_kwargs", {}) or {}
                if self.logger:
                    self.logger.error(f"[propdl_classify] using additional_kwargs={data!r}")

            # tolerancia a alias de clave
            for k in ("property_download", "download", "should_download", "is_download_intent"):
                if k in data:
                    v = data[k]
                    if isinstance(v, str):
                        v = v.strip().lower() == "true"
                    return bool(v)

            return False
        except Exception as ex:
            if self.logger:
                self.logger.error(f"[intent_detection_llm_error] {ex!r}")
            return False

    def _safe_execute(self, filled_slots: Dict[str, str]) -> str:
        """
        Safely execute the download using the demo class.
        Returns a user-friendly message without breaking the bot flow.
        """
        try:
            return self.demo.execute(filled_slots)
        except Exception as ex:
            self.logger.exception("property_download_execute_error", extra={"error": str(ex)})
            return "❌ An error occurred while executing the download. Please try again later."
