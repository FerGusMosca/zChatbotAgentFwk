from __future__ import annotations
from typing import Dict, Optional, Tuple
import json
from langchain.prompts import ChatPromptTemplate

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

        # 1) Classifier: is this a command over a file?
        self.classifier_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a STRICT binary classifier for file-processing requests.\n"
             "Return ONLY this exact JSON: {{\"cmd_exec\": true/false}}\n"
             "Answer true when the user asks to open/read/process/scan/compute/search/show data from a local file by name "
             "(e.g., .txt/.csv/ndjson), even if they don't explicitly say 'execute a command'."),
            ("user", "User message:\n{user_text}")
        ])

        # 2) Slot extractor: filename, action (FREE TEXT), neighborhood (optional)
        self.cmd_extract_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a STRICT information extractor for file-based commands.\n"
             "Return ONLY valid JSON. Nothing else.\n\n"
             "Output MUST be exactly:\n"
             "{{\"slots\": {{\"filename\": <string or null>, \"action\": <string or null>, \"neighborhood\": <string or null>}}}}\n\n"
             "Rules:\n"
             "- Read the user message in Spanish or English and extract:\n"
             "  • filename: the TXT filename mentioned (e.g., \"caba_venta_20250822_1950.txt\"). Trim spaces/newlines. If not present -> null.\n"
             "  • action: REWRITE the user's request as a short imperative phrase in the SAME language of the user (e.g., \"decime cuál es la propiedad más cara\", \"show me the whole file\", \"filtrá por Recoleta y decime la más cara\"). No markdown, no quotes, no extra commentary.\n"
             "  • neighborhood: ONLY fill when the user's request clearly restricts to a specific neighborhood; otherwise -> null. If the neighborhood is part of the action text, still extract it here.\n"
             "- Do NOT add extra keys. Do NOT output markdown. Respond ONLY strict JSON.\n\n"
             "Examples (guidance, DO NOT echo):\n"
             "1) \"Procesa caba_venta_20250822_1950.txt y decime la propiedad más cara\" →\n"
             "   {{\"slots\": {{\"filename\": \"caba_venta_20250822_1950.txt\", \"action\": \"decime cuál es la propiedad más cara\", \"neighborhood\": null}}}}\n"
             "2) \"En caba_venta_20250822_1950.txt, propiedad más cara en Recoleta\" →\n"
             "   {{\"slots\": {{\"filename\": \"caba_venta_20250822_1950.txt\", \"action\": \"decime la propiedad más cara en Recoleta\", \"neighborhood\": \"Recoleta\"}}}}\n"
             "3) \"Mostrame todo el archivo caba_venta_20250822_1950.txt\" →\n"
             "   {{\"slots\": {{\"filename\": \"caba_venta_20250822_1950.txt\", \"action\": \"mostrame todo el archivo\", \"neighborhood\": null}}}}\n"
             ),
            ("user",
             "User message:\n{user_text}\n\n"
             "Extract the three fields and respond ONLY with strict JSON.")
        ])

        # 3) Reprompt when something is missing
        self.reprompt_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a dialogue assistant. Return ONLY valid JSON. "
             "Write ONE short follow-up question in the SAME language as the user "
             "to collect ONLY the missing keys. Keep it concise (1–2 lines)."),
            ("user",
             "User message:\n{user_text}\n"
             "Missing keys (canonical): {missing_keys}\n"
             "Return EXACT JSON:\n"
             "{{\"reprompt\": <string>}}")
        ])

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
