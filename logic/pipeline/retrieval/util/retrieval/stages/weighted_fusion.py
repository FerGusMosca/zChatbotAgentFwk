# ===============================
# weighted_fusion.py
# All comments MUST be in English.
# ===============================

import logging
from typing import List, Dict, Any
from dataclasses import dataclass, field
from langchain.schema import Document

logger = logging.getLogger("weighted_fusion")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[WEIGHTED-FUSION] %(asctime)s | %(levelname)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ===============================
# Data model
# ===============================

@dataclass
class RetrievedDocument:
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    score_faiss: float = 0.0
    score_bm25: float = 0.0

    def combined(self, w_faiss: float, w_bm25: float) -> float:
        return self.score_faiss * w_faiss + self.score_bm25 * w_bm25


# ===============================
# Fusion
# ===============================

def perform_weighted_fusion(
    faiss_docs: List[Document],
    bm25_docs: List[Document],
    *,
    w_faiss: float = 0.65,
    w_bm25: float = 0.35,
    top_k: int = 10,
) -> List[RetrievedDocument]:

    try:
        logger.info(
            f"Starting fusion | faiss_docs={len(faiss_docs)} | bm25_docs={len(bm25_docs)}"
        )

        merged: Dict[str, RetrievedDocument] = {}

        # --- FAISS PASS ---
        for d in faiss_docs:
            key = d.page_content
            merged[key] = RetrievedDocument(
                text=d.page_content,
                metadata=d.metadata,
                score_faiss=1.0,     # FAISS doesn't provide scores
            )

        # --- BM25 PASS ---
        for d in bm25_docs:
            key = d.page_content
            if key not in merged:
                merged[key] = RetrievedDocument(
                    text=d.page_content,
                    metadata=d.metadata,
                    score_bm25=1.0,     # BM25 also doesn't give score
                )
            else:
                merged[key].score_bm25 = 1.0

        # --- RANK ---
        ranked = sorted(
            merged.values(),
            key=lambda doc: doc.combined(w_faiss, w_bm25),
            reverse=True,
        )

        result = ranked[:top_k]

        logger.info(
            f"Fusion done | merged={len(merged)} | returning={len(result)}"
        )

        return result

    except Exception as ex:
        logger.error(f"Fatal fusion error: {ex}", exc_info=True)
        return []
