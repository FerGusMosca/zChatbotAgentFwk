# ===== query_classifier.py =====
# 2025 production – zero strings sueltos

from common.enum.intents import Intent
from langchain_openai import ChatOpenAI

class QueryClassifier:
    def __init__(self, logger=None, use_llm_fallback: bool = False):
        self.logger = logger
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.0) if use_llm_fallback else None

    def classify(self, query: str) -> Intent:
        q = query.lower().strip()

        if any(k in q for k in ["summarize", "overview", "dominant", "narratives", "themes"]):
            return self._return(Intent.BROAD, query)
        if any(k in q for k in ["list", "enumerate", "main risks", "key drivers"]):
            return self._return(Intent.ENUMERATION, query)
        if any(k in q for k in ["why", "drivers", "catalysts", "factors", "explain"]):
            return self._return(Intent.ANALYTICAL, query)
        if any(k in q for k in ["when", "timeline", "since", "evolution"]):
            return self._return(Intent.TEMPORAL, query)
        if len(q.split()) <= 14 and q.startswith(("what", "how much", "which", "is", "does")):
            return self._return(Intent.SPECIFIC, query)

        # LLM fallback opcional
        if self.llm:
            try:
                resp = self.llm.invoke(
                    f"Return ONLY one intent from this list: {', '.join(Intent.list_values())}\nQuery: {query}\nIntent:"
                ).content.strip()
                if resp in Intent.list_values():
                    return self._return(Intent(resp), query)
            except:
                pass

        return self._return(Intent.FUZZY, query)

    def _return(self, intent: Intent, query: str) -> Intent:
        if self.logger:
            self.logger.info("[QUERY-CLASSIFIER]", {"query": query, "intent": intent.value})
        return intent