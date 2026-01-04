# File: cross_encoder_svc.py - Reemplaza el archivo completo
# Run with: python cross_encoder_svc.py

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

from logic.pipeline.retrieval.util.retrieval.stages.common.chunk_relevance_filter import ChunkRelevanceFilter

app = FastAPI()

MODEL_NAME = "BAAI/bge-reranker-large"
PORT = 8000

print(f"Loading cross-encoder model {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)
print("Model loaded.")


reranker = ChunkRelevanceFilter()
reranker.tokenizer = tokenizer
reranker.model = model

class RequestPayload(BaseModel):
    folder: str
    query: str
    texts: List[str]

@app.post("/score")
async def score_documents(payload: RequestPayload):
    query = payload.query
    texts = payload.texts
    folder = payload.folder

    if not texts:
        return {"scores": []}
    print(f"Running scores for query '{query}' for {len(texts)} chunks")
    scores = reranker.run_scores(query, texts)
    print(f"{len(scores)} successfully generated")

    return {"scores": scores}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)