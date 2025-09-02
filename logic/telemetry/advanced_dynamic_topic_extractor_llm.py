# audit/dynamic_topic_extractor.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional

from openai import OpenAI

from common.util.loader.intent_prompt_loader import IntentPromptLoader
from common.util.telemetry.topic_event_dto import TopicEventDTO
from logic.logic.custom_logging_logic import CustomLoggingLogic


class AdvancedDynamicTopicExtractorLLM(CustomLoggingLogic):
    """
    Advanced topic extractor that:
    - Loads its prompt from /input/intent_prompts (no hardcoded prompt).
    - Calls the LLM expecting STRICT JSON (response_format=json_object).
    - Parses into TopicEventDTO with sane defaults and clamps.
    - Logs a compact label + a structured event for telemetry.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        prompt_key: str = "advanced_topic_extractor",
    ) -> None:
        super().__init__()
        self.client = OpenAI()
        self.model = model
        self.prompt_key = prompt_key

        # Load prompt text from the same mechanism you use elsewhere
        self.prompt_template: str = IntentPromptLoader.get_text(self.prompt_key)

    # ------------ public API ------------ #
    def handle(self, question: str, logger) -> TopicEventDTO:
        """
        Extracts topic + signals from a user question.
        Returns a TopicEventDTO and logs telemetry.
        """
        prompt = self._build_prompt(question)

        try:
            resp = self.client.chat.completions.create(
                model=self.model,
                temperature=0,
                response_format={"type": "json_object"},  # maximize JSON correctness
                messages=[
                    {"role": "system", "content": "You return STRICT JSON only."},
                    {"role": "user", "content": prompt},
                ],
            )
            raw = resp.choices[0].message.content.strip()
            data = self._safe_json_load(raw)

            dto = self._to_dto(data)

            # Back-compat label line (compact)
            logger.info("topic_detected --> topic:%s", dto.topic)
            logger.info("topic_event %s", json.dumps(dto.asdict(), ensure_ascii=False))

            # HINT: here you could inject a persistence class and store dto.asdict() in DB.
            # e.g., self.persistence.save_topic_event(dto)

            return dto

        except Exception as ex:
            logger.error(f"dynamic_topic_extractor_error: {ex} | query={question}")
            dto = self._fallback_dto()
            logger.info("topic_event", extra=dto.asdict())
            return dto

    # ------------ internals ------------ #
    def _build_prompt(self, question: str) -> str:
        """
        Renders the external prompt with the user question.
        Your .md should describe the JSON schema to return.
        """
        # Very lightweight templating; your MD can contain a token like {{QUESTION}}
        return self.prompt_template.replace("{{QUESTION}}", question)

    @staticmethod
    def _safe_json_load(raw: str) -> Dict[str, Any]:
        """
        Attempts to parse JSON. If the model wrapped it with prose,
        trims to the first {...} block.
        """
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start, end = raw.find("{"), raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            raise

    @staticmethod
    def _clamp_float(v: Any, lo: float, hi: float, dflt: float) -> float:
        try:
            x = float(v)
            return max(lo, min(hi, x))
        except Exception:
            return dflt

    @staticmethod
    def _clamp_int(v: Any, lo: int, hi: int, dflt: int) -> int:
        try:
            x = int(float(v))
            return max(lo, min(hi, x))
        except Exception:
            return dflt

    def _to_dto(self, data: Dict[str, Any]) -> TopicEventDTO:
        """
        Maps raw dict -> TopicEventDTO with normalization and defaults.
        """
        topic = str(data.get("topic", "UNKNOWN")).upper().strip().replace(" ", "_")[:64]
        subtopic = (data.get("subtopic") or None)
        intent = (data.get("intent") or None)

        confidence = self._clamp_float(data.get("confidence", 0.5), 0.0, 1.0, 0.5)
        sentiment = self._clamp_int(data.get("sentiment", 0), -2, 2, 0)
        urgency = self._clamp_int(data.get("urgency", 0), 0, 3, 0)

        pii_detected = bool(data.get("pii_detected", False))
        cr = str(data.get("compliance_risk", "low")).lower()
        compliance_risk = cr if cr in {"low", "med", "high"} else "low"

        suggested_action = (
            str(data.get("suggested_action", "NO_ACTION")).upper().replace(" ", "_")
        )

        outcome = str(data.get("outcome", "unknown")).lower()
        if outcome not in {"unknown", "success", "failed", "escalated", "fallback"}:
            outcome = "unknown"

        return TopicEventDTO(
            run_id=str(uuid.uuid4()),
            topic=topic,
            subtopic=subtopic,
            intent=intent,
            confidence=confidence,
            sentiment=sentiment,
            urgency=urgency,
            pii_detected=pii_detected,
            compliance_risk=compliance_risk,
            suggested_action=suggested_action,
            outcome=outcome,
        )

    @staticmethod
    def _fallback_dto() -> TopicEventDTO:
        """Safe baseline DTO when the call fails."""
        return TopicEventDTO(
            run_id=str(uuid.uuid4()),
            topic="UNKNOWN",
            subtopic=None,
            intent=None,
            confidence=0.0,
            sentiment=0,
            urgency=0,
            pii_detected=False,
            compliance_risk="low",
            suggested_action="NO_ACTION",
            outcome="unknown",
        )
