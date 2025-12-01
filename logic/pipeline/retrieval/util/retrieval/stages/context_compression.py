# ===============================
# context_compression.py
# All comments MUST be in English.
# ===============================

import logging
from typing import List
from langchain.schema import Document
from logic.util.builder.embedding_factory import EmbeddingFactory  # your factory

logger = logging.getLogger("context_compression")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "[COMPRESSION] %(asctime)s | %(levelname)s | %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# ===============================
# Compression class
# ===============================

class ContextCompressor:
    """
    Reduces each retrieved document to N most relevant sentences.
    This lowers token usage and improves grounding on final answer.
    Zero LLM — only embedding similarity.
    """

    def __init__(
        self,
        model_name: str = "text-embedding-3-small",
        top_k_sentences: int = 3,
        logger_instance=None,
    ):
        self.logger = logger_instance or logger
        self.top_k = top_k_sentences

        # Reuse your embedding factory (same as FAISS ingest)
        self.embedder = EmbeddingFactory.create(model_name=model_name)

    # -------------------------------

    def _split_sentences(self, text: str) -> List[str]:
        """Simple sentence splitter — safe for all PDFs."""
        import re
        parts = re.split(r'(?<=[.!?])\s+', text)
        return [p.strip() for p in parts if len(p.strip()) > 0]

    # -------------------------------

    def _rank_sentences(self, sentences: List[str], query: str) -> List[str]:
        """Ranks sentences by cosine similarity to query embedding."""

        if not sentences:
            return []

        q_emb = self.embedder.embed(query)

        scored = []
        for s in sentences:
            s_emb = self.embedder.embed(s)
            sim = self._cosine(q_emb, s_emb)
            scored.append((sim, s))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[: self.top_k]]

    # -------------------------------

    @staticmethod
    def _cosine(a, b):
        import numpy as np
        a = np.array(a)
        b = np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))

    # -------------------------------

    def compress(self, docs: List[Document], query: str) -> List[Document]:
        try:
            self.logger.info(
                f"Starting compression | docs={len(docs)} | top_k={self.top_k}"
            )

            compressed_docs = []

            for d in docs:
                sents = self._split_sentences(d.page_content)
                top_sents = self._rank_sentences(sents, query)

                new_text = "\n".join(top_sents)
                new_doc = Document(
                    page_content=new_text,
                    metadata=d.metadata.copy(),
                )
                compressed_docs.append(new_doc)

            self.logger.info(f"Compression done | {len(compressed_docs)} docs")

            return compressed_docs

        except Exception as ex:
            self.logger.error(f"Compression fatal error: {ex}", exc_info=True)
            return docs
