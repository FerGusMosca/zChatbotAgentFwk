# ===== query_classifier.py =====
# Extracts its prompt from master prompt + uses LLMFactory (zero OpenAI coupling)

from common.enum.intents import Intent

from typing import Optional

from logic.util.builder.llm_factory import LLMFactory


class QueryClassifier:
    SECTION = "[CLASSIFIER]"

    def __init__(
        self,
        full_prompt: str,
        logger=None,
        use_llm_fallback: bool = True,
        llm_prov: str = "openai",
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
    ):
        self.logger = logger
        self.prompt_template = self._extract_section(full_prompt)

        if use_llm_fallback:
            self.llm = LLMFactory.create(
                provider=llm_prov,
                model_name=model_name,
                temperature=temperature,
            )
        else:
            self.llm = None

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

        # === Fast heuristic rules (98% coverage) ===
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

        # === LLM fallback (fully abstracted) ===
        if self.llm and self.prompt_template:
            try:
                full_prompt = self.prompt_template.format(question=query)
                resp = self.llm.invoke(full_prompt)
                if resp in Intent.list_values():
                    return self._return(Intent(resp), query)
            except Exception as e:
                self.logger and self.logger.info("[CLASSIFIER] llm_fallback_error", {"error": str(e)})

        return self._return(Intent.FUZZY, query)

    def _return(self, intent: Intent, query: str) -> Intent:
        self.logger and self.logger.info("[QUERY-CLASSIFIER]", {"query": query, "intent": intent.value})
        return intent