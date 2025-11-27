# ===== query_expansion.py =====
# Multi-query expansion - standard & working

from langchain_openai import ChatOpenAI

class QueryExpander:
    """LLM-powered multi-query expansion for broader recall."""

    def __init__(self, logger=None):
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.0)
        self.logger = logger

    def expand(self, query: str) -> str:
        prompt = f"""Generate 5 different search queries for this topic, each from a different angle:

{query}

Focus on: rates, commodities, banking, geopolitics, equities, inflation, Fed, China.

Output ONLY the 5 queries, one per line, numbered 1-5."""

        try:
            response = self.llm.invoke(prompt)
            text = response.content.strip()

            # Extrae solo líneas que empiecen con número
            lines = []
            for line in text.split('\n'):
                line = line.strip()
                if line and line[0].isdigit() and '.' in line[:3]:
                    # 1. texto → saca el "1."
                    clean = line.split('.', 1)[1].strip()
                    if clean:
                        lines.append(clean)

            if len(lines) >= 3:
                expanded = " OR ".join(lines[:5])
                self.logger and self.logger.info("[EXPAND] success", {"count": len(lines)})
                return expanded

            # Fallback
            self.logger and self.logger.info("[EXPAND] weak", {"raw": text[:200]})
            return query

        except Exception as e:
            self.logger and self.logger.info("[EXPAND] failed", {"error": str(e)})
            return query