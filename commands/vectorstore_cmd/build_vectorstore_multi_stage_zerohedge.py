"""
Build Vectorstore for ZEROHEDGE Multi-Stage RAG
------------------------------------------------
Loads artifacts for each document:
 - chunks.txt
 - metadata.json
 - embeddings.npy

Builds:
 - FAISS index (cosine similarity)
 - docstore
 - id_map
 - metadata bundle

Logs everything into FAISS_generation_logs.
"""

import os
import sys
import json
import pickle
import numpy as np
import faiss
from datetime import datetime
from common.config.settings import get_settings


# ============================================================
# Logging helper
# ============================================================
def log(msg: str, logfile=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[VS-BUILD] {ts} | {msg}"
    print(line)
    if logfile:
        logfile.write(line + "\n")
        logfile.flush()


# ============================================================
# Load artifacts for one folder
# ============================================================
def load_artifacts(doc_folder: str, logger):
    chunks_path = os.path.join(doc_folder, "chunks.txt")
    metadata_path = os.path.join(doc_folder, "metadata.json")
    embeddings_path = os.path.join(doc_folder, "embeddings.npy")

    if not (
        os.path.exists(chunks_path)
        and os.path.exists(metadata_path)
        and os.path.exists(embeddings_path)
    ):
        logger(f"⚠️ Missing artifacts → {doc_folder}")
        return None, None, None

    try:
        embeddings = np.load(embeddings_path)
    except Exception as e:
        logger(f"⚠️ Error loading embeddings → {doc_folder} | {e}")
        return None, None, None

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        logger(f"⚠️ Invalid embeddings shape {embeddings.shape} → {doc_folder}")
        return None, None, None

    dim = embeddings.shape[1]
    if dim not in (384, 768, 1024):
        logger(f"⚠️ Unsupported embedding dimension: {dim} → {doc_folder}")
        return None, None, None

    with open(chunks_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
        chunks = [x.strip() for x in raw.split("\n\n") if x.strip()]

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if len(chunks) != embeddings.shape[0]:
        logger(f"⚠️ Size mismatch: chunks={len(chunks)} emb={embeddings.shape[0]} → {doc_folder}")
        return None, None, None

    if len(metadata) != embeddings.shape[0]:
        logger(f"⚠️ Size mismatch: metadata={len(metadata)} emb={embeddings.shape[0]}")
        return None, None, None

    return chunks, metadata, embeddings


# ============================================================
# Build FAISS (cosine similarity)
# ============================================================
def build_faiss_index(all_embeddings: np.ndarray, logger):
    dim = all_embeddings.shape[1]
    logger(f"🔧 Normalizing embeddings ({dim}d)…")
    faiss.normalize_L2(all_embeddings)

    logger(f"🔧 Building IndexFlatIP ({dim}d)…")
    index = faiss.IndexFlatIP(dim)
    index.add(all_embeddings)

    return index


# ============================================================
# MAIN ENTRY
# ============================================================
def main():
    # ========== Parse CLI args ==========
    if len(sys.argv) < 2:
        print("Usage:")
        print("python build_vectorstore_multi_stage_zerohedge.py <inner_folder_under_documents>")
        sys.exit(1)

    inner_folder = sys.argv[1]

    # ========== Load settings ==========
    settings = get_settings()
    bot_profile_root = settings.bot_profile_root_path
    bot_profile = settings.bot_profile
    documents_root = os.path.join(settings.index_files_root_path,bot_profile)

    # Example:
    # documents_root = "C:\\zzLotteryTicket\\documents"
    # inner_folder   = "ZEROHEDGE_RAG/Archives/2025/November/Nov 6"

    rag_folder = os.path.join(documents_root, inner_folder)

    if not os.path.exists(rag_folder):
        print(f"❌ Folder does not exist: {rag_folder}")
        sys.exit(1)

    # ========== Prepare output logging ==========
    log_root = os.path.join(documents_root, bot_profile, "FAISS_generation_logs")
    os.makedirs(log_root, exist_ok=True)

    log_file_path = os.path.join(
        log_root,
        f"vs_build_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
    )
    lf = open(log_file_path, "a", encoding="utf-8")

    def logger(msg): log(msg, lf)

    logger(f"🚀 START Vectorstore Build for ZEROHEDGE Multi-Stage")
    logger(f"📁 Reading from: {rag_folder}")

    # ========== Collect document folders ==========
    doc_folders = []

    for root, dirs, files in os.walk(rag_folder):
        for d in dirs:
            full = os.path.join(root, d)
            if any(
                os.path.exists(os.path.join(full, fname))
                for fname in ("chunks.txt", "metadata.json", "embeddings.npy")
            ):
                doc_folders.append(full)

    logger(f"📄 Document folders detected: {len(doc_folders)}")

    all_chunks = []
    all_metadata = []
    embedded_blocks = []

    # ========== Load all artifacts ==========
    for folder in doc_folders:
        logger(f"📥 Loading → {folder}")

        chunks, metadata, embeddings = load_artifacts(folder, logger)

        if chunks is None:
            logger(f"⏭️ Skipping {folder}")
            continue

        all_chunks.extend(chunks)
        all_metadata.extend(metadata)
        embedded_blocks.append(embeddings)

    if len(embedded_blocks) == 0:
        logger("❌ No valid artifacts found. Aborting.")
        lf.close()
        sys.exit(1)

    # ========== Stack embeddings ==========
    all_embeddings = np.vstack(embedded_blocks)
    logger(f"📊 Total chunks: {len(all_chunks)}")
    logger(f"📊 All embeddings shape: {all_embeddings.shape}")

    # ========== Build FAISS ==========
    index = build_faiss_index(all_embeddings, logger)

    # ========== Save vectorstore ==========
    out_dir = os.path.join(bot_profile_root, bot_profile)
    os.makedirs(out_dir, exist_ok=True)

    faiss_path = os.path.join(out_dir, "index.faiss")
    meta_path = os.path.join(out_dir, "index.pkl")

    logger(f"💾 Saving FAISS → {faiss_path}")
    faiss.write_index(index, faiss_path)

    # Build docstore + id map
    logger("🗃️ Building docstore + id_map…")

    id_map = {i: str(i) for i in range(len(all_chunks))}
    docstore = {str(i): all_chunks[i] for i in range(len(all_chunks))}

    bundle = {
        "chunks": all_chunks,
        "metadata": all_metadata,
        "index_to_docstore_id": id_map,
        "docstore": docstore,
    }

    with open(meta_path, "wb") as f:
        pickle.dump(bundle, f)

    logger(f"✅ Metadata saved → {meta_path}")
    logger("🎉 DONE — ZEROHEDGE Vectorstore built successfully.")

    lf.close()


if __name__ == "__main__":
    main()
