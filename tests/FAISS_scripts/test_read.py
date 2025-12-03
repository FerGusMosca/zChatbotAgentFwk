# FILE: test_query.py
import os, json, pickle, faiss, numpy as np
from langchain_community.embeddings import OpenAIEmbeddings
os.environ["OPENAI_API_KEY"]="OPEN AI KEY"

FAISS_PATH=r"C:\faiss_tests"
cfg=json.load(open(os.path.join(FAISS_PATH,"text-embedding-3-large.json")))
index=faiss.read_index(os.path.join(FAISS_PATH,"index.faiss"))
meta=pickle.load(open(os.path.join(FAISS_PATH,"index.pkl"),"rb"))
chunks,metadata=meta["chunks"],meta["metadata"]
emb=OpenAIEmbeddings(model=cfg["embedding_model"],model_kwargs={"dimensions":cfg["dimensions"]})
QUERY= "List all the sections mentioned in the Australian Morning Focus report."
id_map = meta["index_to_docstore_id"]

def print_all_chunks(chs):
    out=[]
    for i,c in enumerate(chs):
        print(f" chunk {i}:{ c.upper()}")
    return out

def emb_search(q):
    qv=np.array(emb.embed_query(q)).astype("float32")
    qv=qv/np.linalg.norm(qv) if cfg["normalize_L2"] else qv
    idx,s=index.search(qv.reshape(1,-1),80)
    return idx[0],s[0]



def print_matches():
    print(f"Running Query: {QUERY}")
    id_map = {str(k): v for k, v in meta["index_to_docstore_id"].items()}
    idxs, scores = emb_search(QUERY)
    for i, fid in enumerate(idxs.astype(int)):
        real_id = int(id_map[str(fid)])
        print("\n====== HIT", i+1, "======")
        print(chunks[real_id])


if __name__=="__main__":

    #1-  Print al chunks
    #print_all_chunks(chunks)

    #2- Print Matches
    print_matches()

