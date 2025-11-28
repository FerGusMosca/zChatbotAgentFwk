# ===== file_indexer_bot.py =====
# Fully LLM-agnostic using LLMFactory – Zero OpenAI coupling

import os
import json
import importlib
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple

from langchain.chains import ConversationalRetrievalChain
from langchain.chains.combine_documents.stuff import StuffDocumentsChain
from langchain.chains.llm import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.prompts import MessagesPlaceholder

from common.config.settings import get_settings
from common.util.app_logger import AppLogger
from common.util.cache.cache_manager import CacheManager
from common.util.loader.faiss_loader import FaissVectorstoreLoader
from logic.util.builder.llm_factory import LLMFactory  # ← NUEVO: 100% AGNÓSTICO


class FileIndexerBot:
    """
    HybridBot variant that detects references to local data files
    and injects their content into the prompt before calling the LLM.
    100% LLM-agnostic via LLMFactory.
    """

    def __init__(
        self,
        vector_store_path,
        prompt_bot,
        retrieval_score_threshold=0.4,
        model_name="gpt-4o",
        temperature=0.0,
        top_k=4,
    ):
        self.logger = AppLogger.get_logger(__name__)
        self.prompt_bot = prompt_bot

        vectordb = FaissVectorstoreLoader.load_legacy_faiss(vector_store_path)
        self.retriever = vectordb.as_retriever(search_kwargs={"k": top_k})
        self.retrieval_score_threshold = retrieval_score_threshold
        self.top_k = top_k
        self.last_metrics = {}
        self.cache = CacheManager()
        self.logger.info(f"Loading FileIndexerBot for profile: {get_settings().bot_profile}")

        # Load dynamic components
        self._load_custom_logger()
        self._intent_detection_logic()

        # ===== LLM – 100% AGNÓSTICO VIA FACTORY =====
        base_llm = LLMFactory.create(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
        ).get_client()  # ← Devuelve el ChatOpenAI real (Runnable)

        # Prompts
        answer_prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(self.prompt_bot.system_prompt + "\n{context}"),
                HumanMessagePromptTemplate.from_template("Chat history:\n{chat_history}\n\n{question}"),
            ],
            input_variables=["context", "question", "chat_history"],
        )

        qgen_prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template("[QGEN] Rephrase the user's question for retrieval.\n\nChat history:\n{chat_history}"),
                HumanMessagePromptTemplate.from_template("{question}"),
            ],
            input_variables=["chat_history", "question"],
        )

        # Memory
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
        )

        # Build conversational chain
        llm_chain = LLMChain(llm=base_llm, prompt=answer_prompt)
        combine_docs_chain = StuffDocumentsChain(llm_chain=llm_chain, document_variable_name="context")
        question_generator = LLMChain(llm=base_llm, prompt=qgen_prompt)

        self.chain = ConversationalRetrievalChain(
            retriever=self.retriever,
            combine_docs_chain=combine_docs_chain,
            question_generator=question_generator,
            memory=memory,
        )

    # ------------------- Dynamic imports -------------------
    def _load_custom_logger(self):
        custom_logger = get_settings().custom_logger
        module = importlib.import_module(custom_logger.split(",")[0])
        class_name = custom_logger.split(",")[1]
        cls = getattr(module, class_name)
        self.custom_logger = cls()

    def _intent_detection_logic(self):
        logic_cfg = get_settings().intent_detection_logic
        module = importlib.import_module(logic_cfg.split(",")[0])
        class_name = logic_cfg.split(",")[1]
        cls = getattr(module, class_name)
        self.intent_logic = cls(self.logger)

    # ------------------- File detection -------------------
    def _detect_target_file_via_rag(self, question: str) -> Optional[Path]:
        try:
            vs = getattr(self.retriever, "vectorstore", None)
            if not vs:
                self.logger.warning("[FileIndexerBot] No vectorstore attached.")
                return None

            pairs = vs.similarity_search_with_score(query=question, k=self.top_k)
            if not pairs:
                self.logger.info("[FileIndexerBot] No relevant document found.")
                return None

            self.logger.info(f"[FileIndexerBot] Evaluating {len(pairs)} candidate documents...")

            best_doc, best_score_raw = pairs[0]
            best_score = 1 / (1 + best_score_raw)

            for doc, score_raw in pairs:
                sim = 1 / (1 + score_raw)
                meta = doc.metadata
                path = meta.get("path", "N/A")
                self.logger.info(
                    f"[FileIndexerBot] Candidate → symbol={meta.get('symbol')} "
                    f"year={meta.get('year')} period={meta.get('period')} "
                    f"type={meta.get('report_type')} | score={sim:.3f} | path={path}"
                )

            if best_score < self.retrieval_score_threshold:
                self.logger.warning(
                    f"[FileIndexerBot] Best similarity {best_score:.3f} below threshold "
                    f"({self.retrieval_score_threshold}); fallback triggered."
                )
                return None

            path_meta = best_doc.metadata.get("path")
            if not path_meta:
                self.logger.warning("[FileIndexerBot] Best document has no path metadata.")
                return None

            resolved_path = Path(path_meta)
            if not resolved_path.exists():
                base = Path(get_settings().index_files_root_path)
                resolved_path = base / path_meta
            if not resolved_path.exists():
                self.logger.warning(f"[FileIndexerBot] Resolved path not found: {resolved_path}")
                return None

            self.logger.info(f"[RAG Detection] Selected file: {resolved_path} (similarity={best_score:.3f})")
            return resolved_path

        except Exception as e:
            self.logger.error(f"[FileIndexerBot] RAG detection error: {e}")
            return None

    def _read_file_content(self, path: Path) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > 8000:
                content = content[:8000] + "\n...[truncated for token safety]..."
            return content
        except Exception as e:
            self.logger.error(f"[FileIndexer] Error reading file {path}: {e}")
            return None

    # ------------------- Core handling -------------------
    def handle(self, question: str) -> str:
        if getattr(self, "intent_logic", None):
            handled, intent_answer, intent_name, flag = self.intent_logic.try_handle(question)
            if handled:
                self._log_metrics(question, "intent", intent_name, flag)
                return intent_answer

        target_file = self._detect_target_file_via_rag(question)
        if target_file:
            file_content = self._read_file_content(target_file)
            if file_content:
                self.logger.info(f"[FileIndexerBot] Using detected file: {target_file.name} ({len(file_content)} chars)")
                enriched_question = (
                    f"{question}\n\n---\nRelevant file detected:\n{target_file.name}\n\n"
                    f"File content:\n{file_content}"
                )
                self.logger.info(f"[FileIndexer] Injecting content of {target_file} into LLM prompt.")
                return self._fallback(enriched_question)

        try:
            docs, best_score = self._retrieve_context(question)
            use_fallback = not docs or (best_score is not None and best_score < self.retrieval_score_threshold)
            if use_fallback:
                return self._fallback(question)
            else:
                return self._rag(question, docs, best_score)
        except Exception as e:
            self.logger.error("file_indexer_fallback_error", extra={"error": str(e)})
            return self._fallback(question)

    def _fallback(self, user_query: str) -> str:
        try:
            result = self.prompt_bot.handle(user_query)
            return result
        except Exception as e:
            self.logger.error("fallback_error", extra={"error": str(e)})
            return f"Error al generar respuesta: {e}"

    def _rag(self, user_query: str, docs, best_score: float) -> str:
        try:
            result = self.chain.run(user_query)
            return result
        except Exception as e:
            self.logger.error("rag_error", extra={"error": str(e)})
            return f"Error al generar respuesta (RAG): {e}"

    def _retrieve_context(self, user_query: str) -> Tuple[List, Optional[float]]:
        try:
            vs = getattr(self.retriever, "vectorstore", None)
            if vs and hasattr(vs, "similarity_search_with_score"):
                pairs = vs.similarity_search_with_score(query=user_query, k=self.top_k)
                docs = [doc for doc, _ in pairs]
                if pairs:
                    best_raw = min(s for _, s in pairs)
                    best_score = 1 / (1 + best_raw)
                    return docs, best_score
            docs = self.retriever.get_relevant_documents(user_query)
            return docs, None
        except Exception as e:
            self.logger.error("retrieve_context_error", extra={"error": str(e)})
            return [], None

    def _log_metrics(self, user_query: str, mode: str, intent=None, flag=None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": user_query,
            "mode": mode,
            "intent": intent,
            "flag": flag,
        }
        self.logger.info("metric_query_handled", extra=payload)