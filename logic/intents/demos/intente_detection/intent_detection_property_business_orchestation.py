from __future__ import annotations
from typing import Optional, Tuple, List

from langchain_community.chat_models import ChatOpenAI

from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intente_detection.intent_detection_logic_command_execution import (
    IntentDetectionLogicCommandExecution,
)
from logic.intents.demos.intente_detection.intent_detection_logic_property_download import (
    IntentDetectionLogicPropertyDownload,
)


class IntentDetectionPropertyBusinessOrchestationLogic(BaseInentDetect):
    """
    Orchestrator for property-business intents.

    Responsibilities:
      - Hold and iterate over multiple intent detectors in a fixed priority order.
      - Forward the user's message to each detector until one handles it.
      - Keep track of the detector that issued a REPROMPT to support resume().
      - Keep a single LLM config for detectors that require it.

    Child detectors (in order):
      1) IntentDetectionLogicCommandExecution  -> queries/commands over exported TXT files
      2) IntentDetectionLogicPropertyDownload  -> raw sales dump from Zonaprop

    Notes:
      - 100% LLM-based detection inside each detector (no regex/heuristics here).
      - This class only orchestrates; it doesn't interpret the message itself.
    """

    INTENT_NAME = "property_business_orchestrator"

    def __init__(
        self,
        logger,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        exports_dir: str = "exports",
        max_chars: int = 2000,
    ):
        super().__init__(logger)

        # Shared LLM instance for detectors that accept a ready-made client
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            response_format={"type": "json_object"},
        )

        # Build detectors in priority order
        self._detectors: List[BaseInentDetect] = [
            # 1) Commands over TXT files (needs an LLM instance)
            IntentDetectionLogicCommandExecution(
                logger=logger, llm=self.llm, exports_dir=exports_dir, max_chars=max_chars
            ),
            # 2) Download listings from Zonaprop (uses model_name/temperature internals)
            IntentDetectionLogicPropertyDownload(
                logger=logger, model_name=model_name, temperature=temperature
            ),
        ]

        # Keep a reference to the detector that is mid-flight (e.g., issued a REPROMPT)
        self._active_detector: Optional[BaseInentDetect] = None

    # --------------------------------------------------------------------- #
    # Public API (BaseInentDetect)
    # --------------------------------------------------------------------- #

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Iterate detectors in priority order; return the first that handles the message.
        If the handler returns a REPROMPT, stash it to allow resume().
        """
        self._active_detector = None

        for det in self._detectors:
            handled, msg, intent_name, stage = det.try_handle(user_text)
            if handled:
                if stage == "REPROMPT":
                    self._active_detector = det
                return handled, msg, intent_name, stage

        # Nobody handled this turn
        return False, "", None, None

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Delegate to the detector that previously reprompted. If none, try all.
        """
        # If we know who is active, let it resume first.
        if self._active_detector is not None:
            handled, msg, intent_name, stage = self._active_detector.resume_intent(user_text)
            # Clear active detector if it completed.
            if handled and stage == "EXECUTED":
                self._active_detector = None
            return handled, msg, intent_name, stage

        # Fallback: give all detectors a chance to resume (stateless ones will return False)
        for det in self._detectors:
            handled, msg, intent_name, stage = det.resume_intent(user_text)
            if handled:
                if stage == "REPROMPT":
                    self._active_detector = det
                else:
                    self._active_detector = None
                return handled, msg, intent_name, stage

        return False, "", None, None
