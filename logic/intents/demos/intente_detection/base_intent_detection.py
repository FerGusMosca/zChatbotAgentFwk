# logic/intents/demos/intente_detection/base_intent_detection.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Tuple


class BaseInentDetect(ABC):
    """
    Base class for intent detectors.

    Handlers must return:
      Tuple[ handled: bool, message: str, intent_name: Optional[str], stage: Optional[str] ]
    """

    def __init__(self, logger=None) -> None:
        self.logger = logger

    @abstractmethod
    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """Attempt to detect+start the intent from a fresh message."""
        raise NotImplementedError

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Continue an ongoing intent. Default: not handled.
        Override in subclasses that keep state.
        """
        return False, "", None, None
