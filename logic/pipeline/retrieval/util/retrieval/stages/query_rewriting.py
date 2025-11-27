# ===== query_rewriting.py =====
# Aggressive LLM rewriting - industry standard 2025

from langchain_openai import ChatOpenAI

class QueryRewriter:
    def __init__(self, logger=None):
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.0)
        self.logger = logger

    def rewrite(self, query: str, chat_history: list = None) -> str:
        prompt = f"""Rewrite this query to MAXIMIZE document recall in a financial macro corpus.

Add keywords: rate cuts, dollar strength, commodity crash, banking stress, Fed pivot, inflation reacceleration, China slowdown, geopolitics, tariffs, AI capex

Output ONLY the rewritten query, nothing else.

User query: {query}

Rewritten query:"""

        try:
            result = self.llm.invoke(prompt).content.strip().strip('"\'')
            final = result if len(result.split()) > 4 else query
            self.logger and self.logger.info("[REWRITE] success", {"orig": query, "new": final})
            return final
        except Exception as e:
            self.logger and self.logger.info("[REWRITE] failed", {"error": str(e)})
            return query