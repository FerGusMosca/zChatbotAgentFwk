# ===============================
# weighted_fusion.py
# All comments MUST be in English.
# ===============================

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from langchain.schema import Document


# ===============================
# Data model
# ===============================

@dataclass
class RetrievedDocument:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score_faiss: float = 0.0
    score_bm25: float = 0.0
    score_rrf:float = 0.0

    def combined(self, w_faiss: float, w_bm25: float) -> float:
        return self.score_faiss * w_faiss + self.score_bm25 * w_bm25

    def to_log_string(self) -> str:
        """Return compact string for debug log: score + first 100 chars of text"""
        preview = self.text.replace("\n", " ").replace("\r", " ")[:100]
        if len(self.text) > 100:
            preview += "..."
        return f"[score={self.combined(0.7, 0.3):.4f} faiss={self.score_faiss:.3f} bm25={self.score_bm25:.3f}] {preview}"


# ===============================
# Fusion
# ===============================

class WeightedFusion:
    def __init__(self,logger):
        self.logger=logger

    def perform_weighted_fusion(
            self,
            faiss_docs: List[Document],
            bm25_docs: List[Document],
            *,
            fusion_top_faiss: int = 40,
            fusion_top_bm25: int = 8
    ) -> List[RetrievedDocument]:
        """
        Production-grade simple fusion:
        - Prioritizes exact lexical matches from BM25
        - Adds semantic results from FAISS
        - Deduplicates only by real document identity (source_pdf + chunk_id)
        """
        try:
            # Step 1: BM25 first – exact matches are usually the correct answer
            candidates = bm25_docs[:fusion_top_bm25]

            # Step 2: Append semantic results from FAISS
            candidates += faiss_docs[:fusion_top_faiss]

            # Step 3: Deduplicate by true document ID (never by text)
            seen = set()
            result = []
            for doc in candidates:
                key = f"{doc.metadata.get('source_pdf', '')}__{doc.metadata.get('chunk_id', '')}"
                if key not in seen:
                    seen.add(key)
                    result.append(
                        RetrievedDocument(
                            text=doc.page_content,
                            metadata=doc.metadata,
                        )
                    )

            self.logger.info(
                f"Simple fusion completed → BM25[:{fusion_top_bm25}] + FAISS[:{fusion_top_faiss}] "
                f"→ {len(result)} unique chunks after dedup by ID"
            )
            return result

        except Exception as ex:
            self.logger.error(f"Fatal error in simple fusion: {ex}", exc_info=True)
            # Fallback: return whatever we have safely
            return []
