"""
Build Vectorstore for RAG 2.0 (Multi-Stage, BGE-large)
------------------------------------------------------
Loads:
 - chunks.txt
 - metadata.json
 - embeddings.npy
Builds FAISS index + docstore + id_map.

This script replaces the legacy version.
"""

import os
import sys
import json
import numpy as np
import faiss
import pickle
from datetime import datetime
from common.config.settings import get_settings


# ---------------------------------------------------------
# Logging helper
# ---------------------------------------------------------
def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[RAG2-BUILD] {ts} | {msg}")


# ---------------------------------------------------------
# Load chunks + metadata + embeddings for one document
# ---------------------------------------------------------
def load_artifacts(doc_folder: str):
    chunks_path = os.path.join(doc_folder, "chunks.txt")
    metadata_path = os.path.join(doc_folder, "metadata.json")
    embeddings_path = os.path.join(doc_folder, "embeddings.npy")

    # Basic file checks
    if not (os.path.exists(chunks_path) and os.path.exists(metadata_path) and os.path.exists(embeddings_path)):
        log(f"⚠️ Missing artifacts → {doc_folder}")
        return None, None, None

    # Load embeddings
    try:
        embeddings = np.load(embeddings_path)
    except Exception as e:
        log(f"⚠️ Error loading embeddings → {doc_folder} | {e}")
        return None, None, None

    # Validate embeddings
    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        log(f"⚠️ Invalid embeddings shape {embeddings.shape} → {doc_folder}")
        return None, None, None

    dim = embeddings.shape[1]
    if dim not in (384, 768, 1024):
        log(f"⚠️ Unsupported embedding dim={dim} → {doc_folder}")
        return None, None, None

    # Load chunks
    with open(chunks_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        chunks = [x.strip() for x in raw.split("\n\n") if x.strip()]

    # Load metadata
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if len(chunks) != embeddings.shape[0] or len(metadata) != embeddings.shape[0]:
        log(f"⚠️ Size mismatch → {doc_folder}")
        return None, None, None

    return chunks, metadata, embeddings


# ---------------------------------------------------------
# Create FAISS index (cosine similarity)
# ---------------------------------------------------------
def build_faiss_index(all_embeddings: np.ndarray):
    dim = all_embeddings.shape[1]
    log(f"🔧 Normalizing embeddings ({dim}d)…")
    faiss.normalize_L2(all_embeddings)

    log(f"🔧 Building FAISS IndexFlatIP ({dim}d)…")
    index = faiss.IndexFlatIP(dim)
    index.add(all_embeddings)
    return index


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------
def main():
    if len(sys.argv) < 2:
        print("Usage: python build_vectorstore_rag2.py <rag_output_folder>")
        sys.exit(1)

    rag_root = sys.argv[1]

    if not os.path.exists(rag_root):
        log(f"❌ Folder not found: {rag_root}")
        sys.exit(1)

    settings = get_settings()
    bot_profile = settings.bot_profile
    base_vector_root = settings.bot_profile_root_path

    log(f"🤖 BOT_PROFILE = {bot_profile}")
    log(f"📁 Reading RAG output: {rag_root}")

    # Gather folders
    subfolders = sorted(
        os.path.join(rag_root, d)
        for d in os.listdir(rag_root)
        if os.path.isdir(os.path.join(rag_root, d))
    )

    log(f"📄 Found {len(subfolders)} document folders.")

    all_chunks = []
    all_metadata = []
    all_embeddings = []

    # -----------------------------------------------------
    # Load artifacts
    # -----------------------------------------------------
    for folder in subfolders:
        log(f"📥 Loading {folder}")

        chunks, metadata, embeddings = load_artifacts(folder)

        if chunks is None:
            log(f"⏭️ Skipping {folder}")
            continue

        all_chunks.extend(chunks)
        all_metadata.extend(metadata)
        all_embeddings.append(embeddings)

    # -----------------------------------------------------
    # Final aggregation
    # -----------------------------------------------------
    if len(all_chunks) == 0:
        log("❌ No valid artifacts found. Exiting.")
        sys.exit(1)

    all_embeddings = np.vstack(all_embeddings)

    log(f"📊 Total chunks: {len(all_chunks)}")
    log(f"📊 Embeddings shape: {all_embeddings.shape}")

    # Build FAISS
    index = build_faiss_index(all_embeddings)

    # -----------------------------------------------------
    # Save vectorstore
    # -----------------------------------------------------
    out_dir = os.path.join(base_vector_root, bot_profile)
    os.makedirs(out_dir, exist_ok=True)

    faiss_path = os.path.join(out_dir, "index.faiss")
    meta_path = os.path.join(out_dir, "index.pkl")

    log(f"💾 Saving FAISS → {faiss_path}")
    faiss.write_index(index, faiss_path)

    # Build docstore
    log("🗃️ Building docstore + id_map…")

    id_map = {i: str(i) for i in range(len(all_chunks))}
    docstore = {str(i): all_chunks[i] for i in range(len(all_chunks))}

    meta_obj = {
        "chunks": all_chunks,
        "metadata": all_metadata,
        "index_to_docstore_id": id_map,
        "docstore": docstore,
    }

    log(f"🧩 id_map size = {len(id_map)}")
    log(f"🧩 docstore size = {len(docstore)}")

    with open(meta_path, "wb") as f:
        pickle.dump(meta_obj, f)

    log(f"✅ Metadata saved → {meta_path}")
    log("🎉 DONE — RAG 2.0 Vectorstore built successfully.")


if __name__ == "__main__":
    main()
