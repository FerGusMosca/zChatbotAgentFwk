# ===== query_expansion.py =====
# Extracts its prompt from master prompt + uses LLMFactory (zero OpenAI coupling)

from typing import List

from common.util.loader.prompt_loader import PromptLoader
from logic.util.builder.llm_factory import LLMFactory  # ← tu factory


class QueryExpander:
    SECTION = "[EXPANDER]"

    def __init__(
        self,
        full_prompt: str,
        logger=None,
        llm_prov: str = "openai",
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self.logger = logger
        self.prompt_template=PromptLoader.extract_section_from_text(full_prompt,self.SECTION)

        self.llm = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )


    def expand(self, query: str) -> str:
        try:
            full_prompt = self.prompt_template.format(query=query)
            text = self.llm.invoke(full_prompt).strip()

            lines: List[str] = []
            for line in text.split('\n'):
                line = line.strip()
                if line and line[0].isdigit() and '.' in line[:3]:
                    clean = line.split('.', 1)[1].strip()
                    if clean:
                        lines.append(clean)

            if len(lines) >= 3:
                expanded = " OR ".join(lines[:5])
                self.logger and self.logger.info("[EXPAND] success", {"count": len(lines)})
                return expanded

            return query
        except Exception as e:
            self.logger and self.logger.info("[EXPAND] failed", {"error": str(e)})
            return query