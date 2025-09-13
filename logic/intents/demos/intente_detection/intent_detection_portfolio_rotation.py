from __future__ import annotations
from typing import Dict, Optional, Tuple
import json, re

from langchain_core.prompts import ChatPromptTemplate
from common.util.loader.intent_prompt_loader import IntentPromptLoader
from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intents_execution.portfolio_rotation.portfolio_rotation_intent_logic import \
    PortfolioRotationIntentLogic


class IntentDetectionLogicPortfolioRotation(BaseInentDetect):
    """
    Detects and executes the 'portfolio_rotation' intent.
    - Triggered by messages like: "mandame los mensajes de rotacion de portfolio"
    """

    INTENT_NAME = "portfolio_rotation"

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__(logger)

        self.exec = PortfolioRotationIntentLogic(
            logger, model_name=model_name, temperature=temperature
        )

        self._classifier: ChatPromptTemplate = IntentPromptLoader.get_prompt(
            "portfolio_rotation_intent_cmd_detect"
        )

        self._active: Optional[Dict] = None

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        if not self._looks_like_trigger(user_text):
            return False, "", None, None

        msg = self._safe_execute({})
        return True, msg, self.INTENT_NAME, "EXECUTED"

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        return False, "", None, None

    def _looks_like_trigger(self, text: str) -> bool:
        """
        Return True if the text mentions both 'portfolio' and 'rotacion' (case-insensitive).
        """
        text = text.lower()
        return bool(re.search(r"\bportfolio\b", text) and re.search(r"\brotacion\b", text))

    def _safe_execute(self, slots: Dict[str, str]) -> str:
        try:
            return self.exec.execute(slots)
        except Exception as ex:
            self.logger.exception("portfolio_rotation_execute_error", extra={"error": str(ex)})
            return '{"answer":"❌ Error ejecutando portfolio rotation","intent":"portfolio_rotation"}'
