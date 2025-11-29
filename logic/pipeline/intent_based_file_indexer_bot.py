# ===== intent_based_file_indexer_bot.py =====
# Fully agnostic to LLM provider using LLMFactory

import importlib
from datetime import datetime

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from common.util.app_logger import AppLogger
from common.util.cache.cache_manager import CacheManager
from common.config.settings import get_settings
from common.util.loader.file_content_extractor import FileContentExtractor
from common.util.loader.prompt_loader import PromptLoader
from logic.util.builder.llm_factory import LLMFactory   # ← NUEVO


class IntentBasedFileIndexerBot:
    """
    Bot that detects intent-based file lookups (no vector search).
    Uses intent detection logic to resolve exact file path and load its content.
    100% LLM-agnostic via LLMFactory.
    """

    def __init__(
            self,
            vector_store_path,
            prompt_name,
            retrieval_score_threshold=0.4,
            llm_prov : str="openai",
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
    ):
        self.logger = AppLogger.get_logger(__name__)
        self.prompt_bot =  LLMFactory.create(
                                        provider=llm_prov,
                                        model_name=model_name,
                                        temperature=temperature,
                                    )
        self.prompt_name=prompt_name
        self.model_name = model_name
        self.temperature = temperature
        self.retrieval_score_threshold = retrieval_score_threshold
        self.top_k = top_k
        self.cache = CacheManager()
        self.last_metrics = {}

        raw_prompt = PromptLoader(self.prompt_name).prompts[self.prompt_name]

        self.full_prompt = ChatPromptTemplate.from_messages([
            ("system", raw_prompt)
        ])

        settings = get_settings()
        self.logger.info(f"Loading IntentBasedFileIndexerBot for profile: {settings.bot_profile}")

        # --- Log ignored args (compat only) ---
        if vector_store_path is not None:
            self.logger.warning("[IntentBasedFileIndexerBot] Ignoring vector_store_path (not used).")
        if top_k is not None:
            self.logger.warning("[IntentBasedFileIndexerBot] Ignoring top_k (not used in this mode).")

        # --- Dynamic intent detection logic ---
        logic_cfg = settings.intent_detection_logic
        module_name, class_name = logic_cfg.split(",")
        module = importlib.import_module(module_name)
        cls = getattr(module, class_name)
        self.intent_logic = cls(self.logger)

        self.logger.info(f"IntentBasedFileIndexerBot initialized successfully (HybridBot-compatible).")

    def _stage_llm(self, batch):
        """
        LLM answering stage.
        Sends the retrieved file content (context) + user question to the LLM.
        The prompt already expects {context} and {question} exactly as written.
        """
        self.logger.info("stage_llm_start", {"question": batch["question"]})

        # Build runnable chain: prompt → LLM → raw string
        chain = (
            self.full_prompt
            | self.prompt_bot.get_client()
            | StrOutputParser()
        )

        # Inject EXACT variables the prompt expects
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
        Detects file intent → loads file → sends file content + question to LLM.
        Returns structured JSON sentiment analysis.
        """
        try:
            self.logger.info("[IntentFileIndexerBot] Detecting intent...")
            relative_path = self.intent_logic.detect(question)

            if not relative_path:
                self.logger.warning("[IntentFileIndexerBot] No intent detected.")
                return "No se detectó intención de archivo para esta consulta."

            self.logger.info(f"[IntentFileIndexerBot] Intent detected: {relative_path}")

            file_content = FileContentExtractor.get_file_content(relative_path)
            if not file_content:
                return f"Error leyendo el archivo: {relative_path}"

            # Build batch with file content as context
            batch = {
                "context": file_content,
                "question": question
            }

            self.logger.info("[IntentFileIndexerBot] Sending to LLM with file content...")
            result = self._stage_llm(batch)

            self._log_metrics(question, "intent", relative_path)
            return result

        except Exception as e:
            self.logger.error(f"[IntentFileIndexerBot] Error handling intent: {e}")
            return f"Error procesando la intención: {e}"

    # ---------------- Metrics ----------------
    def _log_metrics(self, user_query: str, mode: str, detected_path: str = None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": user_query,
            "mode": mode,
            "file_detected": detected_path,
        }
        self.logger.info("metric_query_handled", extra=payload)