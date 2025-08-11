# tests/test_goldens.py
import json, os
from types import SimpleNamespace
from pathlib import Path
import pytest

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from common.util.builder.bot_engine_loader import load_hybrid_bot

GOLDENS = json.loads((Path(__file__).parent / "goldens.json").read_text(encoding="utf-8"))

class SimpleRetriever(BaseRetriever):
    # Pydantic field; NO __init__ manual
    docs: list

    def _get_relevant_documents(self, query, *, run_manager=None):
        def to_doc(d):
            if isinstance(d, Document):
                return d
        # convertir strings / objetos simples a Document
            return Document(page_content=getattr(d, "page_content", str(d)))
        return [to_doc(d) for d in (self.docs or [])]

    async def _aget_relevant_documents(self, query, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)

@pytest.mark.parametrize("case", GOLDENS, ids=[c["name"] for c in GOLDENS])
def test_goldens_route(case):
    os.environ["ZBOT_PROMPT_NAME"] = case.get("prompt_name", "generic")
    bot = load_hybrid_bot(case["client_id"])

    # Stub del chain completo (no pegamos a OpenAI)
    flags = {"rag": False, "fallback": False}
    bot.chain = SimpleNamespace(run=lambda q: _mark(flags, "rag") or f"rag:{q}")
    bot.prompt_bot.handle = lambda q: _mark(flags, "fallback") or f"fallback:{q}"

    # 🔒 Reemplazamos el retriever completo para forzar la ruta
    if case["expected_mode"] == "rag":
        bot.retriever = SimpleRetriever(docs=[Document(page_content="ctx")])
    else:
        bot.retriever = SimpleRetriever(docs=[])

    out = bot.handle(case["question"])

    if case["expected_mode"] == "rag":
        assert flags["rag"] is True and flags["fallback"] is False
        assert str(out).startswith("rag:")
    else:
        assert flags["fallback"] is True and flags["rag"] is False
        assert str(out).startswith("fallback:")

def _mark(flags, key):
    flags[key] = True
    return False
