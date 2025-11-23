"""
Build Vectorstore for ZeroHedge RAG
-----------------------------------
Loads curated artifacts:
 - chunks.txt
 - metadata.json
 - embeddings.npy
And builds a FAISS index.

Run:
    python build_vectorstore_rag_zerohdge.py "C:/Projects/Bias/research_apps/Quant_ML_Research_Platform/output/rag"
"""

import os
import sys
import json
import numpy as np
import faiss
import pickle
from common.config.settings import get_settings


def load_artifacts(doc_folder: str):
    """Load chunks, metadata and embeddings from a single document folder.
       Skips folders with empty or corrupted embeddings."""

    chunks_path = os.path.join(doc_folder, "chunks.txt")
    metadata_path = os.path.join(doc_folder, "metadata.json")
    embeddings_path = os.path.join(doc_folder, "embeddings.npy")

    if not (os.path.exists(chunks_path) and os.path.exists(metadata_path) and os.path.exists(embeddings_path)):
        print(f"[WARN] Missing artifact(s) in: {doc_folder}")
        return None, None, None

    try:
        embeddings = np.load(embeddings_path)
    except Exception as e:
        print(f"[WARN] Could not load embeddings in {doc_folder}: {e}")
        return None, None, None

    # Skip empty embeddings
    if embeddings.size == 0 or len(embeddings.shape) != 2:
        print(f"[SKIP] Empty or invalid embeddings in {doc_folder}")
        return None, None, None

    # Skip weird shaped embeddings (must be 384d)
    if embeddings.shape[1] != 384:
        print(f"[SKIP] Wrong embedding dimension in {doc_folder}: {embeddings.shape}")
        return None, None, None

    # Load chunks
    with open(chunks_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        chunks = [x.strip() for x in raw.split("\n\n") if x.strip()]

    # Load metadata
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    # Size mismatch check
    if len(chunks) != embeddings.shape[0] or len(metadata) != embeddings.shape[0]:
        print(f"[SKIP] Mismatch length in {doc_folder}")
        return None, None, None

    return chunks, metadata, embeddings


def build_faiss_index(all_embeddings: np.ndarray):
    """Create FAISS cosine similarity index (normalized + inner product)."""
    dim = all_embeddings.shape[1]
    faiss.normalize_L2(all_embeddings)
    index = faiss.IndexFlatIP(dim)
    index.add(all_embeddings)
    return index


def main():
    if len(sys.argv) < 2:
        print("Usage: python build_vectorstore_rag_zerohdge.py <path_to_rag_output>")
        sys.exit(1)

    rag_root = sys.argv[1]
    if not os.path.exists(rag_root):
        print(f"[ERROR] Folder not found: {rag_root}")
        sys.exit(1)

    settings = get_settings()
    bot_profile = settings.bot_profile  # <<<<<<<<<<<<<< 🔥 USE BOT_PROFILE
    print(f"\n[BOT] Using BOT_PROFILE = {bot_profile}")

    print(f"[ZEROHEDGE-RAG] Building vectorstore from: {rag_root}\n")

    all_chunks = []
    all_metadata = []
    all_embeddings = []

    subfolders = sorted(
        os.path.join(rag_root, d)
        for d in os.listdir(rag_root)
        if os.path.isdir(os.path.join(rag_root, d))
    )

    print(f"[INFO] Found {len(subfolders)} document folders.")

    for folder in subfolders:
        print(f"[LOAD] {folder}")
        chunks, metadata, embeddings = load_artifacts(folder)

        if chunks is None:
            print(f"[SKIP] {folder}")
            continue

        all_chunks.extend(chunks)
        all_metadata.extend(metadata)
        all_embeddings.append(embeddings)

    if len(all_chunks) == 0:
        print("[ERROR] No artifacts loaded. Nothing to index.")
        sys.exit(1)

    all_embeddings = np.vstack(all_embeddings)

    print(f"[INFO] Total chunks: {len(all_chunks)}")
    print(f"[INFO] Embeddings shape: {all_embeddings.shape}")

    index = build_faiss_index(all_embeddings)

    # 🔥 Save vectorstore into vectorstores/<BOT_PROFILE>
    root_base = settings.bot_profile_root_path  # <<<<<< usa el .env
    out_dir = os.path.join(root_base, bot_profile)
    os.makedirs(out_dir, exist_ok=True)


    faiss_path = os.path.join(out_dir, "index.faiss")
    meta_path = os.path.join(out_dir, "index.pkl")

    faiss.write_index(index, faiss_path)

    # ---------------------------------------------------------
    # Build full metadata for ADVANCED FAISS FORMAT
    # Comments in English
    # ---------------------------------------------------------
    print("[BUILD] Constructing id_map + docstore...")

    try:
        id_map = {i: str(i) for i in range(len(all_chunks))}
        docstore = {str(i): all_chunks[i] for i in range(len(all_chunks))}

        meta_obj = {
            "chunks": all_chunks,
            "metadata": all_metadata,
            "index_to_docstore_id": id_map,
            "docstore": docstore,
        }

        print(f"[BUILD] id_map size = {len(id_map)}")
        print(f"[BUILD] docstore size = {len(docstore)}")
        print(f"[BUILD] sample docstore keys = {list(docstore.keys())[:5]}")

        with open(meta_path, "wb") as f:
            pickle.dump(meta_obj, f)

        print(f"[OK] Metadata saved → {meta_path}")

    except Exception as ex:
        print(f"[ERROR] Failed to build metadata: {ex}")
        raise


if __name__ == "__main__":
    main()
