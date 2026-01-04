# File: chunk_relevance_filter.py
# Comments in English

from typing import List
from langchain_core.documents import Document
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
from logic.pipeline.retrieval.util.retrieval.util.retrieval_logger import RetrievalLogger

# Global model load (once at container startup - ideal for serverless)
MODEL_NAME = "BAAI/bge-reranker-large"
print("Loading cross-encoder model...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print("Model loaded.")

class ChunkRelevanceFilter:
    def run_scores(self, query: str, texts: List[str]) -> List[float]:
        if not texts:
            return []
        inputs = tokenizer(
            [query] * len(texts),
            texts,
            padding=True,
            truncation=True,
            max_length=512,
            return_tensors="pt"
        ).to(device)
        with torch.no_grad():
            logits = model(**inputs).logits
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