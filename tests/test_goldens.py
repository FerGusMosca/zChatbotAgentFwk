# tests/test_goldens.py
import json, os
from types import SimpleNamespace
from pathlib import Path
import pytest

from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from common.util.builder.bot_engine_loader import load_hybrid_bot


class SimpleRetriever(BaseRetriever):
    """Simple retriever for testing: always returns docs if provided."""
    docs: list

    def _get_relevant_documents(self, query, *, run_manager=None):
        def to_doc(d):
            if isinstance(d, Document):
                return d
            return Document(page_content=getattr(d, "page_content", str(d)))
        return [to_doc(d) for d in (self.docs or [])]

    async def _aget_relevant_documents(self, query, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)


# Load golden cases
with open("tests/goldens.json", encoding="utf-8") as f:
    GOLDENS = json.load(f)


def _mark(flags, key):
    flags[key] = True
    return None


@pytest.mark.parametrize("case", GOLDENS, ids=[c["name"] for c in GOLDENS])
def test_goldens_route(case):
    # set prompt name
    prompt_name= case.get("prompt_name", "")
    print(f"Using PROMPT name {prompt_name}")
    os.environ["ZBOT_PROMPT_NAME"] = prompt_name
    bot = load_hybrid_bot(case["client_id"],prompt_name=prompt_name,force_reload=True)

    # flags to track which path is used
    flags = {"rag": False, "fallback": False}

    out = bot.handle(case["question"])
    mode = bot.last_metrics["mode"]
    score =bot.last_metrics["best_score"]

    print (f"BOT used mode {mode}--> score={score}")

    if mode == "rag":
        flags["rag"] = True
    else:
        flags["fallback"] = True

    print(
        f"[Golden] case={case['name']} "
        f"expected={case['expected_mode']} "
        f"got={out} "
        f"flags={flags}"
    )

    if case["expected_mode"] == "rag":
        assert flags["rag"] and not flags["fallback"]
        #assert str(out).startswith("RAG:")
    elif case["expected_mode"] == "fallback":
        assert flags["fallback"] and not flags["rag"]
        #assert str(out).startswith("FALLBACK:")
