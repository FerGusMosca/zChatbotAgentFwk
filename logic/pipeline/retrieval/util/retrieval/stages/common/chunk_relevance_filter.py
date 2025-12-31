from typing import List, Tuple
from langchain_core.documents import Document
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from logic.pipeline.retrieval.util.retrieval.util.retrieval_logger import RetrievalLogger


class ChunkRelevanceFilter:
    """
    Cross-encoder relevance scoring.
    Higher score = more relevant.
    """

    def __init__(self, model_name: str = "BAAI/bge-reranker-large"):
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

    def is_relevant(
            self,
            folder: str,
            query: str,
            docs: List[Document],
            file_logger: RetrievalLogger = None
    ) -> List[float]:
        """
        Score all query-doc pairs using batched inference with dynamic early stopping.
        Stops processing remaining docs if scores fall far below the best seen so far.
        Returns scores in the same order as input docs.
        """
        if not docs:
            return []

        # Extract texts
        texts = [doc.page_content for doc in docs]

        # Batch tokenization (much faster than per-doc)
        inputs = self.tokenizer(
            [query] * len(texts),
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(next(self.model.parameters()).device)

        # Single batched forward pass
        with torch.no_grad():
            logits = self.model(**inputs).logits
            scores = logits.squeeze(-1).cpu().tolist()  # list of floats, same order as docs

        # Optional: sorted logging
        if file_logger:
            scored_pairs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
            for doc, score in scored_pairs:
                file_logger.print_cross_encoding_comp(folder, query, doc.page_content, score)

        return scores
