# tests/test_hybrid_bot.py
from types import SimpleNamespace
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from logic.pipeline.hybrid_bot import HybridBot

class SimpleRetriever(BaseRetriever):

    # Pydantic field; no __init__ manual
    docs: list

    def _get_relevant_documents(self, query, *, run_manager=None):
        def to_doc(d):
            if isinstance(d, Document):
                return d
            return Document(page_content=getattr(d, "page_content", str(d)))
        return [to_doc(d) for d in (self.docs or [])]

    async def _aget_relevant_documents(self, query, *, run_manager=None):
        return self._get_relevant_documents(query, run_manager=run_manager)

class FakeVectorDB:
    def __init__(self, docs):
        self._docs = docs
    def as_retriever(self, search_kwargs=None):
        return SimpleRetriever(docs=self._docs)

class FakePromptBot:
    def __init__(self):
        self.system_prompt = "You are a helpful assistant."
        self.fallback_called = False
    def handle(self, q: str) -> str:
        self.fallback_called = True
        return f"fallback:{q}"

def test_hybrid_bot_fallback_path():
    # No docs -> debe ir a fallback y NO llamar chain.run
    vectordb = FakeVectorDB(docs=[])
    prompt_bot = FakePromptBot()
    bot = HybridBot(vectordb, prompt_bot)

    # Reemplazamos TODO chain por un stub que explota si lo llaman
    bot.chain = SimpleNamespace(run=lambda q: (_ for _ in ()).throw(
        AssertionError("chain.run should not be called on fallback path")
    ))

    out = bot.handle("q-out-of-corpus")
    assert out.startswith("fallback:")
    assert prompt_bot.fallback_called is True

def test_hybrid_bot_rag_path():
    # Hay un doc -> debe ir por RAG y NO por fallback
    doc = SimpleNamespace(page_content="some context")
    vectordb = FakeVectorDB(docs=[doc])
    prompt_bot = FakePromptBot()
    bot = HybridBot(vectordb, prompt_bot)

    bot.chain = SimpleNamespace(run=lambda q: f"rag:{q}")

    out = bot.handle("q-covered")
    assert out.startswith("rag:")
    assert prompt_bot.fallback_called is False
