# ===== reranked_rag_bot.py =====
# All comments MUST be in English.

import uuid
from datetime import datetime
from langchain.schema import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.retrievers import BM25Retriever

from langchain_core.prompts import (
    SystemMessagePromptTemplate,
    HumanMessagePromptTemplate,
    ChatPromptTemplate,
)

from langchain_core.runnables import (
    RunnablePassthrough,
    RunnableWithMessageHistory, RunnableLambda
)

from langchain_core.chat_history import InMemoryChatMessageHistory

from common.util.loader.faiss_loader import FaissVectorstoreLoader
from common.util.logger.logger import SimpleLogger
from logic.pipeline.retrieval.util.retrieval.stages.query_classifier import QueryClassifier
from logic.pipeline.retrieval.util.retrieval.stages.weighted_fusion import perform_weighted_fusion
from logic.pipeline.retrieval.util.retrieval.stages.query_rewriting import QueryRewriter
from logic.pipeline.retrieval.util.retrieval.stages.query_expansion import QueryExpander
from logic.pipeline.retrieval.util.retrieval.stages.cross_encoder_reranker import CrossEncoderReranker
from logic.pipeline.retrieval.util.retrieval.stages.salient_span_indexer import SalientSpanIndexer

# === GLOBAL MODULE SWITCHES ===
REWRITE_ON = True
EXPAND_ON = True
SSI_ON = False



class RerankedRagBot:
    """
    Hybrid Retrieval + Cross-Encoder Reranking bot.
    Now fully dynamic: each query builds its own pipeline.
    Clean sequential stages. No lambdas.
    """

    # ==========================================================
    # INIT
    # ==========================================================
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


        self.logger = logger if logger is not None else SimpleLogger()

        # --- Load system prompt provided by PromptBasedChatbot ---
        if prompt_bot:
            self.system_prompt = prompt_bot.system_prompt or ""
        else:
            self.system_prompt = system_prompt or ""

        self.top_k_faiss = top_k_faiss
        self.top_k_bm25 = top_k_bm25
        self.top_k_fusion = kwargs.get("top_k_fusion", 10)

        # ===== Modules =====
        self.rewriter = QueryRewriter(logger=self.logger)
        self.expander = QueryExpander(logger=self.logger)
        self.reranker = CrossEncoderReranker(top_k=top_k, logger_ref=self.logger)
        self.ssi = SalientSpanIndexer(top_k=top_k, logger_ref=self.logger)

        # ===== Query classifier =====
        self.classifier = QueryClassifier(logger=self.logger)

        self.chat_store = {}

        # ===== Load FAISS =====
        try:
            self._log("init_start", {"vector_path": vector_store_path})
            vectordb, meta = FaissVectorstoreLoader.load_faiss_rerankers(vector_store_path)
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

        # ===== FAISS retriever =====
        try:
            self.faiss_retriever = self.vectordb.as_retriever(
                search_kwargs={"k": self.top_k_faiss}
            )

        except Exception as ex:
            self._log("fatal_faiss_retriever_error", {"exception": str(ex)})
            raise

        # ===== BM25 retriever =====
        try:
            self.bm25_retriever = BM25Retriever.from_texts(
                texts=self.text_raw,
                metadatas=self.docs_raw
            )
            self.bm25_retriever.k = self.top_k_bm25
        except Exception as ex:
            self._log("fatal_bm25_error", {"exception": str(ex)})
            raise

        # ===== LLM =====
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)

        # ===== Prompt =====
        self.answer_prompt = ChatPromptTemplate.from_messages([
            SystemMessagePromptTemplate.from_template(
                self.system_prompt + "\n\nContext:\n{context}"
            ),
            HumanMessagePromptTemplate.from_template(
                "Chat history:\n{chat_history}\n\nQuestion:\n{question}"
            ),
        ])

        # DO NOT build pipeline here (dynamic!). Keep only runner wrapper.
        self._log("init_complete", {})

    # ==========================================================
    # INTENT FLAGS
    # ==========================================================
    def _intent_to_flags(self, label: str):
        """
        Maps intent → pipeline module flags.
        Global switches (REWRITE_ON, EXPAND_ON, SSI_ON) override everything.
        """

        # Base flags by intent
        if label == "broad_query":
            f = {"rewrite": True, "expand": True, "ssi": False, "rerank": True}
        elif label == "enumeration_query":
            f = {"rewrite": False, "expand": False, "ssi": False, "rerank": True}
        elif label == "specific_query":
            f = {"rewrite": False, "expand": False, "ssi": True, "rerank": True}
        elif label == "analytical_query":
            f = {"rewrite": True, "expand": True, "ssi": True, "rerank": True}
        elif label == "temporal_query":
            f = {"rewrite": True, "expand": False, "ssi": False, "rerank": True}
        else:
            f = {"rewrite": False, "expand": False, "ssi": False, "rerank": True}

        # === Global kill-switch overrides ===
        f["rewrite"] = f["rewrite"] and REWRITE_ON
        f["expand"] = f["expand"] and EXPAND_ON
        f["ssi"] = f["ssi"] and SSI_ON

        return f

    # ==========================================================
    # STAGES
    # ==========================================================
    def stage_rewrite(self, batch, flags):
        """Rewrite the input query if enabled."""
        if not flags.get("rewrite"):
            # SAFE OFF: restore clean input
            return {
                "input": batch.get("input", ""),
                "chat_history": batch.get("chat_history", [])
            }

        self._log("stage_rewrite_start", {"input": batch.get("input", "")})
        new_q = self.rewriter.rewrite(
            batch["input"],
            batch.get("chat_history", [])
        )
        batch["input"] = new_q
        self._log("stage_rewrite_done", {"rewritten": new_q})
        return batch

    def stage_expand(self, batch, flags):
        """Expand the query if enabled."""
        if not flags.get("expand"):
            return {
                "input": batch.get("input", ""),
                "chat_history": batch.get("chat_history", [])
            }

        self._log("stage_expand_start", {"input": batch.get("input", "")})
        expanded = self.expander.expand(batch["input"])
        batch["input"] = expanded
        self._log("stage_expand_done", {"expanded": expanded})
        return batch

    def stage_hybrid_search(self, batch):
        q = batch["input"]
        self._log("hybrid_start", {"query": q})

        try:
            faiss_hits = self.faiss_retriever.invoke(q)
            self._log("faiss_ok", {"hits": len(faiss_hits)})
        except Exception as e:
            self._log("faiss_error", {"error": str(e)})
            faiss_hits = []

        try:
            bm25_hits = self.bm25_retriever.invoke(q)
            self._log("bm25_ok", {"hits": len(bm25_hits)})
        except Exception as e:
            self._log("bm25_error", {"error": str(e)})
            bm25_hits = []

        try:
            fusion_docs = perform_weighted_fusion(faiss_hits, bm25_hits, top_k=self.top_k_fusion)
            self._log("fusion_ok", {"hits": len(fusion_docs)})
        except Exception as e:
            self._log("fusion_error", {"error": str(e)})
            fusion_docs = faiss_hits + bm25_hits

        batch["context"] = fusion_docs
        batch["question"] = q
        batch["chat_history"] = batch.get("chat_history", [])
        return batch

    def stage_ssi(self, batch, flags):
        """Apply Salient Span Indexer if enabled."""
        if not flags.get("ssi"):
            return {
                "input": batch.get("input", ""),
                "chat_history": batch.get("chat_history", []),
                "context": batch.get("context", []),
                "question": batch.get("question", batch.get("input", ""))
            }

        self._log("ssi_start", {"query": batch.get("question", "")})
        ctx = batch.get("context", [])
        new_ctx = self.ssi.extract(batch["question"], ctx)
        batch["context"] = new_ctx
        self._log("ssi_done", {"count": len(new_ctx)})
        return batch

    def stage_rerank(self, batch, flags):
        """Apply cross-encoder reranker if enabled."""
        if not flags.get("rerank"):
            return batch

        self._log("rerank_start", {"query": batch.get("question", "")})
        ctx = batch.get("context")
        q = batch.get("question")
        if isinstance(ctx, list) and all(isinstance(d, Document) for d in ctx):
            reranked = self.reranker.rerank(q, ctx)
            batch["context"] = reranked
            self._log("rerank_done", {"count": len(reranked)})
        return batch

    def stage_compress(self, batch):
        """Remove duplicates & merge docs into a single context string."""
        self._log("stage_compress_start", {
            "context_items": len(batch.get("context", []))
        })

        docs = batch["context"]
        normalized = []
        for d in docs:
            if isinstance(d, Document):
                normalized.append(d)
            else:
                normalized.append(Document(page_content=str(d), metadata={}))

        # Remove duplicates
        seen = set()
        unique = []
        for d in normalized:
            if d.page_content not in seen:
                seen.add(d.page_content)
                unique.append(d)

        combined = "\n\n---\n\n".join([d.page_content for d in unique])
        if not combined.strip():
            combined = "No relevant context retrieved."

        batch["context"] = combined

        self._log("stage_compress_done", {
            "unique_docs": len(unique),
            "final_length_chars": len(combined)
        })

        return batch

    def stage_llm(self, batch):
        """LLM answering stage."""
        self._log("stage_llm_start", {
            "context_preview": batch["context"][:200],
            "question": batch.get("question", "")
        })

        chain = self.answer_prompt | self.llm | StrOutputParser()
        answer = chain.invoke({
            "context": batch["context"],
            "chat_history": batch.get("chat_history", []),
            "question": batch["question"],
        })

        self._log("stage_llm_done", {
            "answer_preview": str(answer)[:200]
        })

        return answer

    # ==========================================================
    # BUILD PIPELINE
    # ==========================================================
    def _build_pipeline(self, flags):
        """
        Clean, flat, explicit pipeline builder.
        Returns a Runnable that executes the stages sequentially.
        No nested functions, no dynamic classes.
        """

        # --- Stage wrapper: keeps pipeline pure ---
        def run_pipeline(inputs):
            self._log("pipeline_start", {
                "flags": flags,
                "input": inputs.get("input", "")
            })

            batch = {
                "input": inputs.get("input", ""),
                "chat_history": inputs.get("chat_history", [])
            }

            batch = self.stage_rewrite(batch, flags)
            batch = self.stage_expand(batch, flags)
            batch = self.stage_hybrid_search(batch)
            batch = self.stage_ssi(batch, flags)
            batch = self.stage_rerank(batch, flags)
            batch = self.stage_compress(batch)
            answer = self.stage_llm(batch)

            self._log("pipeline_end", {"answer_preview": str(answer)[:200]})
            return answer

        # --- Return flat runnable ---
        return (
                RunnablePassthrough()
                | run_pipeline
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
    # HANDLE
    # ==========================================================
    def handle(self, user_query: str):
        """
        Entry point: classify intent, build pipeline, run.
        """
        import traceback

        session_id = "default"
        user_query = str(user_query).strip()

        self._log("query_received", {"query": user_query})

        try:
            # 1) classify
            label = self.classifier.classify(user_query)
            flags = self._intent_to_flags(label)

            self._log("intent", {
                "label": label,
                "flags": flags
            })

            # 2) build dynamic pipeline
            dynamic_pipeline = self._build_pipeline(flags)

            # 3) run pipeline with message history
            chain = RunnableWithMessageHistory(
                dynamic_pipeline,
                self._get_session_history,
                input_messages_key="input",
                history_messages_key="chat_history",
                store_history=self._save_session_history,
            )

            result = chain.invoke(
                {"input": user_query},
                config={"configurable": {"session_id": session_id}},
            )

            ans = str(result).strip() or "No strong evidence found in retrieved context."
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
    # LOGGING
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
