# File: chunk_relevance_filter.py
# Comments in English

from typing import List
from langchain_core.documents import Document
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from logic.pipeline.retrieval.util.retrieval.util.retrieval_logger import RetrievalLogger


class ChunkRelevanceFilter:

    def __init__(self, model_name: str = "BAAI/bge-reranker-large",
                 use_run_pod_GPU_for_cross_encoder=False,run_pod_url=None,run_pod_api=None):
        # Load tokenizer and model
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model.to(device)
        self.device=device

    def run_scores(self, query: str, texts: List[str]) -> List[float]:
        if not texts:
            return []
        inputs = self.tokenizer(
            [query] * len(texts),
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(self.device)
        with torch.no_grad():
            logits = self.model(**inputs).logits
            scores = logits.squeeze(-1).cpu().tolist()
        return scores

    def is_relevant(
        self,
        folder: str,
        query: str,
        docs: List[Document],
        file_logger: RetrievalLogger = None
    ) -> List[float]:
        if not docs:
            return []
        texts = [doc.page_content for doc in docs]
        scores = self.run_scores(query, texts)
        for doc, score in zip(docs, scores):
            doc.metadata["cross_encoder_score"] = score
        if file_logger:
            scored_pairs = sorted(zip(docs, scores), key=lambda x: x[1], reverse=True)
            for doc, score in scored_pairs:
                file_logger.print_cross_encoding_comp(folder, query, doc.page_content, score)
        return scores