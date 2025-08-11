import pytest
from common.util.builder.bot_engine_loader import load_hybrid_bot

def test_hybrid_bot_load_and_respond():
    bot = load_hybrid_bot("demo_client")
    result = bot.ask("Test message")
    assert isinstance(result, str)
    assert len(result) > 0
