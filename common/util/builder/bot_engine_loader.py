import os
from dotenv import load_dotenv
from langchain.chains import ConversationalRetrievalChain
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.memory import ConversationBufferMemory
from typing import Dict, Tuple, Optional
from common.config.settings import settings
from logic.pipeline.hybrid_bot import HybridBot
from logic.pipeline.prompt_based_chatbot import PromptBasedChatbot
from common.util.loader.prompt_loader import PromptLoader
from pathlib import Path
import importlib
load_dotenv()

_HYBRID_BOT_CACHE: Dict[Tuple[str, str], HybridBot] = {}  # (client_id, session_id) -> bot
def load_bot_for_client(client_name: str):
    """
    Loads a chatbot that uses only prompt-based behavior.

    This bot:
    - Does NOT use FAISS or any vector database.
    - Does NOT answer content-specific questions.
    - Only responds using predefined prompts (e.g., tone, role, structure).

    Use case:
    - Useful for stylistic assistants or copilots that don't need knowledge retrieval.
    """
    prompt_name = os.getenv("ZBOT_PROMPT_NAME", "generic_prompt")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    loader = PromptLoader(os.path.join(base_dir, "../prompts"))
    return PromptBasedChatbot(loader, prompt_name=prompt_name)


def load_qa_chain_for_client(client_id: str = None):
    """
    Loads a simple QA bot using only FAISS and memory (RAG-style).

    This bot:
    - Uses a trained FAISS vector store to retrieve knowledge.
    - Uses LangChain memory to retain conversational context.
    - Does NOT use prompts for style.
    - Does NOT fallback to general OpenAI completion when no match is found.

    Use case:
    - Good for pure knowledge-retrieval chatbots without behavioral customization.
    """
    client_id = client_id or settings.bot_profile
    print(f"🤖 Loading QA bot for client: {client_id}")

    vectorstore_path = f"vectorstores/{client_id}"
    vectordb = FAISS.load_local(
        vectorstore_path,
        OpenAIEmbeddings(),
        allow_dangerous_deserialization=True
    )

    llm = ChatOpenAI(temperature=0)
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)

    qa_chain = ConversationalRetrievalChain.from_llm(
        llm=llm,
        retriever=vectordb.as_retriever(),
        memory=memory
    )

    return qa_chain


def load_hybrid_bot(
    client_id: Optional[str] = None,
    *,
    session_id: Optional[str] = None,
    cache_scope: str = "session",
    force_reload: bool = False
) -> HybridBot:
    """
    Load or reuse a HybridBot instance.

    cache_scope:
        "session" (default) → use (client_id, session_id) as cache key.
        "client"            → use only client_id as cache key.
    force_reload:
        True → force rebuild and replace the instance in cache.
    """
    client_id = client_id or settings.bot_profile
    print(f"🤖 Loading hybrid bot for client: {client_id}")

    # --- Cache key resolution ---
    if cache_scope == "session":
        if not session_id:
            # If no session_id provided, fall back to client-level cache
            cache_key = (client_id, "__DEFAULT__")
        else:
            cache_key = (client_id, session_id)
    else:
        # Client-level cache only (all sessions share the same bot)
        cache_key = (client_id, "__CLIENT__")

    # --- Reuse existing bot if found ---
    if not force_reload and cache_key in _HYBRID_BOT_CACHE:
        return _HYBRID_BOT_CACHE[cache_key]

    # --- Normal (re)construction path ---
    # Walk upwards to find repo root (must contain /vectorstores and /prompts)
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        if (parent / "vectorstores").exists() and (parent / "prompts").exists():
            repo_root = parent
            break
    else:
        # Fallback: one level up from this file (legacy behavior)
        repo_root = Path(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    # --- Load FAISS index for this client ---
    vectorstore_path = repo_root / "vectorstores" / client_id
    emb = OpenAIEmbeddings()
    vectordb = FAISS.load_local(
        str(vectorstore_path),
        emb,
        allow_dangerous_deserialization=True
    )
    try:
        ntotal = getattr(getattr(vectordb, "index", None), "ntotal", None)
        print(f"[VDB] path={vectorstore_path} | ntotal={ntotal}")
    except Exception:
        pass

    # --- Load prompt (prompt name comes from env or defaults) ---
    prompts_path = repo_root / "prompts"
    prompt_name = os.getenv("ZBOT_PROMPT_NAME", "generic_prompt")  # e.g., 'generic_inmob'
    prompt_loader = PromptLoader(str(prompts_path), prompt_name=prompt_name)
    prompt_bot = PromptBasedChatbot(prompt_loader, prompt_name=prompt_name)

    # --- Model configuration (from env or defaults) ---
    model_name = os.getenv("OPENAI_MODEL_NAME", "gpt-4o")
    temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.0"))
    top_k = int(os.getenv("TOP_K", "4"))

    # --- Instantiate HybridBot ---
    bot = HybridBot(
        vectordb=vectordb,
        prompt_bot=prompt_bot,
        retrieval_score_threshold=settings.retrieval_score_threshold,
        model_name=model_name,
        temperature=temperature,
        top_k=top_k,
    )

    # --- Save in cache for reuse ---
    _HYBRID_BOT_CACHE[cache_key] = bot
    return bot


