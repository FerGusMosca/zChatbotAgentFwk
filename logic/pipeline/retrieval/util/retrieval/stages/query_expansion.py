# ===== query_expansion.py =====
# Extracts its prompt from master prompt + uses LLMFactory (zero OpenAI coupling)

from typing import List
from logic.util.builder.llm_factory import LLMFactory  # ← tu factory


class QueryExpander:
    SECTION = "[EXPANDER]"

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
        self.logger and self.logger.info("[EXPANDER] prompt loaded", {"length": len(section)})
        return section

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