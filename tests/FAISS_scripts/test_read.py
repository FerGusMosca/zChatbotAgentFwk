# FILE: test_query.py
import os, json, pickle, faiss, numpy as np
from langchain_community.embeddings import OpenAIEmbeddings
os.environ["OPENAI_API_KEY"]="KEY"
FAISS_PATH=r"C:\faiss_tests"
cfg=json.load(open(os.path.join(FAISS_PATH,"text-embedding-3-large")))
index=faiss.read_index(os.path.join(FAISS_PATH,"index.faiss"))
meta=pickle.load(open(os.path.join(FAISS_PATH,"index.pkl"),"rb"))
chunks,metadata=meta["chunks"],meta["metadata"]
emb=OpenAIEmbeddings(model=cfg["embedding_model"],model_kwargs={"dimensions":cfg["dimensions"]})
QUERY= "In the Philippines, weak growth prospects"
id_map = meta["index_to_docstore_id"]

def print_all_chunks(chs):
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = fr"C:\faiss_tests\chunks_{ts}.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        for i, c in enumerate(chs):
            f.write(f"CHUNK {i}:\n{c}\n\n")
    print("WROTE:", out_path)


def emb_search(q):
    qv = np.array(emb.embed_query(q)).astype("float32")
    if cfg["normalize_L2"]:
        qv = qv / np.linalg.norm(qv)
    D, I = index.search(qv.reshape(1, -1), 500)   # ← D = distancias, I = índices
    return I[0], D[0]                             # ← devuelve índices primero


def print_matches():
    print(f"Running Query: {QUERY}")
    idxs, scores = emb_search(QUERY)          # idxs = índices reales del FAISS

    for i, fid in enumerate(idxs):
        fid = int(fid)                                            # convierte a int
        real_id = int(meta["index_to_docstore_id"][fid])          # ← acceso correcto al mapa
        print(f"\n====== HIT {i+1} (score: {scores[i]:.4f}) ======")
        print(chunks[real_id])
        print("-" * 70)

if __name__=="__main__":

    #1-  Print al chunks
    print("---START OUTPUT---")
    #print_all_chunks(chunks)

    #2- Print Matches
    print_matches()

