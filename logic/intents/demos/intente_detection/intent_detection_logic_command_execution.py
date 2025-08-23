from __future__ import annotations
from typing import Dict, Optional, Tuple
import json
from langchain.prompts import ChatPromptTemplate

from common.util.loader.intent_prompt_loader import IntentPromptLoader
from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intents_execution.file_command_executor_demo import FileCommandExecutor


class IntentDetectionLogicCommandExecution(BaseInentDetect):
    """
    Intent detector for commands over an exported TXT file.
    - LLM-only detection & slot extraction.
    - 'action' is kept as free text in the user's language (no enums).
    """

    INTENT_NAME = "command_execution_on_file"

    def __init__(self, logger, llm, exports_dir: str = "exports", max_chars: int = 24000):
        super().__init__(logger)
        self.llm = llm
        self.exec = FileCommandExecutor(logger=logger, llm=llm, exports_dir=exports_dir, max_chars=max_chars)

        # Prompt to classify if the user request is about processing a file (yes/no).
        self.classifier_prompt = IntentPromptLoader.get_prompt("intent_detect_process_file_classifier")

        # Prompt to extract slots from the user request:
        # - filename (the TXT file mentioned)
        # - action (the command in free text, rewritten as imperative)
        # - neighborhood (optional filter if present)
        self.cmd_extract_prompt = IntentPromptLoader.get_prompt("intent_detect_process_file_slot_extract")

        # Prompt to generate a reprompt if any required slot is missing.
        # It asks the user (in the same language) for only the missing keys.
        self.reprompt_prompt = IntentPromptLoader.get_prompt("intent_detect_process_file_reprompt")

    # ---------------------- Public API -----------------------

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        # 1) detect intent
        if not self._looks_like_cmd_exec(user_text):
            return False, "", None, None

        # 2) extract slots
        slots = self._try_extract_slots(user_text)
        missing = self._missing_slots(slots)

        # 3) reprompt if needed
        if missing:
            reprompt = self._reprompt(missing, user_text)
            return True, reprompt, self.INTENT_NAME, "REPROMPT"

        # 4) execute via the executor service (action is free-text)
        msg = self.exec.execute(
            filename=slots["filename"],
            action=slots["action"],
            neighborhood=slots.get("neighborhood")
        )
        return True, msg, self.INTENT_NAME, "EXECUTED"

    def resume_intent(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        # Stateless: rerun detection path
        return self.try_handle(user_text)

    # ---------------------- LLM helpers ----------------------

    def _looks_like_cmd_exec(self, text: str) -> bool:
        """Robust classifier: never raises; logs raw output; tolerates alias keys."""
        try:
            msgs = self.classifier_prompt.format_messages(user_text=text)
            resp = self.llm.invoke(msgs)

            raw = getattr(resp, "content", None)
            if self.logger:
                self.logger.error(f"[cmd_classify] raw_type={type(raw).__name__} raw={raw!r}")

            if isinstance(raw, str):
                data = json.loads(raw)
            elif isinstance(raw, dict):
                data = raw
            else:
                data = getattr(resp, "additional_kwargs", {}) or {}
                if self.logger:
                    self.logger.error(f"[cmd_classify] using additional_kwargs={data!r}")

            for key in ("cmd_exec", "is_cmd", "command", "execute_command"):
                if key in data:
                    val = data[key]
                    if isinstance(val, str):
                        val = val.strip().lower() == "true"
                    return bool(val)
            return False

        except Exception as ex:
            if self.logger:
                self.logger.error(f"[cmd_classify] EXC: {ex!r}")
            return False

    def _try_extract_slots(self, text: str):
        """
        Defensive slot parsing (action is FREE TEXT).
        """
        out = {"filename": None, "action": None, "neighborhood": None}
        try:
            msgs = self.cmd_extract_prompt.format_messages(user_text=text)
            resp = self.llm.invoke(msgs)

            raw = getattr(resp, "content", None)
            if self.logger:
                self.logger.error(f"[cmd_slots] raw_type={type(raw).__name__} raw={raw!r}")

            if isinstance(raw, str):
                cleaned = raw.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.strip("` \n")
                    idx = cleaned.find("{")
                    if idx != -1:
                        cleaned = cleaned[idx:]
                try:
                    data = json.loads(cleaned)
                except Exception:
                    data = getattr(resp, "additional_kwargs", {}) or {}
            elif isinstance(raw, dict):
                data = raw
            else:
                data = getattr(resp, "additional_kwargs", {}) or {}

            slots = data.get("slots", {}) if isinstance(data, dict) else {}
            if not isinstance(slots, dict):
                slots = {}

            for k in out.keys():
                v = slots.get(k)
                out[k] = (v.strip() if isinstance(v, str) else None) or None

            if self.logger:
                self.logger.error(f"[cmd_slots] parsed={out}")
            return out

        except Exception as ex:
            if self.logger:
                self.logger.error(f"[cmd_slots] EXC: {ex!r}")
            return out

    def _missing_slots(self, slots: Dict[str, Optional[str]]) -> Dict[str, str]:
        # Action must be present as FREE TEXT (no enum).
        miss = {}
        if not slots.get("filename"):
            miss["filename"] = "TXT file name (e.g., caba_venta_YYYYMMDD_HHMM.txt)"
        if not slots.get("action"):
            miss["action"] = "your command in your own words (imperative phrase)"
        if (slots.get("action") and "en " in slots["action"].lower()) and (  # cheap hint; still optional
            "más cara en " in slots["action"].lower()
        ) and not slots.get("neighborhood"):
            # If the user clearly meant a neighborhood, ask for it (kept optional if extractor didn't find it)
            miss["neighborhood"] = "CABA neighborhood (e.g., Recoleta, Palermo)"
        return miss

    def _reprompt(self, missing: Dict[str, str], user_text: str) -> str:
        try:
            msgs = self.reprompt_prompt.format_messages(
                user_text=user_text,
                missing_keys=", ".join(missing.keys())
            )
            resp = self.llm.invoke(msgs)
            raw = getattr(resp, "content", None)
            data = json.loads(raw) if isinstance(raw, str) else (raw or {})
            r = (data.get("reprompt") or "").strip()
            return r or "¿Qué archivo TXT y qué acción querés que ejecute?"
        except Exception:
            return "¿Qué archivo TXT y qué acción querés que ejecute?"
