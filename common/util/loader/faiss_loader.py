# All comments MUST be in English.

import os
from langchain.schema import Document
from langchain_community.docstore import InMemoryDocstore
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings
import json
import pickle
import faiss

class FaissVectorstoreLoader:
    """
    Utility loader that supports:
      1) Legacy FAISS format (index.faiss + index.pkl)
      2) New advanced FAISS format (docstore + id_map inside index.pkl)
    """

    @staticmethod
    def load_legacy_faiss(path: str):
        """Load vectorstore using the OLD LangChain FAISS loader."""
        emb = OpenAIEmbeddings()
        try:
            vdb = FAISS.load_local(
                path,
                emb,
                allow_dangerous_deserialization=True
            )

            ntotal = getattr(getattr(vdb, "index", None), "ntotal", None)
            print(f"[FAISS-LEGACY] Loaded. ntotal={ntotal}")
            return vdb

        except Exception as ex:
            print(f"[FAISS-LEGACY] Failed: {ex}")
            return None

    @staticmethod
    def load_advanced_faiss(path: str):
        """
        Load vectorstore using ADVANCED SAFE FORMAT.
        Enforces strict key casting + fallback for FAISS/LC mismatches.
        All comments in English.
        """
        try:
            faiss_path = os.path.join(path, "index.faiss")
            meta_path = os.path.join(path, "index.pkl")

            if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
                print("[FAISS-ADV] Missing index.faiss or index.pkl.")
                return None

            # Load FAISS index
            index = faiss.read_index(faiss_path)

            # Load metadata
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

            chunks = meta["chunks"]
            metadata = meta["metadata"]
            id_map_raw = meta["index_to_docstore_id"]
            doc_raw = meta["docstore"]

            # 1) cast docstore keys -> str
            docstore_dict = {str(i): Document(page_content=chunks[i], metadata=metadata[i]) for i in range(len(chunks))}

            # 2) cast id_map -> int -> str
            id_map = {int(k): str(v) for k, v in id_map_raw.items()}

            # 3) build SAFE fallback: ensure every FAISS id has doc
            missing = []
            for fid in range(index.ntotal):
                if fid not in id_map:
                    missing.append(fid)
                    id_map[fid] = str(fid)
                    docstore_dict[str(fid)] = Document(
                        page_content="[[FALLBACK — missing chunk]]",
                        metadata={}
                    )

            if missing:
                print(f"[FAISS-ADV][WARN] Fixed {len(missing)} missing ids: {missing[:10]} ...")

            # Logging
            print(f"[FAISS-ADV] Loaded. ntotal = {index.ntotal}")
            print(f"[FAISS-ADV] chunks = {len(chunks)}")
            print(f"[FAISS-ADV] docstore_keys_range = "
                  f"{min(docstore_dict.keys())} → {max(docstore_dict.keys())}")
            print(f"[FAISS-ADV] sample_id_map = {list(id_map.items())[:5]}")

            # Build LangChain FAISS instance
            emb = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")  # Comments in English
            docstore = InMemoryDocstore(docstore_dict)

            vdb = FAISS(
                index=index,
                docstore=docstore,
                index_to_docstore_id=id_map,
                embedding_function=emb,
                normalize_L2=False
            )
            vdb.metadatas = metadata

            return vdb, meta

        except Exception as ex:
            print(f"[FAISS-ADV] Failed: {ex}")
            return None

    @staticmethod
    def load_faiss_rerankers(faiss_path: str, config_path: str):
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
            if cfg.get("dimensions") != 384:
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
            norm_on_search=cfg.get("normalize_L2", built_w_norm)
            vdb = FAISS(
                embedding_function=correct_emb.embed_query,
                index=index,
                docstore=InMemoryDocstore(docstore_dict),
                index_to_docstore_id=id_map,
                normalize_L2= norm_on_search
            )
            vdb.metadatas = metadata

            return vdb, meta, correct_emb , norm_on_search

        except Exception as ex:
            raise RuntimeError(f"[FAISS-RERANKERS] Load failed: {ex}")

    @staticmethod
    def load_vectorstore_any(path: str):
        """
        Try legacy loader first. If it fails, try advanced.
        """
        vdb = FaissVectorstoreLoader.load_legacy_faiss(path)
        if vdb:
            return vdb

        return FaissVectorstoreLoader.load_advanced_faiss(path)
