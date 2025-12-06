import json
import os
import pickle

import numpy as np
from langchain.vectorstores import faiss
from langchain_community.docstore import InMemoryDocstore
import faiss
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from sentence_transformers import SentenceTransformer


class FaissSearcher():

    def __init__(self,faiss_cfg,top_k_faiss):
        self.faiss_cfg=faiss_cfg
        self.top_k_faiss=top_k_faiss

        self.vectordb = None
        self.meta = None
        self.norm_on_search = None
        self.docs_raw = None
        self.text_raw = None


    def load_faiss_rerankers(self,faiss_path: str, config_path: str):
        """
        Load FAISS vectorstore strictly according to the given config_path JSON.
        Throws exceptions if any attribute is unexpected.
        """
        try:
            meta_path = os.path.join(faiss_path, "index.pkl")
            index_file = os.path.join(faiss_path, "index.faiss")

            if not (os.path.exists(index_file) and os.path.exists(meta_path) and os.path.exists(config_path)):
                raise FileNotFoundError("[FAISS-RERANKERS] index.faiss, index.pkl or config missing")

            # === Load config ===
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            # === Validate config strictly ===
            if cfg.get("embedding_model") != "BAAI/bge-large-en-v1.5":
                raise ValueError(f"Unsupported embedding_model: {cfg.get('embedding_model')}")
            if cfg.get("dimensions") != 1024:
                raise ValueError(f"Unsupported dimensions: {cfg.get('dimensions')}")
            if cfg.get("index_type") != "IndexFlatIP":
                raise ValueError(f"Unsupported index_type: {cfg.get('index_type')}")

            built_w_norm = cfg.get("built_with_normalization", False)
            if not built_w_norm:
                raise ValueError("Index must be built with normalization")

            # === Load FAISS index ===
            index = faiss.read_index(index_file)

            # === Load metadata ===
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

            chunks = meta["chunks"]
            metadata = meta["metadata"]
            id_map_raw = meta["index_to_docstore_id"]

            # === Ensure docstore matches index.ntotal ===
            docstore_dict = {}
            for fid in range(index.ntotal):
                if fid < len(chunks) and fid < len(metadata):
                    docstore_dict[str(fid)] = Document(page_content=chunks[fid], metadata=metadata[fid])
                else:
                    docstore_dict[str(fid)] = Document(page_content="[[MISSING CHUNK]]", metadata={})

            # === Build id_map ===
            id_map = {int(k): str(v) for k, v in id_map_raw.items()}
            for fid in range(index.ntotal):
                if fid not in id_map:
                    id_map[fid] = str(fid)

            print(f"[FAISS-RERANKERS] Loaded {index.ntotal} vectors, dim={index.d}")

            # === Embedding function according to config ===
            correct_emb = OpenAIEmbeddings(
                model=cfg["embedding_model"],
                dimensions=cfg["dimensions"]
            )

            # === Apply normalization if built with normalization ===
            '''
            if cfg.get("built_with_normalization", False):
                faiss.normalize_L2(index.reconstruct_n(0, index.ntotal))
            '''

            # === Build FAISS wrapper ===
            norm_on_search = cfg.get("normalize_L2", built_w_norm)
            vdb = FAISS(
                embedding_function=correct_emb.embed_query,
                index=index,
                docstore=InMemoryDocstore(docstore_dict),
                index_to_docstore_id=id_map,
                normalize_L2=norm_on_search
            )
            vdb.metadatas = metadata

            self.vectordb=vdb
            self.meta=meta
            self.norm_on_search=norm_on_search
            self.docs_raw = meta["metadata"]
            self.text_raw = meta["chunks"]

            return vdb, meta, correct_emb, norm_on_search

        except Exception as ex:
            raise RuntimeError(f"[FAISS-RERANKERS] Load failed: {ex}")

    def run_faiss_search(self, query: str):
        """
        FAISS search that returns exactly the same format as BM25 retriever.
        Returns a list of langchain Document objects (page_content + metadata).
        Fully compatible with your existing RAG pipeline.
        """
        # 1. Use the exact same local model that was used to build the index
        embedder = SentenceTransformer(self.faiss_cfg["embedding_model"])

        # 2. Encode query (bge already normalizes by default)
        qv = embedder.encode([query], normalize_embeddings=True).astype("float32")

        # 3. Extra L2 normalization only if required by config
        if self.norm_on_search:
            qv /= np.linalg.norm(qv, axis=1, keepdims=True)

        # 4. Search in the FAISS index
        D, I = self.vectordb.index.search(qv, self.top_k_faiss)

        # 5. Return exactly what BM25 returns → list[Document]
        results = []
        id_map = self.meta["index_to_docstore_id"]

        for faiss_idx, distance in zip(I[0], D[0]):
            real_id = int(id_map[int(faiss_idx)])
            chunk_text = self.text_raw[real_id]

            results.append(Document(
                page_content=chunk_text,
                metadata={
                    "source": f"faiss_chunk_{real_id}",
                    "score": float(distance),  # cosine distance (lower = better)
                    "faiss_idx": int(faiss_idx)
                }
            ))

        return results