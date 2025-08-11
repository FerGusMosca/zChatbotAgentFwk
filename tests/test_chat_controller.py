# tests/test_chat_controller.py
from fastapi.testclient import TestClient
from main import app
import types

client = TestClient(app)

def test_chat_controller_ok(monkeypatch):
    # Fake bot that always returns a string (no network calls)
    class FakeBot:
        def handle(self, q: str) -> str:
            return "ok-from-fake-bot"

    # Patch where the controller imports it
    import controllers.chat_controller as cc
    monkeypatch.setattr(cc, "load_hybrid_bot", lambda *args, **kwargs: FakeBot())

    res = client.post("/chatbot/ask", json={"question": "hola"})
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data.get("answer"), str)
    assert data["answer"] == "ok-from-fake-bot"

def test_chat_controller_400_missing_question():
    res = client.post("/chatbot/ask", json={})
    assert res.status_code == 400
    data = res.json()
    assert "Missing 'question'" in data.get("detail", "")

def test_chat_controller_500_when_bot_raises(monkeypatch):
    class BoomBot:
        def handle(self, q: str) -> str:
            raise RuntimeError("kaboom")

    import controllers.chat_controller as cc
    monkeypatch.setattr(cc, "load_hybrid_bot", lambda *args, **kwargs: BoomBot())

    res = client.post("/chatbot/ask", json={"question": "hola"})
    assert res.status_code == 500
    data = res.json()
    assert data.get("error") == "Internal error" or "error" in data
