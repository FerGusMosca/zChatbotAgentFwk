"""
Build Vectorstore for ZEROHEDGE Multi-Stage RAG - FULLY CONFIG-DRIVEN
--------------------------------------------------------------------
- Forces bge-large-en-v1.5 (384 dim) via sacred JSON config
- Explodes instantly on any deviation
- Copies the config alongside the index so loader never has to guess
All comments in English.
"""

import os
import sys
import json
import pickle
import numpy as np
import faiss
from datetime import datetime
from pathlib import Path
from common.config.settings import get_settings


# ============================================================
# SACRED CONFIG (single source of truth)xxx
# ============================================================
from pathlib import Path

# From this file: build_...py → vectorstore_cmd → commands → project root
CONFIG_PATH = Path("/app/config/FAISS_config/bge-large-en-v1.5.json")

if not CONFIG_PATH.exists():
    raise FileNotFoundError(f"[FATAL] Missing mandatory config: {CONFIG_PATH}")

with open(CONFIG_PATH) as f:
    CFG = json.load(f)

# Hard expectations - any deviation = instant death
EXPECTED_DIM = CFG["dimensions"]                     # 1024
EXPECTED_METRIC = faiss.METRIC_INNER_PRODUCT         # matches IndexFlatIP
EXPECTED_INDEX_TYPE = "IndexFlatIP"


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
# Load artifacts + strict dimension validation
# ============================================================
def load_artifacts(doc_folder: str, logger):
    chunks_path = os.path.join(doc_folder, "chunks.txt")
    metadata_path = os.path.join(doc_folder, "metadata.json")
    embeddings_path = os.path.join(doc_folder, "embeddings.npy")

    if not all(os.path.exists(p) for p in (chunks_path, metadata_path, embeddings_path)):
        logger(f"Missing artifacts → {doc_folder}")
        return None, None, None

    try:
        embeddings = np.load(embeddings_path, mmap_mode="r")
    except Exception as e:
        logger(f"Error loading embeddings → {doc_folder} | {e}")
        return None, None, None

    if embeddings.ndim != 2 or embeddings.shape[0] == 0:
        logger(f"Invalid embeddings shape {embeddings.shape} → {doc_folder}")
        return None, None, None

    dim = embeddings.shape[1]
    if dim != EXPECTED_DIM:
        raise ValueError(
            f"[FATAL] Dimension mismatch in {doc_folder}!\n"
            f"    Expected: {EXPECTED_DIM} (bge-large-en-v1.5)\n"
            f"    Found:    {dim}\n"
            f"    Update your embedding model or config."
        )

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = [x.strip() for x in f.read().strip().split("\n\n") if x.strip()]

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    if len(chunks) != len(metadata) != embeddings.shape[0]:
        raise ValueError(f"[FATAL] Length mismatch in {doc_folder}")

    return chunks, metadata, embeddings.astype(np.float32)  # ensure type


# ============================================================
# Build FAISS - enforced cosine via normalized + IP
# ============================================================
def build_faiss_index(all_embeddings: np.ndarray, logger):
    dim = all_embeddings.shape[1]
    if dim != EXPECTED_DIM:
        raise RuntimeError("Logic error - dimension slipped through")

    logger(f"Normalizing L2 embeddings ({dim}d) - required for cosine...")
    faiss.normalize_L2(all_embeddings)

    logger(f"Building {EXPECTED_INDEX_TYPE} (cosine via Inner Product)...")
    index = faiss.IndexFlatIP(dim)   # Inner Product + normalized vectors = cosine
    index.add(all_embeddings)
    return index


# ============================================================
# MAIN
# ============================================================
def main():
    if len(sys.argv) < 2:
        print("Usage: python build_vectorstore_multi_stage_zerohedge.py <inner_folder_under_documents>")
        sys.exit(1)

    inner_folder = sys.argv[1]
    settings = get_settings()
    bot_profile = settings.bot_profile
    documents_root = os.path.join(settings.index_files_root_path, bot_profile)
    rag_folder = os.path.join(documents_root, inner_folder)

    if not os.path.exists(rag_folder):
        raise FileNotFoundError(f"Folder does not exist: {rag_folder}")

    # Logging
    log_root = os.path.join(settings.index_files_root_path, bot_profile, "FAISS_generation_logs")
    os.makedirs(log_root, exist_ok=True)
    log_file_path = os.path.join(log_root, f"vs_build_{datetime.now():%Y-%m-%d_%H-%M-%S}.log")
    lf = open(log_file_path, "a", encoding="utf-8")
    def logger(msg): log(msg, lf)

    logger(f"START ZEROHEDGE Vectorstore Build")
    logger(f"BUILD PARAMETER (inner_folder): {inner_folder}")
    logger(f"Config enforced: {CONFIG_PATH.name} (dim={EXPECTED_DIM}, cosine via IP)")

    # Collect folders
    doc_folders = [
        os.path.join(root, d)
        for root, dirs, _ in os.walk(rag_folder)
        for d in dirs
        if all(os.path.exists(os.path.join(root, d, f)) for f in ("chunks.txt", "metadata.json", "embeddings.npy"))
    ]

    logger(f"Found {len(doc_folders)} document folders")

    all_chunks = []
    all_metadata = []
    embedded_blocks = []

    for folder in doc_folders:
        logger(f"Loading → {folder}")
        chunks, metadata, embeddings = load_artifacts(folder, logger)
        if chunks is None:
            continue
        all_chunks.extend(chunks)
        all_metadata.extend(metadata)
        embedded_blocks.append(embeddings)

    if not embedded_blocks:
        logger("No valid artifacts found. Aborting.")
        lf.close()
        sys.exit(1)

    all_embeddings = np.vstack(embedded_blocks)
    logger(f"Total chunks: {len(all_chunks)} | Shape: {all_embeddings.shape}")

    index = build_faiss_index(all_embeddings, logger)

    # Output
    out_dir = os.path.join(settings.bot_profile_root_path, bot_profile)
    os.makedirs(out_dir, exist_ok=True)

    faiss_path = os.path.join(out_dir, "index.faiss")
    meta_path = os.path.join(out_dir, "index.pkl")
    config_dest = os.path.join(out_dir, "bge-large-en-v1.5.json")

    logger(f"Saving FAISS index → {faiss_path}")
    faiss.write_index(index, faiss_path)

    logger(f"Saving config → {config_dest}")
    with open(config_dest, "w", encoding="utf-8") as f:
        json.dump(CFG, f, indent=2)

    # Docstore
    id_map = {i: str(i) for i in range(len(all_chunks))}
    bundle = {
        "chunks": all_chunks,
        "metadata": all_metadata,
        "index_to_docstore_id": id_map,
    }
    with open(meta_path, "wb") as f:
        pickle.dump(bundle, f)

    logger(f"Metadata saved → {meta_path}")
    logger("DONE - Vectorstore built with zero ambiguity")
    lf.close()


if __name__ == "__main__":
    main()