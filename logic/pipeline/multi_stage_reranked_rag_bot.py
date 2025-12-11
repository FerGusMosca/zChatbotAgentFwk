# ===== reranked_rag_bot.py =====
# All comments MUST be in English.
import json
import uuid
from datetime import datetime
import traceback
from langchain.schema import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_community.retrievers import BM25Retriever

from common.util.loader.prompt_loader import PromptLoader


from logic.pipeline.reranked_rag_bot import RerankedRagBot
from logic.pipeline.retrieval.util.retrieval.stages.retrievers.multi_stage_FAISS_searcher import MultiStageFaissSearcher
from logic.pipeline.retrieval.util.retrieval.stages.common.context_compression import ContextCompressor
from logic.pipeline.retrieval.util.retrieval.stages.common.dedup_eliminator import DedupEliminator
from logic.pipeline.retrieval.util.retrieval.stages.retrievers.multi_stage_bm25_searcher import MultiStageBM25Searcher
from logic.pipeline.retrieval.util.retrieval.util.chunks_debugger import ChunksDebugger
from logic.util.builder.llm_factory import LLMFactory
from langchain_core.prompts import (
    ChatPromptTemplate,
)

from langchain_core.runnables import (
    RunnablePassthrough,
    RunnableWithMessageHistory
)

from langchain_core.chat_history import InMemoryChatMessageHistory

from common.config.settings import get_settings
from common.enum.intents import Intent
from common.util.logger.logger import SimpleLogger
from logic.pipeline.retrieval.util.prompt_extractor.prompt_parser import PromptSectionExtractor
from logic.pipeline.retrieval.util.retrieval.stages.common.query_classifier import QueryClassifier
from logic.pipeline.retrieval.util.retrieval.stages.common.weighted_fusion import  WeightedFusion
from logic.pipeline.retrieval.util.retrieval.stages.common.query_rewriting import QueryRewriter
from logic.pipeline.retrieval.util.retrieval.stages.common.query_expansion import QueryExpander
from logic.pipeline.retrieval.util.retrieval.stages.common.cross_encoder_reranker import CrossEncoderReranker
from logic.pipeline.retrieval.util.retrieval.stages.common.salient_span_indexer import SalientSpanIndexer

# === GLOBAL MODULE SWITCHES ===
REWRITE_ON = True
EXPAND_ON = True
SSI_ON = False
DEBUG_MODE=True


class MultiStageRerankedRagBot(RerankedRagBot):
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


        self.logger = logger if logger is not None else SimpleLogger(loki_url=get_settings().loki_url,
                                                                     grafana_on= get_settings().grafana_on)

        # --- Inner Settings ---
        self.dedup_settings_path= get_settings().dedup_settings
        self.compression_settings_path=get_settings().compression_settings
        self.ssi_settings=get_settings().ssi_settings
        self.reranker_settings=get_settings().rerankers_settings
        self.faiss_config_file = get_settings().faiss_config_file
        self.index_files_root_path=get_settings().index_files_root_path
        self.bot_profile=get_settings().bot_profile

        #-- logs
        self.dump_on_logs=get_settings().dump_on_logs
        self.dump_log_folder=get_settings().dump_log_folder

        self.rerankers_cfg=self._load_config(self.reranker_settings)
        self.faiss_cfg=self._load_config(self.faiss_config_file)

        # --- Load system prompt provided by PromptBasedChatbot ---
        self.system_prompt = prompt_name
        self.top_k_faiss = int(self.rerankers_cfg["top_k_faiss"])
        self.top_k_bm25 = int(self.rerankers_cfg["top_k_bm25"])
        self.top_k_fusion = int(self.rerankers_cfg["top_k_fusion"])

        # ===== Modules =====
        full_prompt=PromptLoader(self.system_prompt,self.logger).prompts[prompt_name]

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


        # ===== Context Compressor =====
        try:
            self.context_compressor = ContextCompressor(self.compression_settings_path,self.logger)
        except Exception as ex:
            self._log("fatal_context_compressor_error", {"exception": str(ex)})
            raise

        # ===== FAISS retriever =====
        self._init_FAISS_retriever()

        # ===== BM25 retriever =====
        self._init_BM25_retriever()

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

    def _init_FAISS_retriever(self):
        # ===== FAISS retriever =====
        try:
            self.ms_FAISS_searcher = MultiStageFaissSearcher(self.faiss_cfg, self.rerankers_cfg,
                                                             self.index_files_root_path, self.bot_profile,
                                                             self.top_k_faiss, self.logger,
                                                             self.dump_on_logs,self.dump_log_folder)

        except Exception as ex:
            self._log("fatal_ms_FAISS_searcher_error", {"exception": str(ex)})
            raise

    def _init_BM25_retriever(self):
        # ===== BM25 retriever =====
        try:
            self.bm25_searcher = MultiStageBM25Searcher(
                docs_path=self.index_files_root_path,
                bot_profile=self.bot_profile,
                top_k_bm25=self.top_k_bm25,
                std_out_logger =self.logger,
                dump_on_logs=self.dump_on_logs,
                dump_log_folder = self.dump_log_folder
            )

            # Successful initialization log
            self._log("init_ms_BM25_searcher_ok", {
                "bot_profile": self.bot_profile,
                "top_k_bm25": self.top_k_bm25,
                "index_root": self.index_files_root_path,
                "status": "initialized"
            })

        except Exception as ex:
            self._log("fatal_ms_BM25_searcher_error", {"exception": str(ex)})
            raise

    def stage_hybrid_search(self, batch):
        q = batch["input"]
        self._log("hybrid_start", {"query": q})

        try:
            faiss_hits=self.ms_FAISS_searcher.run_faiss_search(q)
            #faiss_hits=[]
            self._log("faiss_ok", {"hits": len(faiss_hits)})
        except Exception as e:
            self._log("faiss_error", {"error": str(e)})
            faiss_hits = []


        try:
            bm25_hits = self.bm25_searcher.run_bm25_search(q)
            self._log("bm25_ok", {"hits": len(bm25_hits)})
        except Exception as e:
            self._log("bm25_error", {"error": str(e)})
            bm25_hits = []

        # ===== Hybrid Fusion (FAISS + BM25) =====
        try:
            self.logger.info(
                f"[FUSION] starting | faiss={len(faiss_hits)} | bm25={len(bm25_hits)}"
            )

            weight_fusion = WeightedFusion(self.logger)

            fusion_docs = weight_fusion.perform_weighted_fusion(
                faiss_docs=faiss_hits,
                bm25_docs=bm25_hits,
                fusion_top_faiss=self.rerankers_cfg["fusion_top_faiss"],
                fusion_top_bm25=self.rerankers_cfg["fusion_top_bm25"]
            )

            self._log("fusion_ok", {"hits": len(fusion_docs)})

        except Exception as e:
            self._log("fusion_error", {"error": str(e)})
            fusion_docs = []


        batch["context"] = fusion_docs
        batch["question"] = q
        batch["chat_history"] = batch.get("chat_history", [])

        if DEBUG_MODE:
            pass
            #ChunksDebugger._log_prefetch_documents(faiss_hits,"FAISS", self.logger)
            #ChunksDebugger._log_prefetch_documents(bm25_hits, "BM25", self.logger)
            #ChunksDebugger._log_retrieved_document(batch["context"],"FUSION",self.logger)


        return batch


