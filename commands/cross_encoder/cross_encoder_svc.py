# File: cross_encoder_svc.py
import os, torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from logic.pipeline.retrieval.util.retrieval.stages.common.chunk_relevance_filter import ChunkRelevanceFilter

MODEL_NAME = "BAAI/bge-reranker-large"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()
model.to(torch.device("cuda" if torch.cuda.is_available() else "cpu"))

reranker = ChunkRelevanceFilter()
reranker.tokenizer = tokenizer
reranker.model = model

def score(query, texts):
    if not query or not texts: return []
    return reranker.run_scores(query, texts)

# ---- RunPod Serverless ----
def handler(event):
    payload = event.get("input", {})
    return {"scores": score(payload.get("query"), payload.get("texts", []))}

# ---- Local HTTP (optional) ----
if __name__ == "__main__":
    from fastapi import FastAPI
    from pydantic import BaseModel
    import uvicorn
    app = FastAPI()
    class Req(BaseModel): query: str; texts: list
    @app.post("/score")
    def http_score(r: Req): return {"scores": score(r.query, r.texts)}
    uvicorn.run(app, host="0.0.0.0", port=8000)
