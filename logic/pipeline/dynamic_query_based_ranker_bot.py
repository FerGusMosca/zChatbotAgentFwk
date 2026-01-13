# ===== dynamic_query_based_ranker_bot.py =====
# Dynamic ranking-based bot.
# Fully LLM-agnostic via LLMFactory.
# Uses precomputed ranking folders and query-time logic.

import importlib
from datetime import datetime

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from common.util.app_logger import AppLogger
from common.util.cache.cache_manager import CacheManager
from common.config.settings import get_settings
from common.util.loader.file_content_extractor import FileContentExtractor
from common.util.loader.inner_file_locator import InnerFileLocator
from common.util.loader.prompt_loader import PromptLoader
from logic.util.builder.llm_factory import LLMFactory
from logic.util.loader.dynamic_query import DynamicQuery


class DynamicQueryBasedRankerBot:
    """
    Bot that processes user queries against ranking-based document folders.
    No vector search.
    Ranking selection + file resolution is handled by query logic.
    Fully LLM-agnostic via LLMFactory.
    """

    def __init__(
        self,
        vector_store_path,
        prompt_name,
        retrieval_score_threshold=0.4,
        llm_prov: str = "openai",
        model_name: str = "gpt-4o",
        temperature: float = 0.0,
        top_k: int = 4,
    ):
        self.logger = AppLogger.get_logger(__name__)
        self.cache = CacheManager()
        self.last_metrics = {}

        self.rank_root_path = None
        self.prompt_name = prompt_name
        self.model_name = model_name
        self.temperature = temperature
        self.top_k = top_k

        # --- LLM initialization (provider-agnostic) ---
        self.prompt_bot = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )

        # --- Load system prompt ---
        raw_prompt = PromptLoader(self.prompt_name, self.logger).prompts[self.prompt_name]
        self.full_prompt = ChatPromptTemplate.from_messages([
            ("system", raw_prompt)
        ])

        settings = get_settings()
        self.logger.info(
            f"Loading DynamicQueryBasedRankerBot for profile: {settings.bot_profile}"
        )

        # --- Dynamic query-based ranking logic ---
        self.query_logic = None #NO intents for this class
        self.logger.info("DynamicQueryBasedRankerBot initialized successfully.")

    # ---------------- LLM stage ----------------
    def _stage_llm(self, batch: dict) -> str:
        """
        Final LLM answering stage.
        Receives ranked context + user query.
        """
        self.logger.info("stage_llm_start", {"question": batch["question"]})

        chain = (
            self.full_prompt
            | self.prompt_bot.get_client()
            | StrOutputParser()
        )

        answer = chain.invoke({
            "context": batch["context"],
            "question": batch["question"]
        })

        self.logger.info("stage_llm_done", {"answer_preview": answer[:200]})
        return answer

    # ---------------- Core handler ----------------
    def handle(self, question: str) -> str:
        """
        Main entry point.
        Resolves ranked files → loads content → sends to LLM.
        """
        try:
            self.logger.info("[DynamicRankerBot] Resolving ranked files...")

            self.logger.info("[QUERY_ANN] raw_query_received", {"query": question})

            dto = DynamicQuery.parse(question)

            if dto.is_dynamic:
                self.logger.info(f"[QUERY_ANN] dynamic_query_found!: folder:{dto.chunks_folder}...", {})
                self.logger.info("[QUERY_ANN] query_processed", {"query": dto.query})
                question = dto.query
                self.rank_root_path = dto.chunks_folder
            else:
                self.logger.info("[QUERY_ANN] simple_query_found! --> using default folder", {})
                self.logger.info("[QUERY_ANN] query_processed", {"query": question})
                return "Query received must be in dynamic query format: query and root path"


            referenced_files=InnerFileLocator.list_files(self.rank_root_path)

            contexts=[]
            for ref_file in referenced_files:
                contexts.append( FileContentExtractor.get_file_content(ref_file))


            self.logger.info(
                f"[DynamicRankerBot] Ranked files resolved: size {len(contexts)}"
            )

            if not contexts:
                return "Failed to load ranked document contents."

            batch = {
                "context": "\n\n".join(contexts),
                "question": question
            }

            self.logger.info("[DynamicRankerBot] Sending ranked context to LLM...")
            result = self._stage_llm(batch)

            self._log_metrics(question, "ranking", contexts)
            return result

        except Exception as e:
            self.logger.error(f"[DynamicRankerBot] Error handling query: {e}")
            return f"Error processing ranked query: {e}"

    # ---------------- Metrics ----------------
    def _log_metrics(self, user_query: str, mode: str, ranked_paths: list = None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": user_query,
            "mode": mode,
            "ranked_files": ranked_paths,
        }
        self.logger.info("metric_query_handled", extra=payload)
