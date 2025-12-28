# ===== query_rewriting.py =====
# Extracts its prompt from master prompt + uses LLMFactory (zero OpenAI coupling)

from typing import Optional, List

from common.util.loader.prompt_loader import PromptLoader
from logic.util.builder.llm_factory import LLMFactory  # ← tu factory


class QueryRewriter:
    SECTION = "[REWRITER]"

    def __init__(
        self,
        full_prompt: str,
        logger=None,
        llm_prov:str="openai",
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self.logger = logger
        self.prompt_template = PromptLoader.extract_section_from_text(full_prompt, self.SECTION)

        self.llm = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )

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