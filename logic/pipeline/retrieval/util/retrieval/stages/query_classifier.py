# ===== query_classifier.py =====
# # Extracts its prmompts since master prompt

from common.enum.intents import Intent
from langchain_openai import ChatOpenAI

class QueryClassifier:
    SECTION = "[CLASSIFIER]"

    def __init__(self, full_prompt: str, logger=None, use_llm_fallback: bool = True):
        self.logger = logger
        self.prompt_template = self._extract_section(full_prompt)
        self.llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.0) if use_llm_fallback else None

    def _extract_section(self, text: str) -> str:
        start = text.find(self.SECTION)
        if start == -1:
            raise ValueError(f"Missing section {self.SECTION} in master prompt")
        start += len(self.SECTION)
        end = text.find("[", start)
        section = text[start:end if end != -1 else None].strip()
        self.logger and self.logger.info("[CLASSIFIER] prompt loaded", {"length": len(section)})
        return section

    def classify(self, query: str) -> Intent:
        q = query.lower().strip()

        # === Reglas rápidas (98 % cobertura) ===
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

        # === LLM fallback usando la sección del master prompt ===
        if self.llm and self.prompt_template:
            try:
                full_prompt = self.prompt_template.format(query=query)
                resp = self.llm.invoke(full_prompt).content.strip()
                if resp in Intent.list_values():
                    return self._return(Intent(resp), query)
            except Exception as e:
                self.logger and self.logger.info("[CLASSIFIER] llm_fallback_error", {"error": str(e)})

        return self._return(Intent.FUZZY, query)

    def _return(self, intent: Intent, query: str) -> Intent:
        self.logger and self.logger.info("[QUERY-CLASSIFIER]", {"query": query, "intent": intent.value})
        return intent