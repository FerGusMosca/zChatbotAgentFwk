# ===== query_rewriting.py =====
# All comments MUST be in English.

from langchain_openai import ChatOpenAI
import re

class QueryRewriter:
    """LLM-powered query rewriting with normalization + safety."""

    def __init__(self, model_name="gpt-4o-mini", temperature=0.0, logger=None):
        self.llm = ChatOpenAI(model_name=model_name, temperature=temperature)
        self.logger = logger

    def _log(self, event, payload):
        if self.logger:
            try:
                self.logger.info(f"[QUERY-REWRITE] {event}", extra=payload)
            except:
                pass

    def normalize(self, q: str) -> str:
        """Lowercase + trim + remove duplicate spaces."""
        q2 = re.sub(r"\s+", " ", q.strip().lower())
        self._log("normalized", {"in": q, "out": q2})
        return q2

    def rewrite(self, raw_query: str, chat_history: list) -> str:
        """Rewrite query for retrieval — history aware + noise filtered."""
        try:
            prompt = (
                "Rewrite the user query so it becomes optimal for document retrieval.\n"
                "Rules:\n"
                "- Keep only factual terms.\n"
                "- Remove opinions and filler text.\n"
                "- Keep the semantic intent.\n"
                "- If pronouns ('he', 'she', 'it', 'they') appear, resolve using chat history.\n\n"
                f"Chat history: {chat_history}\n"
                f"Original query: {raw_query}\n"
            )

            result = self.llm.invoke(prompt).content
            final = self.normalize(result)

            self._log("rewrite_done", {"raw": raw_query, "rewritten": final})
            return final

        except Exception as ex:
            self._log("rewrite_error", {"exception": str(ex)})
            return self.normalize(raw_query)
