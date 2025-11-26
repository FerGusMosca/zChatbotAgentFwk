# ===== reranked_rag_bot.py =====
# All comments MUST be in English.

import uuid
from datetime import datetime
from langchain.schema import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI
from langchain_community.retrievers import BM25Retriever

from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
)

from langchain_core.runnables import (
    RunnablePassthrough,
    RunnableWithMessageHistory, )

from langchain_core.chat_history import InMemoryChatMessageHistory

from common.util.loader.faiss_loader import FaissVectorstoreLoader
from logic.pipeline.retrieval.util.retrieval.stages.weighted_fusion import perform_weighted_fusion
from logic.pipeline.retrieval.util.retrieval.stages.query_rewriting import QueryRewriter
from logic.pipeline.retrieval.util.retrieval.stages.query_expansion import QueryExpander
from logic.pipeline.retrieval.util.retrieval.stages.cross_encoder_reranker import CrossEncoderReranker
from logic.pipeline.retrieval.util.retrieval.stages.salient_span_indexer import SalientSpanIndexer

class RerankedRagBot:
    """
    Hybrid Retrieval + (future) Cross-Encoder Reranking bot.
    Fully hardened with logging, exception safety, and context compression.
    """

    def __init__(
            self,
            vector_store_path: str,
            prompt_bot=None,
            retrieval_score_threshold=None,
            system_prompt: str = "",
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
            top_k_faiss: int = 8,
            top_k_bm25: int = 12,
            logger=None,
            **kwargs
    ):
        self.logger = logger

        # --- Load system prompt from PromptBasedChatbot ---
        if prompt_bot:
            self.system_prompt = prompt_bot.system_prompt or ""
        else:
            self.system_prompt = system_prompt or ""


        self.top_k_faiss = top_k_faiss
        self.top_k_bm25 = top_k_bm25
        self.top_k_fusion = kwargs.get("top_k_fusion", 10)
        self.rewriter = QueryRewriter(logger=logger)
        self.expander = QueryExpander(logger=logger)
        # ===== Cross-Encoder Reranker =====
        self.reranker = CrossEncoderReranker(
            top_k=top_k,
            logger_ref=logger
        )

        # ===== Salient Span Indexer =====
        self.ssi = SalientSpanIndexer(
            top_k=top_k,
            logger_ref=logger
        )

        self.chat_store = {}

        try:
            self._log("init_start", {"vector_path": vector_store_path})

            vectordb, meta = FaissVectorstoreLoader.load_advanced_faiss(vector_store_path)
            if vectordb is None:
                raise RuntimeError("Failed to load FAISS vectorstore.")

            self.vectordb = vectordb
            self.docs_raw = meta["metadata"]
            self.text_raw = meta["chunks"]

            self._log("faiss_loaded", {
                "chunks": len(self.text_raw),
                "metadata": len(self.docs_raw),
                "k_faiss": self.top_k_faiss,
            })

        except Exception as ex:
            self._log("fatal_init_error", {"exception": str(ex)})
            raise

        # === Hybrid Stage: FAISS retriever ===
        try:
            self.faiss_retriever = vectordb.as_retriever(
                search_kwargs={"k": self.top_k_faiss}
            )
        except Exception as ex:
            self._log("fatal_faiss_retriever_error", {"exception": str(ex)})
            raise

        # === Hybrid Stage: BM25 retriever ===
        try:
            self.bm25_retriever = BM25Retriever.from_texts(
                texts=self.text_raw,
                metadatas=self.docs_raw
            )
            self.bm25_retriever.k = self.top_k_bm25
        except Exception as ex:
            self._log("fatal_bm25_error", {"exception": str(ex)})
            raise

        # === LLM ===
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)

        # === Prompt ===
        self.answer_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                self.system_prompt + "\n\nContext:\n{context}"
            ),
            HumanMessagePromptTemplate.from_template(
                "Chat history:\n{chat_history}\n\nQuestion:\n{question}"
            ),
        ])

        # === Build chain ===
        self.chain = RunnableWithMessageHistory(
            self._build_pipeline(),
            self._get_session_history,
            input_messages_key="input",
            history_messages_key="chat_history",
            #output_messages_key="answer",
            store_history=self._save_session_history,
        )

    # ==========================================================
    # PIPELINE
    # ==========================================================
    def _build_pipeline(self):
        """FAISS + BM25 → Fusion → Compress → LLM (clean baseline)."""

        def hybrid_search(inputs):
            q = str(inputs["input"]).strip()
            chat_hist = inputs.get("chat_history", [])

            self._log("hybrid_start", {"query": q})

            # ===== FAISS =====
            try:
                faiss_hits = self.faiss_retriever.invoke(q)
            except Exception as ex:
                self._log("faiss_search_error", {"exception": str(ex)})
                faiss_hits = []

            # ===== BM25 =====
            try:
                bm25_hits = self.bm25_retriever.invoke(q)
            except Exception as ex:
                self._log("bm25_search_error", {"exception": str(ex)})
                bm25_hits = []

            # Normalizar BM25 resultados → convertir dicts o strings en Document
            norm_bm25 = []
            for x in bm25_hits:
                if isinstance(x, Document):
                    norm_bm25.append(x)
                elif isinstance(x, str):
                    norm_bm25.append(Document(page_content=x, metadata={}))
                elif isinstance(x, dict):
                    norm_bm25.append(
                        Document(page_content=x.get("text", ""), metadata=x.get("metadata", {}))
                    )

            # ===== FUSION =====
            try:
                raw_fusion = perform_weighted_fusion(
                    query=q,
                    faiss_docs=faiss_hits,
                    bm25_docs=norm_bm25,
                    top_k=self.top_k_fusion
                )

                fusion_docs = [
                    Document(
                        page_content=doc.text,
                        metadata={
                            **doc.metadata,
                            "score_faiss": getattr(doc, "score_faiss", None),
                            "score_bm25": getattr(doc, "score_bm25", None)
                        }
                    )
                    for doc in raw_fusion
                ]

            except Exception as ex:
                self._log("fusion_error", {"exception": str(ex)})
                fusion_docs = faiss_hits + norm_bm25  # fallback consistente

            self._log("hybrid_done", {
                "faiss_count": len(faiss_hits),
                "bm25_count": len(norm_bm25),
                "fusion_count": len(fusion_docs),
            })

            return {
                "context": fusion_docs,
                "question": q,
                "chat_history": chat_hist
            }

        def compress_context(batch):
            docs = batch["context"]

            # Asegurar lista de Documents
            normalized = []
            for d in docs:
                if isinstance(d, Document):
                    normalized.append(d)
                else:
                    normalized.append(Document(page_content=str(d), metadata={}))

            # Remove dups
            seen = set()
            unique = []
            for d in normalized:
                if d.page_content not in seen:
                    seen.add(d.page_content)
                    unique.append(d)

            # Combine
            combined = "\n\n---\n\n".join([d.page_content for d in unique])
            if not combined.strip():
                combined = "No relevant context retrieved."

            batch["context"] = combined
            return batch

        return (
                RunnablePassthrough()
                | hybrid_search
                | compress_context
                | self.answer_prompt
                | self.llm
                | StrOutputParser()
        )

    # ==========================================================
    # MEMORY
    # ==========================================================
    def _get_session_history(self, session_id: str):
        return self.chat_store.setdefault(session_id, InMemoryChatMessageHistory())

    def _save_session_history(self, session_id: str, inputs, outputs):
        try:
            hist = self.chat_store.setdefault(session_id, InMemoryChatMessageHistory())
            user_msg = inputs.get("input", "")
            ai_msg = str(outputs)
            hist.add_user_message(user_msg)
            hist.add_ai_message(ai_msg)

            self._log("history_update", {
                "session_id": session_id,
                "user": user_msg[:120],
                "ai": ai_msg[:120],
                "len": len(hist.messages),
            })
        except Exception as ex:
            self._log("history_error", {"exception": str(ex)})

    # ==========================================================
    # RUN
    # ==========================================================
    def handle(self, user_query: str):
        import traceback

        session_id = "default"
        user_query = str(user_query).strip()

        self._log("query_received", {"query": user_query})

        try:
            result = self.chain.invoke(
                {"input": user_query},
                config={"configurable": {"session_id": session_id}},
            )

            ans = str(result).strip()
            if not ans:
                ans = "No strong evidence found in retrieved context."

            self._log("query_answered", {"answer": ans[:200]})
            return ans

        except Exception as ex:
            traceback.print_exc()
            err_id = str(uuid.uuid4())[:8]

            self._log("fatal_query_error", {
                "error_id": err_id,
                "exception": str(ex)
            })

            return f"RerankedRAG error ({err_id})."

    # ==========================================================
    # LOG
    # ==========================================================
    def _log(self, event: str, payload: dict):
        if not self.logger:
            return
        try:
            self.logger.info(
                f"[RERANKED-RAG] {event}",
                extra={"timestamp": datetime.utcnow().isoformat(), **payload}
            )
        except:
            pass
