import importlib
from datetime import datetime
from langchain_openai import ChatOpenAI
from common.util.app_logger import AppLogger
from common.util.cache.cache_manager import CacheManager
from common.config.settings import get_settings
from common.util.loader.file_content_extractor import FileContentExtractor


class IntentBasedFileIndexerBot:
    """
    Bot that detects intent-based file lookups (no vector search).
    Uses intent detection logic to resolve exact file path and load its content.
    """

    def __init__(
            self,
            vector_store_path,
            prompt_bot,
            retrieval_score_threshold=0.4,
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
    ):
        """
        Compatible constructor with HybridBot for loader integration.
        Ignores vectordb and retrieval params since this bot is intent-based.
        """
        # --- Core wiring (match HybridBot contract) ---
        self.logger = AppLogger.get_logger(__name__)
        self.prompt_bot = prompt_bot
        self.model_name = model_name
        self.temperature = temperature
        self.retrieval_score_threshold = retrieval_score_threshold
        self.top_k = top_k
        self.cache = CacheManager()
        self.last_metrics = {}

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
        self.logger.info(f"[IntentBasedFileIndexerBot] Loaded intent logic: {cls.__name__}")

        # --- LLM base instance ---
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)
        self.logger.info(f"✅ {self.__class__.__name__} initialized successfully (HybridBot-compatible).")

    # ---------------- Core handler ----------------
    def handle(self, question: str) -> str:
        """
        Main entrypoint.
        1. Detect if the question references a known file intent.
        2. If found, read its content and send to fallback (prompt_bot).
        3. Otherwise, respond that no matching file intent was detected.
        """
        try:
            self.logger.info("[IntentFileIndexerBot] 🧠 Detecting intent...")
            relative_path = self.intent_logic.detect(question)

            if not relative_path:
                self.logger.warning("[IntentFileIndexerBot] No intent detected.")
                return "No matching file intent detected for this query."

            self.logger.info(f"[IntentFileIndexerBot] ✅ Intent detected: {relative_path}")

            file_content = FileContentExtractor.get_file_content(relative_path)
            if not file_content:
                return f"Error reading file: {relative_path}"

            enriched_question = (
                f"{question}\n\n---\n📂 File identified: {relative_path}\n\n"
                f"Contenido del archivo:\n{file_content}"
            )

            self.logger.info("[IntentFileIndexerBot] 🚀 Forwarding to fallback LLM...")
            result = self.prompt_bot.handle(enriched_question)

            self._log_metrics(question, "intent", relative_path)
            return result

        except Exception as e:
            self.logger.error(f"[IntentFileIndexerBot] ❌ Error handling intent: {e}")
            return f"Error processing intent: {e}"

    # ---------------- Metrics ----------------
    def _log_metrics(self, user_query: str, mode: str, detected_path: str = None):
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "question": user_query,
            "mode": mode,
            "file_detected": detected_path,
        }
        self.logger.info("metric_query_handled", extra=payload)
