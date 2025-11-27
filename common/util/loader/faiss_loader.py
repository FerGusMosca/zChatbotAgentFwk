# All comments MUST be in English.

import os
from langchain.schema import Document
from langchain_community.docstore import InMemoryDocstore
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

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
    def load_faiss_rerankers(path: str):
        """
        Load FAISS vectorstore for the rerankers pipeline.
        Uses the exact embedding model that built the index:
        text-embedding-3-large with dimensions=1024 (1024-d vectors).
        All comments in English.
        """
        try:
            faiss_path = os.path.join(path, "index.faiss")
            meta_path = os.path.join(path, "index.pkl")

            if not (os.path.exists(faiss_path) and os.path.exists(meta_path)):
                print("[FAISS-RERANKERS] Missing index.faiss or index.pkl")
                return None, None

            # Load raw FAISS index
            index = faiss.read_index(faiss_path)

            # Load pickle metadata
            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

            chunks = meta["chunks"]
            metadata = meta["metadata"]
            id_map_raw = meta["index_to_docstore_id"]

            # Build docstore with string keys
            docstore_dict = {
                str(i): Document(page_content=chunks[i], metadata=metadata[i])
                for i in range(len(chunks))
            }

            # Convert id_map keys to int → str
            id_map = {int(k): str(v) for k, v in id_map_raw.items()}

            # Safety: fill missing IDs (should never happen but keeps LangChain happy)
            for fid in range(index.ntotal):
                if fid not in id_map:
                    id_map[fid] = str(fid)
                    docstore_dict[str(fid)] = Document(
                        page_content="[[MISSING CHUNK]]", metadata={}
                    )

            print(f"[FAISS-RERANKERS] Loaded {index.ntotal} vectors, dim={index.d}")

            # Correct embedding model (the one used when the index was built)
            from langchain_openai import OpenAIEmbeddings
            correct_emb = OpenAIEmbeddings(
                model="text-embedding-3-large",
                dimensions=1024  # forces 1024-d output
            )

            # LangChain in-memory docstore
            docstore = InMemoryDocstore(docstore_dict)

            # Build FAISS wrapper with the right embedding function
            vdb = FAISS(
                embedding_function=correct_emb.embed_query,  # critical line
                index=index,
                docstore=docstore,
                index_to_docstore_id=id_map,
                normalize_L2=False,  # already normalized when index was created
            )
            vdb.metadatas = metadata

            return vdb, meta

        except Exception as ex:
            print(f"[FAISS-RERANKERS] Load failed: {ex}")
            return None, None

    @staticmethod
    def load_vectorstore_any(path: str):
        """
        Try legacy loader first. If it fails, try advanced.
        """
        vdb = FaissVectorstoreLoader.load_legacy_faiss(path)
        if vdb:
            return vdb

        return FaissVectorstoreLoader.load_advanced_faiss(path)
