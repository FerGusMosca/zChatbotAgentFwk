# ===== query_expansion.py =====
# All comments MUST be in English.

class QueryExpander:
    """Rule-based query expansion: synonyms, variants, domain terms."""

    def __init__(self, logger=None):
        self.logger = logger

        # Very minimal seed dictionary.
        self.synonyms = {
            "inflation": ["cpi", "prices", "cost of living"],
            "fed": ["federal reserve", "powell"],
            "recession": ["slowdown", "economic contraction"],
            "gold": ["xau", "precious metal"],
        }

    def expand(self, query: str) -> str:
        try:
            q_lower = query.lower()
            extra_terms = []

            for key, syns in self.synonyms.items():
                if key in q_lower:
                    extra_terms.extend(syns)

            if not extra_terms:
                return query

            expanded = f"{query} ({' OR '.join(extra_terms)})"
            return expanded

        except Exception:
            return query
