# FILE: test_query_bge.py
import os, json, pickle, faiss, numpy as np
from sentence_transformers import SentenceTransformer

FAISS_PATH = r"C:\faiss_tests"

cfg = json.load(open(os.path.join(FAISS_PATH, "bge-large-en-v1.5.json")))
index = faiss.read_index(os.path.join(FAISS_PATH, "index.faiss"))
meta = pickle.load(open(os.path.join(FAISS_PATH, "index.pkl"), "rb"))
chunks, metadata = meta["chunks"], meta["metadata"]
id_map = meta["index_to_docstore_id"]

# Use the same model as used in the build
model = SentenceTransformer(cfg["embedding_model"])

QUERY = "What is the expected headline CPI and food deflation trend for India in late 2025, and what monetary policy actions are anticipated by the RBI"


def print_all_chunks(chs):
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = fr"C:\faiss_tests\chunks_{ts}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(chs):
            f.write(f"CHUNK {i}:\n{c}\n\n")
    print("WROTE:", out_path)


def emb_search(q):
    qv = model.encode([q], normalize_embeddings=True).astype("float32")
    if cfg["normalize_L2"]:
        qv = qv / np.linalg.norm(qv)
    D, I = index.search(qv, 20)
    return I[0], D[0]


def print_matches():
    print(f"Running Query: {QUERY}")
    idxs, scores = emb_search(QUERY)
    for i, fid in enumerate(idxs):
        fid = int(fid)
        real_id = int(id_map[fid])
        print(f"\n====== HIT {i+1} (score: {scores[i]:.4f}) ======")
        print(chunks[real_id])
        print("-" * 70)


if __name__ == "__main__":
    print("---START OUTPUT---")
    #print_all_chunks(chunks)   # Optional: save all chunks
    print_matches()
