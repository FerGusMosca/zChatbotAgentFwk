# ===== query_classifier.py =====
# All comments MUST be in English.

class QueryClassifier:
    """
    Intent-based classifier.
    Detects the STRUCTURE of the question, not the domain.
    """

    def __init__(self, logger=None):
        self.logger = logger

    def _log(self, event, payload):
        if self.logger:
            try:
                self.logger.info(f"[QUERY-CLASSIFIER] {event}", extra=payload)
            except:
                pass

    def classify(self, query: str) -> str:
        """
        Possible labels:
            - broad_query
            - specific_query
            - analytical_query
            - enumeration_query
            - temporal_query
            - fuzzy_query
        """

        q = query.lower().strip()

        # BROAD / SUMMARY queries
        if any(w in q for w in ["summarize", "overall", "themes", "narratives", "overview"]):
            label = "broad_query"

        # LISTINGS / ENUMERATIONS
        elif any(w in q for w in ["list", "enumerate", "what are the risks", "what risks"]):
            label = "enumeration_query"

        # ANALYSIS / WHY / DRIVERS
        elif any(w in q for w in ["why", "drivers", "catalysts", "factors", "explain"]):
            label = "analytical_query"

        # TEMPORAL
        elif any(w in q for w in ["when", "timeline", "evolution", "how has it changed"]):
            label = "temporal_query"

        # SPECIFIC FACT QUERY
        elif len(q.split()) <= 10:  # short/direct questions
            label = "specific_query"

        # DEFAULT
        else:
            label = "fuzzy_query"

        self._log("classified", {"query": query, "label": label})
        return label
