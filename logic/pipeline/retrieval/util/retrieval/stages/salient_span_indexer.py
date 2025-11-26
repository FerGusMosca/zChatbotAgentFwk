# ===== salient_span_indexer.py =====
# All comments MUST be in English.

import logging
from typing import List
from langchain.schema import Document
from transformers import pipeline

logger = logging.getLogger("salient_span_indexer")
if not logger.handlers:
    h = logging.StreamHandler()
    f = logging.Formatter("[SSI] %(asctime)s | %(levelname)s | %(message)s")
    h.setFormatter(f)
    logger.addHandler(h)
logger.setLevel(logging.INFO)


class SalientSpanIndexer:
    """
    Extract key spans using a QA / summarization pipeline.
    """

    def __init__(
        self,
        model_name: str = "deepset/roberta-base-squad2",
        top_k: int = 5,
        logger_ref=None,
    ):
        self.top_k = top_k
        self.logger = logger_ref or logger

        try:
            self.logger.info(f"Loading SSI model: {model_name}")
            self.extractor = pipeline("question-answering", model=model_name)
            self.logger.info("SSI model loaded OK")
        except Exception as ex:
            self.logger.error(f"Failed to load SSI model: {ex}", exc_info=True)
            raise

    # -----------------------------------------------------

    def extract(self, query: str, docs: List[Document]) -> List[Document]:
        """Return top salient spans from each document."""
        try:
            if not docs:
                self.logger.info("No documents → skipping SSI")
                return []

            results = []

            for d in docs:
                try:
                    out = self.extractor(
                        question=query,
                        context=d.page_content,
                        top_k=1
                    )

                    span = out["answer"]
                    relevance = out.get("score", 0.0)

                    nd = Document(
                        page_content=span,
                        metadata={**d.metadata, "ssi_score": float(relevance)}
                    )
                    results.append(nd)

                except Exception as inner_ex:
                    self.logger.error(f"SSI extraction error: {inner_ex}")

            ranked = sorted(results, key=lambda d: d.metadata["ssi_score"], reverse=True)
            return ranked[: self.top_k]

        except Exception as ex:
            self.logger.error(f"Fatal SSI error: {ex}", exc_info=True)
            return docs  # failsafe
