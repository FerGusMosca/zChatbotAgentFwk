from typing import List, Tuple
from langchain_core.documents import Document
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


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
        query: str,
        docs: List[Document],
    ) -> List[Tuple[bool, float]]:
        """
        Returns (is_relevant, relevance_score) for each chunk.
        """

        results = []

        for doc in docs:
            text = doc.page_content

            # Encode pair
            inputs = self.tokenizer(
                query,
                text,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )

            # Forward pass
            with torch.no_grad():
                logits = self.model(**inputs).logits

                # BGE reranker outputs a single score
                score = logits[0].item()


            results.append(score)

        return results
