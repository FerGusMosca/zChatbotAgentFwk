# ===== query_rewriting.py =====
# # Extracts its prmompts since master prompt

from langchain_openai import ChatOpenAI

class QueryRewriter:
    SECTION = "[REWRITER]"

    def __init__(self, full_prompt: str, logger=None):
        self.logger = logger
        self.prompt_template = self._extract_section(full_prompt)
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.0)

    def _extract_section(self, text: str) -> str:
        start = text.find(self.SECTION)
        if start == -1:
            raise ValueError(f"Missing section {self.SECTION} in master prompt")
        start += len(self.SECTION)
        end = text.find("[", start)
        section = text[start:end if end != -1 else None].strip()
        self.logger and self.logger.info("[REWRITER] prompt loaded", {"length": len(section)})
        return section

    def rewrite(self, query: str, chat_history: list = None) -> str:
        try:
            full_prompt = self.prompt_template.format(query=query)
            result = self.llm.invoke(full_prompt).content.strip().strip('"\'')
            final = result if len(result.split()) > 4 else query
            self.logger and self.logger.info("[REWRITE] success", {"orig": query, "new": final})
            return final
        except Exception as e:
            self.logger and self.logger.info("[REWRITE] failed", {"error": str(e)})
            return query