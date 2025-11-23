from typing import Tuple, Optional
from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect


class IntentDetectionLogicDummy(BaseInentDetect):
    """
    Dummy intent detector.
    - Never detects any intent.
    - Used when no intent system should run.
    """

    def __init__(self, logger):
        super().__init__()
        self.logger = logger

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Always return: no intent detected.
        """
        self.logger.info("dummy_intent_noop", extra={"text": user_text})
        return False, "", None, None

    def resume_intent(self, user_text: str):
        """
        Dummy never resumes anything.
        """
        self.logger.info("dummy_intent_resume_noop", extra={"text": user_text})
        return False, "", None, None

    def reset(self):
        """Nothing to reset."""
        pass
