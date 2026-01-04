import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification
from logic.pipeline.retrieval.util.retrieval.stages.common.chunk_relevance_filter import ChunkRelevanceFilter

MODEL_NAME = os.getenv("CROSS_ENCODER_MODEL", "BAAI/bge-reranker-large")
print(f"Loading model {MODEL_NAME}...")
reranker = ChunkRelevanceFilter(model_name=MODEL_NAME)
print(f"Model loaded on {reranker.device}")

def score(query: str, texts: list[str]):
    """Compute relevance scores between query and list of texts."""
    if not query or not texts:
        print("Empty query or texts received")
        return []
    print(f"Scoring query with {len(texts)} texts")
    return reranker.run_scores(query, texts)

# ---- RunPod Serverless Handler ----
def handler(job):
    """RunPod serverless handler (used in Queue mode and local --rp_serve_api)."""
    job_id = job.get("id", "unknown")
    print(f"Processing job {job_id}")
    job_input = job.get("input", {})
    query = job_input.get("query", "")
    texts = job_input.get("texts", [])
    result = {"scores": score(query, texts)}
    print(f"Job {job_id} completed")
    return result

if __name__ == "__main__":
    import argparse
    import runpod

    parser = argparse.ArgumentParser()
    parser.add_argument("--rp_serve_api", action="store_true", help="Run local HTTP API for testing")
    parser.add_argument("--rp_api_port", type=int, default=8000, help="Port for local API")
    args = parser.parse_args()

    if args.rp_serve_api:
        print(f"Starting local HTTP testing server on port {args.rp_api_port}")
        print("POST to /runsync with {'input': {'query': ..., 'texts': [...]}}")
        runpod.serverless.start({
            "handler": handler,
            "rp_serve_api": True,
            "rp_api_port": args.rp_api_port,
            "rp_api_host": "0.0.0.0"
        })
    else:
        print("Starting RunPod serverless Queue mode (production)")
        runpod.serverless.start({"handler": handler})