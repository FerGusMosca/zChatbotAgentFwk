import os
from dotenv import load_dotenv
from langchain.chains import ConversationalRetrievalChain
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings, ChatOpenAI
from langchain.memory import ConversationBufferMemory
from typing import Dict, Tuple, Optional
from common.config.settings import get_settings
from logic.pipeline.hybrid_bot import HybridBot
from logic.pipeline.prompt_based_chatbot import PromptBasedChatbot
from common.util.loader.prompt_loader import PromptLoader
from pathlib import Path
import importlib

load_dotenv()

_HYBRID_BOT_CACHE: Dict[Tuple[str, str], HybridBot] = {}  # (client_id, session_id) -> bot


def load_hybrid_bot(
    client_id: str,
    *,
    session_id: Optional[str] = None,
    cache_scope: str = "session",
    force_reload: bool = False,
    prompt_name=None,
) -> HybridBot:
    """
    Load or reuse a HybridBot instance.

    ✅ client_id must be the FULL PATH to the vectorstore directory.
    ✅ Prompts always loaded from repo's /prompts directory.
    """

    if not client_id:
        raise ValueError("❌ 'client_id' must be provided explicitly — no fallback allowed.")

    print(f"🤖 Loading hybrid bot strictly for client_id (full path): {client_id}")

    # --- Cache key resolution ---
    if cache_scope == "session":
        cache_key = (client_id, session_id or "__DEFAULT__")
    else:
        cache_key = (client_id, "__CLIENT__")

    if not force_reload and cache_key in _HYBRID_BOT_CACHE:
        return _HYBRID_BOT_CACHE[cache_key]

    # --- Load FAISS index using the full path directly ---
    vectorstore_path = Path(client_id).expanduser().resolve()

    if not vectorstore_path.exists():
        raise FileNotFoundError(f"❌ Vectorstore not found at: {vectorstore_path}")


    # --- Load prompt ---
    settings=get_settings()

    repo_root = Path(__file__).resolve().parents[3]
    prompts_path = repo_root / "prompts"
    prompt_name = prompt_name or get_settings().chat_prompt
    print(f"🧠 Loading prompt '{prompt_name}' from {prompts_path}")
    prompt_loader = PromptLoader(str(prompts_path), prompt_name=prompt_name)
    prompt_bot = PromptBasedChatbot(prompt_loader, prompt_name=prompt_name)

    # --- Model configuration ---
    model_name = settings.model_name
    temperature = settings.model_temperature
    model_final_k=settings.model_final_k

    # --- Dynamic bot logic instantiation ---
    bot_logic = settings.bot_logic
    if not bot_logic:
        raise ValueError("❌ BOT_LOGIC not defined in .env or settings.")
    module_path, class_name = bot_logic.split(",")
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name)
    print(f"✅ Loaded bot logic: {class_name} from {module_path}")

    bot = cls(
        vectorstore_path,
        prompt_bot=prompt_bot,
        retrieval_score_threshold=get_settings().retrieval_score_threshold,
        model_name=model_name,
        temperature=temperature,
        top_k=model_final_k,
    )

    # --- Cache instance ---
    _HYBRID_BOT_CACHE[cache_key] = bot
    print(f"✅ Hybrid bot ready for {client_id} (cached under {cache_scope})")

    return bot
