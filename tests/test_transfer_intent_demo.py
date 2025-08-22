# tests/test_transfer_intent_demo.py
# -*- coding: utf-8 -*-
"""
E2E tests for the demo "send_transfer" intent using a fake LLM.
- No network calls: we stub .llm.invoke() for both the detector and the intent.
- Validates: gate -> detect -> extract -> reprompt (ES) -> resume -> execute.
"""

from types import SimpleNamespace
from typing import List, Any, Dict

from logic.intents.demos.intente_detection.intent_detection_logic_money_transfer import IntentDetectionLogicMoneyTransfer


# --------------------------- Test doubles ---------------------------

class DummyLogger:
    """Minimal logger used in tests (keeps interface only)."""
    def info(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass
    def exception(self, *args, **kwargs): pass


def _last_user_content(messages: List[Any]) -> str:
    """Extract the last message content from LangChain messages."""
    last = messages[-1]
    # LangChain BaseMessage has .content
    return getattr(last, "content", str(last))


def _extract_user_text_from_prompt(prompt: str) -> str:
    """
    Our prompts always include 'User message:\n{user_text}\n\n...'.
    For test fakes we parse that segment when present.
    """
    marker = "User message:\n"
    if marker in prompt:
        body = prompt.split(marker, 1)[1]
        return body.split("\n\n", 1)[0].strip()
    return prompt.strip()


class FakeLLM:
    """
    Deterministic LLM stub for tests.
    It inspects the last prompt and returns JSON strings matching the
    behavior expected by IntentDetectionLogicMoneyTransfer + MoneyTransferIntentLogicDemo.
    """

    def invoke(self, messages: List[Any]) -> SimpleNamespace:
        content = _last_user_content(messages)
        user_text = _extract_user_text_from_prompt(content).lower()

        # 1) Gate prompt -> expects {"is_transfer": true|false}
        if '{"is_transfer": true|false}' in content or '"is_transfer"' in content:
            # Include common Spanish flexions + currencies to reduce FNs in tests
            triggers = [
                "mandar", "manda", "mandale", "mandá",
                "enviar", "enviale", "enviarle",
                "transferir", "transferile", "transferirle",
                "pagar", "pagale", "págale",
                "plata", "dinero", "guita",
                "usd", "ars", "eur"
            ]
            is_transfer = any(t in user_text for t in triggers)
            return SimpleNamespace(content='{"is_transfer": %s}' % ("true" if is_transfer else "false"))

        # 2) Detect prompt -> expects {"intent": "...", "confidence": ...}
        if '"intent"' in content and '"confidence"' in content and 'JSON' in content:
            # If the gate let us come here, just classify as send_transfer
            return SimpleNamespace(content='{"intent": "send_transfer", "confidence": 0.95}')

        # 3) Slot extraction prompt -> expects {"slots": {...}}
        if '"slots"' in content:
            slots: Dict[str, str] = {}
            # Very small deterministic mapping for tests
            if "martina" in user_text:
                slots["recipient"] = "Martina"
            if "juan" in user_text or "@juan" in user_text:
                slots["recipient"] = "Juan"
            if "100 usd" in user_text or "usd 100" in user_text:
                slots["amount"] = "100 USD"
            if "250 usd" in user_text or "usd 250" in user_text:
                slots["amount"] = "250 USD"
            if "150 usd" in user_text or "usd 150" in user_text:
                slots["amount"] = "150 USD"
            return SimpleNamespace(content='{"slots": %s}' % __import__("json").dumps(slots))

        # 4) Reprompt builder -> expects {"reprompt": "..."}
        if '"reprompt"' in content:
            # Ask in Spanish for whichever slot is missing (we don't parse strictly; it's enough for tests)
            ask_amount = "amount" in content or "monto" in content or "cantidad" in content
            ask_recipient = "recipient" in content or "destinatario" in content
            if ask_amount and not ask_recipient:
                return SimpleNamespace(content='{"reprompt": "¿Cuánto dinero te gustaría enviarle a Martina?"}')
            if ask_recipient and not ask_amount:
                return SimpleNamespace(content='{"reprompt": "¿A quién deseas enviar el dinero?"}')
            return SimpleNamespace(content='{"reprompt": "Necesito el monto y el destinatario."}')

        # Safety: if we ever miss a branch, return a valid empty JSON to avoid crashes
        return SimpleNamespace(content="{}")


# ------------------------------ Tests ------------------------------

def _make_logic_with_fakes() -> IntentDetectionLogicMoneyTransfer:
    """Factory that wires the fake LLM into both the detector and the intent."""
    logic = IntentDetectionLogicMoneyTransfer(DummyLogger(), model_name="gpt-4o-mini", temperature=0.0)
    fake = FakeLLM()
    logic.llm = fake
    logic.intent.llm = fake
    logic.reset()  # ensure clean session
    return logic


def test_two_turn_flow_es():
    """
    User provides recipient first → bot reprompts for amount (ES) → user replies amount → executes.
    """
    logic = _make_logic_with_fakes()

    handled, msg, intent, flag = logic.try_handle("necesito enviar plata a Martina")
    assert handled is True
    assert intent == "send_transfer"
    assert flag == "ASK_MISSING"
    assert "cuánto" in msg.lower() or "monto" in msg.lower() or "dinero" in msg.lower()

    handled, msg, intent, flag = logic.resume_intent("100 USD")
    assert handled is True
    assert flag == "COMPLETED"
    assert "✅ Transferencia enviada" in msg
    assert "100 USD" in msg and "Martina" in msg


def test_single_turn_executes_immediately():
    """
    If amount + recipient are in the same sentence, execution should be immediate.
    """
    logic = _make_logic_with_fakes()

    handled, msg, intent, flag = logic.try_handle("por favor mandale 250 USD a Juan")
    assert handled is True
    assert intent == "send_transfer"
    assert flag == "COMPLETED"
    assert "250 USD" in msg and "Juan" in msg


def test_non_transfer_is_not_handled():
    """
    A general question must not trigger the transfer intent.
    """
    logic = _make_logic_with_fakes()

    handled, msg, intent, flag = logic.try_handle("¿quién es el presidente de Suecia?")
    assert handled is False
    assert intent is None
    assert flag is None


def test_resume_ignores_out_of_context_after_completion():
    """
    After a completed session, the next unrelated turn should not be captured by resume_intent.
    """
    logic = _make_logic_with_fakes()

    # Complete a session
    logic.try_handle("quiero mandarle plata a Martina")
    logic.resume_intent("100 USD")

    # Now an unrelated question
    handled, msg, intent, flag = logic.resume_intent("¿cómo está el clima?")
    assert handled is False
