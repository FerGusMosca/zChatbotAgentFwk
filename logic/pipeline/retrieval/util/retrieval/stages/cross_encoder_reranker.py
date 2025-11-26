# ===== cross_encoder_reranker.py =====
# All comments MUST be in English.

import logging
from typing import List
from langchain.schema import Document
from sentence_transformers import CrossEncoder

logger = logging.getLogger("cross_encoder_reranker")
if not logger.handlers:
    h = logging.StreamHandler()
    f = logging.Formatter("[CE-RERANK] %(asctime)s | %(levelname)s | %(message)s")
    h.setFormatter(f)
    logger.addHandler(h)
logger.setLevel(logging.INFO)


class CrossEncoderReranker:
    """
    Lightweight reranker using a SentenceTransformer CrossEncoder.
    """

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        top_k: int = 8,
        logger_ref=None,
    ):
        self.top_k = top_k
        self.logger = logger_ref or logger

        try:
            self.logger.info(f"Loading CrossEncoder model: {model_name}")
            self.model = CrossEncoder(model_name)
            self.logger.info("CrossEncoder loaded OK")
        except Exception as ex:
            self.logger.error(f"Failed to load CrossEncoder: {ex}", exc_info=True)
            raise

    # -----------------------------------------------------

    def rerank(self, query: str, docs: List[Document]) -> List[Document]:
        """Score documents using cross-encoder relevance."""
        try:
            if not docs:
                self.logger.info("No docs received → skipping rerank")
                return []

            self.logger.info(f"Reranking {len(docs)} docs")

            pairs = [(query, d.page_content) for d in docs]
            scores = self.model.predict(pairs)

            for d, s in zip(docs, scores):
                d.metadata["ce_score"] = float(s)

            ranked = sorted(docs, key=lambda d: d.metadata["ce_score"], reverse=True)
            result = ranked[: self.top_k]

            self.logger.info(f"Reranking complete | returned={len(result)}")
            return result

        except Exception as ex:
            self.logger.error(f"CrossEncoder Rerank fatal error: {ex}", exc_info=True)
            return docs  # failsafe
