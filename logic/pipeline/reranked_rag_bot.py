# ===== reranked_rag_bot.py =====
# All comments MUST be in English.
import json
from pathlib import Path
import uuid
from datetime import datetime
import numpy as np
import traceback
from langchain.schema import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_community.retrievers import BM25Retriever

from common.util.loader.prompt_loader import PromptLoader
from logic.pipeline.retrieval.util.retrieval.stages.context_compression import ContextCompressor
from logic.pipeline.retrieval.util.retrieval.stages.dedup_eliminator import DedupEliminator
from logic.util.builder.llm_factory import LLMFactory
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

from common.config.settings import get_settings
from common.enum.intents import Intent
from common.util.loader.faiss_loader import FaissVectorstoreLoader
from common.util.logger.logger import SimpleLogger
from logic.pipeline.retrieval.util.prompt_extractor.prompt_parser import PromptSectionExtractor
from logic.pipeline.retrieval.util.retrieval.stages.query_classifier import QueryClassifier
from logic.pipeline.retrieval.util.retrieval.stages.weighted_fusion import  WeightedFusion
from logic.pipeline.retrieval.util.retrieval.stages.query_rewriting import QueryRewriter
from logic.pipeline.retrieval.util.retrieval.stages.query_expansion import QueryExpander
from logic.pipeline.retrieval.util.retrieval.stages.cross_encoder_reranker import CrossEncoderReranker
from logic.pipeline.retrieval.util.retrieval.stages.salient_span_indexer import SalientSpanIndexer

# === GLOBAL MODULE SWITCHES ===
REWRITE_ON = True
EXPAND_ON = True
SSI_ON = False
DEBUG_MODE=True


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
        prompt_name,
        retrieval_score_threshold=None,
        llm_prov: str="openai",
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        top_k: int = 4,
        logger=None,
        **kwargs
    ):


        self.logger = logger if logger is not None else SimpleLogger()

        # --- Inner Settings ---
        self.dedup_settings_path= get_settings().dedup_settings
        self.compression_settings_path=get_settings().compression_settings
        self.ssi_settings=get_settings().ssi_settings
        self.reranker_settings=get_settings().rerankers_settings

        self.rerankers_cfg=self._load_config(self.reranker_settings)


        # --- Load system prompt provided by PromptBasedChatbot ---
        self.system_prompt = prompt_name
        self.top_k_faiss = int(self.rerankers_cfg["top_k_faiss"])
        self.top_k_bm25 = int(self.rerankers_cfg["top_k_bm25"])
        self.top_k_fusion = int(self.rerankers_cfg["top_k_fusion"])



        # ===== Modules =====
        full_prompt=PromptLoader(self.system_prompt).prompts[prompt_name]

        self.rewriter = QueryRewriter(
            full_prompt=full_prompt,
            logger=self.logger,
            llm_prov=llm_prov,
            model_name=model_name,
            temperature=temperature
        )
        self.expander = QueryExpander(
            full_prompt=full_prompt,
            logger=self.logger,
            llm_prov=llm_prov,
            model_name=model_name,
            temperature=temperature
        )

        self.reranker = CrossEncoderReranker(top_k=top_k, logger_ref=self.logger)
        self.deduper = DedupEliminator(self.logger,self.dedup_settings_path)

        self.ssi = SalientSpanIndexer(self.ssi_settings,self.logger)

        # ===== Query classifier =====
        self.classifier = QueryClassifier(
            full_prompt=full_prompt,
            logger=self.logger,
            use_llm_fallback=True,
            llm_prov=llm_prov,
            model_name=model_name,
            temperature=temperature
        )

        self.chat_store = {}

        # ===== Load FAISS =====
        try:
            self._log("init_start", {"vector_path": vector_store_path})

            self.faiss_config_file=get_settings().faiss_config_file
            vectordb, meta,embed,norm_on_search = FaissVectorstoreLoader.load_faiss_rerankers(vector_store_path,config_path=self.faiss_config_file)

            if vectordb is None:
                raise RuntimeError("Failed to load FAISS vectorstore.")

            self.vectordb = vectordb
            self.meta=meta
            self.embed=embed
            self.norm_on_search=norm_on_search
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

        # ===== Context Compressor =====
        try:
            self.context_compressor = ContextCompressor(self.compression_settings_path,self.logger)
        except Exception as ex:
            self._log("fatal_context_compressor_error", {"exception": str(ex)})
            raise

        # ===== BM25 retriever =====
        try:
            self.bm25_retriever = BM25Retriever.from_documents([Document(page_content=t) for t in self.text_raw])
            self.bm25_retriever.k = self.top_k_bm25

        except Exception as ex:
            self._log("fatal_bm25_error", {"exception": str(ex)})
            raise

        # ===== LLM =====
        self.llm = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )

        # ===== Prompt =====
        self.answer_prompt = ChatPromptTemplate.from_template(PromptSectionExtractor.extract(full_prompt, "MAIN_LLM"))

        # DO NOT build pipeline here (dynamic!). Keep only runner wrapper.
        self._log("init_complete", {})

    def _load_config(self,rerankers_config_path):
        # Load and validate JSON
        try:
            with open(rerankers_config_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
                return  raw_config
        except FileNotFoundError:
            raise FileNotFoundError(f"SSI config file not found: {rerankers_config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in SSI config: {e}")



    # ==========================================================
    # INTENT FLAGS
    # ==========================================================
    def _intent_to_flags(self, intent: Intent) -> dict:
        flags = {
            "rewrite": True,
            "expand": True,
            "ssi": False,
            "rerank": True
        }

        if intent == Intent.SPECIFIC:
            flags["ssi"] = True
            flags["expand"] = False
        elif intent == Intent.TEMPORAL:
            flags["expand"] = False
        elif intent == Intent.ENUMERATION:
            flags["rewrite"] = False
            flags["expand"] = False

        # Global overrides
        flags["rewrite"] &= REWRITE_ON
        flags["expand"] &= EXPAND_ON
        flags["ssi"] &= SSI_ON

        return flags

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
            qv = np.array(self.embed.embed_query(q), dtype="float32")
            if self.norm_on_search:
                qv /= np.linalg.norm(qv)

            idxs, scores = self.vectordb.index.search(qv.reshape(1, -1), self.top_k_faiss)

            id_map = {str(k): v for k, v in self.meta["index_to_docstore_id"].items()}
            faiss_hits = [self.vectordb.docstore._dict[str(id_map[str(int(fid))])] for fid in idxs[0]]

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
            weight_fusion=WeightedFusion(self.logger)
            fusion_docs = weight_fusion.perform_weighted_fusion(faiss_hits, bm25_hits, top_k=self.top_k_fusion)
            self._log("fusion_ok", {"hits": len(fusion_docs)})
        except Exception as e:
            self._log("fusion_error", {"error": str(e)})
            fusion_docs = faiss_hits + bm25_hits

        batch["context"] = fusion_docs
        batch["question"] = q
        batch["chat_history"] = batch.get("chat_history", [])

        if DEBUG_MODE:
            self.logger.debug("----CHUNKS RETURNED ----")
            for i, doc in enumerate(batch["context"], start=1):
                self.logger.debug(f"CHUNK[{i:02d}]: {doc.to_log_string()}")

        return batch

    def stage_ssi(self, batch: dict, flags: dict) -> dict:
        """Apply SSI only if flagged – minimal, safe, production-ready"""
        if not flags.get("ssi", False):
            return batch

        docs = batch.get("context", [])
        query = batch.get("question") or batch.get("input", "")
        intent = flags.get("intent", "")

        batch["context"] = self.ssi.extract(docs=docs, query=query, intent=intent)
        return batch

    def stage_dedup(self, batch,label):
        ctx = batch.get("context", [])
        result = self.deduper.run(ctx,label)
        batch["context"] = result.docs
        self._log("stage_dedup", {"removed": result.removed})
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

    def stage_context_compression(self, batch):
        # keep original objects → compressor extrae texto solo adentro
        docs = batch.get("context", [])
        batch["context"] = self.context_compressor.compress(docs, batch["question"])
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
        self._log("stage_llm_start", {"question": batch["question"]})
        chain = self.answer_prompt | self.llm.get_client() | StrOutputParser()
        answer = chain.invoke({
            "context": batch["context"],
            "query": batch["question"]  # <--- query, no question
        })
        self._log("stage_llm_done", {"answer_preview": answer[:200]})
        return answer

    def _pipeline_processing_error(self,batch,ex):
        error_id = str(uuid.uuid4())[:8]
        tb = traceback.format_exc()

        self._log("pipeline_fatal_error", {
            "error_id": error_id,
            "exception": str(ex),
            "trace": tb,
            "batch_snapshot": {
                "input": batch.get("input", "")[:200] if batch else None,
                "question": batch.get("question", "")[:200] if batch and "question" in batch else None,
                "has_context": "context" in batch,
                "context_items": len(batch.get("context", [])) if batch and "context" in batch else None,
                "context_types": [type(x).__name__ for x in batch.get("context", [])]
                if batch and "context" in batch else None
            }
        })

        return f"[Pipeline Error {error_id}] Internal processing failure. "

    # ==========================================================
    # BUILD PIPELINE
    # ==========================================================
    def _build_pipeline(self, flags,label):
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

            try:
                batch = self.stage_rewrite(batch, flags)
                batch = self.stage_expand(batch, flags)
                batch = self.stage_hybrid_search(batch)
                batch = self.stage_dedup(batch,label)
                batch = self.stage_ssi(batch, flags)
                batch = self.stage_rerank(batch, flags)
                batch = self.stage_context_compression(batch)
                batch = self.stage_compress(batch)
                answer = self.stage_llm(batch)

                self._log("pipeline_end", {"answer_preview": str(answer)[:200]})
                return answer
            except Exception as ex:
                return  self._pipeline_processing_error(batch,ex)

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
            dynamic_pipeline = self._build_pipeline(flags,label)

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
