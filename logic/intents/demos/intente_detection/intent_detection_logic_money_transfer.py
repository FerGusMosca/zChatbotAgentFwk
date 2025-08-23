from typing import Tuple, Optional
from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate
import json

from logic.intents.demos.intente_detection.base_intent_detection import BaseInentDetect
from logic.intents.demos.intents_execution.money_transfer_intent_logic_demo import MoneyTransferIntentLogicDemo


class IntentDetectionLogicMoneyTransfer(BaseInentDetect):
    """
    GPT-only intent manager:
    - try_handle(...) starts a new 'send_transfer' session if detected.
    - resume_intent(...) continues an ongoing slot-filling session.
    - All interpretation (classification, extraction, reprompt text) is done by GPT.
    """

    def __init__(self, logger, model_name: str = "gpt-4o-mini", temperature: float = 0.0):
        super().__init__()
        self.logger = logger
        self.llm = ChatOpenAI(
            model_name=model_name,
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        self.intent = MoneyTransferIntentLogicDemo(logger, model_name=model_name, temperature=temperature)

        # Simple in-memory session (demo scope). In prod, persist by user_id.
        self.active = getattr(IntentDetectionLogicMoneyTransfer, "_active", False)
        self.collected = getattr(IntentDetectionLogicMoneyTransfer, "_collected", {})
        self.awaiting_keys = getattr(IntentDetectionLogicMoneyTransfer, "_awaiting_keys", [])

        # Detection prompt (JSON-only; braces escaped).
        self.detect_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are an intent classifier. Return ONLY valid JSON (no extra text). "
             "Supported intents: ['send_transfer'] and 'NONE'. "
             "Classify as 'send_transfer' whenever the user wants to send/transfer/pay money, "
             "including when they ASK IF they/we can send (e.g., '¿podemos…?', '¿podrías…?', '¿le podés…?'). "
             "Do not infer slot values here."),
            ("user", "Quiero transferirle unos mangos a Maria"),
            ("assistant", "{{\"intent\": \"send_transfer\", \"confidence\": 0.92}}"),
            ("user", "Pasale guita a @juan, después te paso el monto"),
            ("assistant", "{{\"intent\": \"send_transfer\", \"confidence\": 0.90}}"),
            ("user", "¿Podemos mandarle dinero a Martina?"),
            ("assistant", "{{\"intent\": \"send_transfer\", \"confidence\": 0.95}}"),
            ("user", "le podemos mandar dinero a Martina?"),
            ("assistant", "{{\"intent\": \"send_transfer\", \"confidence\": 0.95}}"),
            ("user", "¿Cuánto salen los mangos (la fruta) en el súper?"),
            ("assistant", "{{\"intent\": \"NONE\", \"confidence\": 0.85}}"),
            ("user",
             "User message:\n{user_text}\n\n"
             "Respond EXACT JSON:\n"
             "{{\"intent\": \"send_transfer\"|\"NONE\", \"confidence\": <number 0..1>}}"),
        ])

        # Binary gate: decide if the message is REALLY about sending money.
        self.gate_prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a precise detector. Return ONLY valid JSON.\n"
             "Answer whether the user is asking to send/transfer/pay money to someone.\n"
             "Treat as TRUE also when the user asks IF we/you can send (e.g., '¿podemos…?', "
             "'¿le podés…?', '¿puedes…?'). Prefer TRUE when the message explicitly mentions "
             "money/transfer words (dinero, plata, guita, mandar, transferir, pagar), unless it is "
             "clearly off-topic (e.g., presidents, weather, trivia)."),

            # Negative few-shots
            ("user", "¿Quién es el presidente de Suecia?"),
            ("assistant", "{{\"is_transfer\": false}}"),
            ("user", "hola, ¿cómo estás?"),
            ("assistant", "{{\"is_transfer\": false}}"),

            # Positive few-shots (questions/permissions)
            ("user", "¿Podemos mandarle dinero a Martina?"),
            ("assistant", "{{\"is_transfer\": true}}"),
            ("user", "le podemos mandar dinero a Martina?"),
            ("assistant", "{{\"is_transfer\": true}}"),
            ("user", "¿Le podés mandar plata a Juan?"),
            ("assistant", "{{\"is_transfer\": true}}"),

            # Actual input (NOTE: escape braces, keep {user_text} single-braced)
            ("user", "User message:\n{user_text}\n\nRespond EXACT JSON: {{\"is_transfer\": true|false}}"),
        ])

    def _persist_session(self) -> None:
        IntentDetectionLogicMoneyTransfer._active = self.active
        IntentDetectionLogicMoneyTransfer._collected = self.collected
        IntentDetectionLogicMoneyTransfer._awaiting_keys = self.awaiting_keys

    # ---------- lifecycle helpers ----------

    def reset(self) -> None:
        self.active = False
        self.collected = {}
        self.awaiting_keys = []
        self._persist_session()

    # ---------- public API ----------

    def try_handle(self, user_text: str) -> Tuple[bool, str, Optional[str], Optional[str]]:
        """
        Start a new session if GPT detects 'send_transfer'.
        Returns: (handled, answer, intent_name, flag) where flag ∈ {'ASK_MISSING', 'COMPLETED'}.
        GPT-only: binary gate -> classifier -> slot extraction -> reprompt/execute.
        """

        # ---- 1) Binary gate: is this REALLY about sending/transferring money? ----
        try:
            gate_msgs = self.gate_prompt.format_messages(user_text=user_text)
            gate_resp = self.llm.invoke(gate_msgs)
            gate_data = json.loads((gate_resp.content or "").strip())
            if not bool(gate_data.get("is_transfer", False)):
                return False, "", None, None
        except Exception as ex:
            # Be conservative: if gate parsing fails, do NOT trigger intent
            self.logger.exception("intent_gate_parse_error", extra={"error": str(ex)})
            return False, "", None, None

        # ---- 2) Classifier: choose between 'send_transfer' and 'NONE' ----
        try:
            cls_msgs = self.detect_prompt.format_messages(user_text=user_text)
            cls_resp = self.llm.invoke(cls_msgs)
            raw = (cls_resp.content or "").strip()
            data = json.loads(raw)
        except Exception as ex:
            self.logger.exception("intent_detection_json_error", extra={"error": str(ex)})
            return False, "", None, None

        intent_name = data.get("intent", "NONE")
        try:
            confidence = float(data.get("confidence", 0.0))
        except Exception:
            confidence = 0.0

        # Tight threshold to avoid false positives after unrelated questions
        if intent_name != "send_transfer" or confidence < 0.65:
            return False, "", None, None

        # ---- 3) Start a fresh session (in-memory for demo) ----
        self.active = True
        self.collected = {}
        self.awaiting_keys = []
        if hasattr(self, "_persist_session"):
            self._persist_session()  # optional: persist across instances

        # ---- 4) First-pass slot extraction (GPT-only) ----
        try:
            extracted = self.intent.try_extract(user_text)
        except Exception as ex:
            self.logger.exception("intent_extract_error", extra={"error": str(ex)})
            extracted = {}

        if extracted:
            self.collected.update(extracted)
            if hasattr(self, "_persist_session"):
                self._persist_session()

        missing = self.intent.missing_slots(self.collected)
        self.logger.info(
            "intent_detected",
            extra={"intent": self.intent.name, "confidence": confidence, "initial_slots": self.collected},
        )

        if missing:
            # Ask for missing info; GPT writes follow-up in the user's language
            self.awaiting_keys = list(missing.keys())
            if hasattr(self, "_persist_session"):
                self._persist_session()
            reprompt = self.intent.build_prompt_for_missing(missing, user_text=user_text)
            return True, reprompt, self.intent.name, "ASK_MISSING"

        # ---- 5) All slots present -> execute and end session ----
        msg = self.intent.execute(self.collected)
        self.reset()  # also persists if you implemented _persist_session() inside
        return True, msg, self.intent.name, "COMPLETED"

    def resume_intent(self, user_text: str):
        if not self.active:
            # in case a fresh instance didn't hydrate yet
            self.active = getattr(IntentDetectionLogicMoneyTransfer, "_active", False)
            self.collected = getattr(IntentDetectionLogicMoneyTransfer, "_collected", {})
            self.awaiting_keys = getattr(IntentDetectionLogicMoneyTransfer, "_awaiting_keys", [])
            if not self.active:
                return False, "", None, None

        extracted = self.intent.try_extract(user_text)
        if extracted:
            self.collected.update(extracted)
            self._persist_session()

        missing = self.intent.missing_slots(self.collected)
        if missing:
            self.awaiting_keys = list(missing.keys())
            self._persist_session()
            return True, self.intent.build_prompt_for_missing(missing,
                                                              user_text=user_text), self.intent.name, "ASK_MISSING"

        msg = self.intent.execute(self.collected)
        self.reset()
        return True, msg, self.intent.name, "COMPLETED"




