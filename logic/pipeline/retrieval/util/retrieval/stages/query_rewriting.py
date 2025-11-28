# ===== query_rewriting.py =====
# Extracts its prompt from master prompt + uses LLMFactory (zero OpenAI coupling)

from typing import Optional, List
from logic.util.builder.llm_factory import LLMFactory  # ← tu factory


class QueryRewriter:
    SECTION = "[REWRITER]"

    def __init__(
        self,
        full_prompt: str,
        logger=None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self.logger = logger
        self.prompt_template = self._extract_section(full_prompt)

        # ← 100 % desacoplado via factory
        self.llm = LLMFactory.create(
            provider="openai",
            model_name=model_name,
            temperature=temperature,
        )

    def _extract_section(self, text: str) -> str:
        start = text.find(self.SECTION)
        if start == -1:
            raise ValueError(f"Missing section {self.SECTION} in master prompt")
        start += len(self.SECTION)
        end = text.find("[", start)
        section = text[start:end if end != -1 else None].strip()
        self.logger and self.logger.info("[REWRITER] prompt loaded", {"length": len(section)})
        return section

    def rewrite(self, query: str, chat_history: Optional[List] = None) -> str:
        try:
            full_prompt = self.prompt_template.format(query=query)
            result = self.llm.invoke(full_prompt).strip().strip('"\'')
            final = result if len(result.split()) > 4 else query
            self.logger and self.logger.info("[REWRITE] success", {"orig": query, "new": final})
            return final
        except Exception as e:
            self.logger and self.logger.info("[REWRITE] failed", {"error": str(e)})
            return query