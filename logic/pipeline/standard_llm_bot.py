# ===== standard_llm_bot.py =====
# Simple bot for standard LLM invocations.
# Receives query + prompt, makes direct LLM call.
# No context loading, no vector search, no chunking.
# Fully LLM-agnostic via LLMFactory.

from datetime import datetime
from typing import Optional

from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from common.util.app_logger import AppLogger
from common.config.settings import get_settings
from logic.util.builder.llm_factory import LLMFactory
from logic.util.loader.standard_llm_query import StandardLLMQuery


class StandardLLMBot:
    """
    Simplest possible LLM bot.
    Receives JSON with query and prompt, invokes LLM directly.
    No file loading, no vector search, no preprocessing.
    """

    def __init__(
            self,
            vector_store_path: str,
            prompt_name: str,
            retrieval_score_threshold=None,
            llm_prov: str = "openai",
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
            logger=None,
            **kwargs
    ):
        """
        Initialize the standard LLM bot.

        Args:
            llm_prov: LLM provider (openai, anthropic, etc.)
            model_name: Specific model to use
            temperature: Sampling temperature for responses
        """
        self.logger = AppLogger.get_logger(__name__)
        self.model_name = model_name
        self.temperature = temperature
        self.llm_prov = llm_prov

        settings = get_settings()

        self.logger.info(
            "[StandardLLMBot] Initializing bot",
            extra={
                "profile": settings.bot_profile,
                "provider": llm_prov,
                "model": model_name,
                "temperature": temperature
            }
        )

        # --- LLM initialization (provider-agnostic) ---
        try:
            self.llm_client = LLMFactory.create(
                provider=llm_prov,
                model_name=model_name,
                temperature=temperature,
            )
            self.logger.info(
                "[StandardLLMBot] LLM client initialized successfully",
                extra={"provider": llm_prov, "model": model_name}
            )
        except Exception as e:
            self.logger.error(
                "[StandardLLMBot] Failed to initialize LLM client",
                extra={"error": str(e), "provider": llm_prov}
            )
            raise

        self.logger.info("[StandardLLMBot] Bot initialized successfully")

    def _invoke_llm(self, query: str, prompt: str) -> str:
        """
        Core LLM invocation.
        Creates a chat prompt template and invokes the LLM.

        Args:
            query: User's question/input
            prompt: System prompt/instructions for the LLM

        Returns:
            LLM's response as string

        Raises:
            Exception: If LLM invocation fails
        """
        self.logger.info(
            "[StandardLLMBot] Starting LLM invocation",
            extra={
                "query_preview": query[:100],
                "prompt_preview": prompt[:100]
            }
        )

        try:
            # Create prompt template with system message
            chat_prompt = ChatPromptTemplate.from_messages([
                ("system", prompt),
                ("user", "{query}")
            ])

            # Build LangChain chain
            chain = (
                    chat_prompt
                    | self.llm_client.get_client()
                    | StrOutputParser()
            )

            self.logger.info("[StandardLLMBot] Invoking LLM...")

            # Invoke LLM
            answer = chain.invoke({"query": query})

            self.logger.info(
                "[StandardLLMBot] LLM invocation completed",
                extra={
                    "answer_length": len(answer),
                    "answer_preview": answer[:200]
                }
            )

            return answer

        except Exception as e:
            self.logger.error(
                "[StandardLLMBot] LLM invocation failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "query_preview": query[:100]
                }
            )
            raise

    def handle(self, raw_query: str) -> str:
        """
        Main entry point for processing queries.
        Parses JSON query, validates format, invokes LLM.

        Args:
            raw_query: JSON string with format {"query": "...", "prompt": "..."}

        Returns:
            LLM response or error message
        """
        start_time = datetime.utcnow()

        self.logger.info(
            "[StandardLLMBot] Received query",
            extra={
                "raw_query_length": len(raw_query) if raw_query else 0,
                "timestamp": start_time.isoformat()
            }
        )

        try:
            # Parse and validate query
            self.logger.info("[StandardLLMBot] Parsing query...")
            dto = StandardLLMQuery.parse(raw_query)

            if not dto.is_valid:
                error_msg = f"Invalid query format: {dto.error_message}"
                self.logger.warning(
                    "[StandardLLMBot] Query validation failed",
                    extra={
                        "error": dto.error_message,
                        "raw_query_preview": raw_query[:200] if raw_query else ""
                    }
                )
                return error_msg

            self.logger.info(
                "[StandardLLMBot] Query validated successfully",
                extra={
                    "query_length": len(dto.query),
                    "prompt_length": len(dto.prompt) if dto.prompt else 0
                }
            )

            # Invoke LLM
            result = self._invoke_llm(dto.query, dto.prompt)

            # Log success metrics
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            self._log_metrics(
                query=dto.query,
                prompt=dto.prompt,
                result_length=len(result),
                duration=duration,
                status="success"
            )

            return result

        except Exception as e:
            # Log failure metrics
            end_time = datetime.utcnow()
            duration = (end_time - start_time).total_seconds()

            error_msg = f"Error processing query: {str(e)}"

            self.logger.error(
                "[StandardLLMBot] Query processing failed",
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration": duration,
                    "raw_query_preview": raw_query[:200] if raw_query else ""
                }
            )

            self._log_metrics(
                query=raw_query[:200] if raw_query else "",
                prompt="N/A",
                result_length=0,
                duration=duration,
                status="error",
                error=str(e)
            )

            return error_msg

    def _log_metrics(
            self,
            query: str,
            prompt: str,
            result_length: int,
            duration: float,
            status: str,
            error: Optional[str] = None
    ):
        """
        Log detailed metrics for monitoring and debugging.

        Args:
            query: User's query
            prompt: System prompt used
            result_length: Length of LLM response
            duration: Processing time in seconds
            status: "success" or "error"
            error: Error message if status is "error"
        """
        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "query_preview": query[:100],
            "prompt_preview": prompt[:100],
            "result_length": result_length,
            "duration_seconds": round(duration, 3),
            "status": status,
            "llm_provider": self.llm_prov,
            "model": self.model_name,
            "temperature": self.temperature
        }

        if error:
            payload["error"] = error

        self.logger.info(
            "[StandardLLMBot] Query metrics",
            extra=payload
        )