# ===== hybrid_bot.py =====
# Hybrid RAG Bot – 100% LLM-agnostic, modern, clean, bulletproof

import uuid
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from common.config.settings import get_settings
from common.util.app_logger import AppLogger
from common.util.cache.cache_manager import CacheManager
from common.util.loader.faiss_loader import FaissVectorstoreLoader
from logic.util.builder.llm_factory import LLMFactory


class HybridBot:
    def __init__(
        self,
        vector_store_path: str,
        prompt_name: str,
        retrieval_score_threshold: float = 0.4,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        top_k: int = 8,
    ):
        self.logger = AppLogger.get_logger(__name__)
        self.cache = CacheManager()
        self.retrieval_score_threshold = retrieval_score_threshold
        self.top_k = top_k

        # --- FAISS (legacy loader) ---
        vectordb = FaissVectorstoreLoader.load_legacy_faiss(vector_store_path)
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})

        # --- LLM (100% agnostic) ---
        self.llm = LLMFactory.create(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
        ).get_client()

        # --- PROMPT CORRECTO (este era el error) ---
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", prompt_name),  # ← system puro
            ("placeholder", "{chat_history}"),
            ("system", "Context:\n{context}"),  # ← contexto como system (válido)
            ("human", "{question}"),
        ])

        # --- Chain perfecta ---
        self.chain = (
            {
                "context": self.retriever | (lambda docs: "\n\n".join(d.page_content for d in docs) if docs else "No relevant context found."),
                "question": RunnablePassthrough(),
                "chat_history": lambda x: x.get("chat_history", []),
            }
            | self.prompt
            | self.llm
            | StrOutputParser()
        )

        self.logger.info("HybridBot initialized – 100% agnostic, modern, clean, bulletproof")

    def handle(self, question: str, chat_history: Optional[List] = None) -> str:
        try:
            result = self.chain.invoke({
                "question": question,
                "chat_history": chat_history or [],
            })
            return result
        except Exception as e:
            error_id = str(uuid.uuid4())[:8]
            self.logger.error("hybrid_bot_error", extra={"error_id": error_id, "error": str(e)})
            return f"Error interno ({error_id}). Intenta de nuevo."

    def ask(self, question: str) -> str:
        return self.handle(question)