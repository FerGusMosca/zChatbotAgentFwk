# FILE: test_build.py
import os, json, pickle, faiss
import numpy as np

os.environ["OPENAI_API_KEY"] = "KEY"

#ROOT = r"C:\faiss_tests\Nov 6"
ROOT = r"C:\faiss_tests\Nov_6_red"
OUT  = r"C:\faiss_tests"
os.makedirs(OUT, exist_ok=True)

CONFIG = {
    "embedding_model": "BAAI/bge-large-en-v1.5",
    "dimensions": 1024,
    "metric": "METRIC_INNER_PRODUCT",
    "normalize_L2": True,
    "distance_is_cosine": True,
    "index_type": "IndexFlatIP",
    "built_with_normalization": True,
}

all_chunks=[]
all_meta=[]
all_emb=[]

for root,dirs,files in os.walk(ROOT):

    # detect EXACT leaf directories containing the files
    c=os.path.join(root,"chunks.txt")
    m=os.path.join(root,"metadata.json")
    e=os.path.join(root,"embeddings.npy")

    if not (os.path.isfile(c) and os.path.isfile(m) and os.path.isfile(e)):
        print(f"[MISS] {root}  c={os.path.isfile(c)}  m={os.path.isfile(m)}  e={os.path.isfile(e)}")
        continue

    # load triple
    raw = open(c, encoding="utf-8").read()

    # split by empty line (una o más líneas vacías)
    import re

    chunks = [
        x.strip()
        for x in re.split(r"\n\s*\n", raw)
        if x.strip()
    ]
    print(f"Found {len(chunks)} chunks!!!")
    meta=json.load(open(m,encoding="utf-8"))
    emb=np.load(e).astype("float32")

    print(f"embed found w {emb.shape[0]} rows")
    print("embed Shape:", emb.shape)
    print("embed Dtype:", emb.dtype)
    print("embed First row sample:", emb[0][:10])
    print("embed Min/Max:", emb.min(), emb.max())

    # strict triple validation

    print(f"[ADD] {root}  chunks={len(chunks)}")  # log added
    all_chunks.extend(chunks)
    all_meta.extend(meta)
    all_emb.append(emb)

all_emb=np.vstack(all_emb)
faiss.normalize_L2(all_emb)

index=faiss.IndexFlatIP(CONFIG["dimensions"])
index.add(all_emb)

faiss.write_index(index, os.path.join(OUT,"index.faiss"))
json.dump(CONFIG, open(os.path.join(OUT,"bge-large-en-v1.5.json"),"w"), indent=2)

pickle.dump(
    {"chunks":all_chunks,"metadata":all_meta,
     "index_to_docstore_id":{i:str(i) for i in range(len(all_chunks))}},
    open(os.path.join(OUT,"index.pkl"),"wb")
)

print("DONE:", all_emb.shape)
