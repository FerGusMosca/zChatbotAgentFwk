# FILE: multi_stage_faiss_searcher.py
import glob
import os
import json
import numpy as np
import faiss
import re
from typing import List, Dict, Any, Tuple

from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer
from collections import defaultdict
from logic.pipeline.retrieval.util.retrieval.stages.common.chunk_relevance_filter import ChunkRelevanceFilter
from logic.pipeline.retrieval.util.retrieval.util.dominance_detector import DominanceDetector
from logic.pipeline.retrieval.util.retrieval.util.retrieval_logger import RetrievalLogger


class MultiStageFaissSearcher:
    def __init__(self, faiss_cfg,rerankers_cfg, docs_path, bot_profile, top_k_faiss, std_out_logger
                ,dump_on_logs=False,dump_log_file=None):
        self.faiss_cfg = faiss_cfg
        self.rerankers_cfg=rerankers_cfg
        self.top_k_faiss = top_k_faiss
        self.docs_path = docs_path
        self.bot_profile = bot_profile
        self.std_out_logger = std_out_logger
        self.file_logger=RetrievalLogger(dump_on_logs,dump_log_file)

        # Load model once at init
        self.model = SentenceTransformer(self.faiss_cfg["embedding_model"])
        self.normalize_embeddings = self.faiss_cfg.get("normalize_L2", True)
        self.chunk_relevance_filter=ChunkRelevanceFilter(self.rerankers_cfg["chunk_filter_model"])

    def _get_temp_FAISS(self, folder_path: str) -> Tuple[faiss.IndexFlatIP, List[str], List[Dict]]:
        """
        Build a temporary in-memory FAISS index from all subfolders under folder_path.
        Extremely robust against spaces, quotes, special chars, etc.
        Logs every skip and every successful load.
        """
        all_emb = []
        all_chunks = []
        all_meta = []

        # Fast and bullet-proof way: find every embeddings.npy recursively
        pattern = os.path.join(folder_path, "**", "embeddings.npy")
        for emb_path in glob.iglob(pattern, recursive=True):
            root_dir = os.path.dirname(emb_path)

            chunks_path = os.path.join(root_dir, "chunks.txt")
            meta_path = os.path.join(root_dir, "metadata.json")

            # --- Skip + log if any file is missing ---
            if not os.path.isfile(chunks_path):
                self.std_out_logger.debug(f"[FAISS_SKIP] {root_dir} → missing chunks.txt")
                continue
            if not os.path.isfile(meta_path):
                self.std_out_logger.debug(f"[FAISS_SKIP] {root_dir} → missing metadata.json")
                continue

            # --- All three files exist → load them safely ---
            try:
                # Load text chunks
                with open(chunks_path, "r", encoding="utf-8") as f:
                    raw = f.read()
                chunks = [c.strip() for c in re.split(r"\n\s*\n", raw) if c.strip()]

                # Load metadata
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)

                # Load embeddings
                embeddings = np.load(emb_path).astype("float32")

                # Append to global lists
                all_chunks.extend(chunks)
                all_meta.extend(metadata)
                all_emb.append(embeddings)

                self.std_out_logger.debug(f"[FAISS_LOADED] {root_dir} → {len(chunks)} chunks")

            except Exception as exc:
                self.std_out_logger.debug(f"[FAISS_ERROR] {root_dir} → {exc}")
                continue

        # --- Final checks ---
        if not all_emb:
            raise ValueError(f"No valid shards found under {folder_path}")

        all_emb = np.vstack(all_emb)
        faiss.normalize_L2(all_emb)

        index = faiss.IndexFlatIP(all_emb.shape[1])
        index.add(all_emb)

        return index, all_chunks, all_meta

    def _log_kept_docs(self, filtered_docs, folder):
        for rank, doc in enumerate(filtered_docs, start=1):
            text = doc.page_content
            source = doc.metadata.get("source_pdf", "UNKNOWN")

            self.file_logger.print_to_file_chunk_(
                source="FAISS",
                folder=folder,
                rank=rank,
                text=text,
                pdf=source
            )

    def _result_to_document(
            self,
            distances: np.ndarray,
            indices: np.ndarray,
            chunks: List[str],
            metas: List[Dict],
            folder: str,  # ← nuevo parámetro para saber de qué banco viene
    ) -> List[Document]:
        """Convert FAISS raw output → LangChain Document list + LOG del chunk matcheado"""
        results = []

        for rank, (dist, idx) in enumerate(zip(distances, indices), start=1):
            if idx == -1:
                continue

            similarity = 1.0 - dist
            chunk_text = chunks[idx]

            results.append(Document(
                page_content=chunk_text,
                metadata={
                    **metas[idx],
                    "source_folder": folder,
                    "faiss_similarity": float(similarity),
                    "dominance_score": float(similarity),
                    "faiss_distance": float(dist),
                    "faiss_rank": rank,
                }
            ))

        return results

    def _run_search(
            self,
            query: str,
            index: faiss.IndexFlatIP,
            chunks: List[str],
            metas: List[Dict],
            folder: str
    ) -> List[Document]:
        """Run FAISS search on a single bank folder and filter relevant chunks."""

        # --- Encode query ---
        query_vec = self.model.encode(
            [query],
            normalize_embeddings=self.normalize_embeddings,
        ).astype("float32")

        if not self.normalize_embeddings:
            query_vec = query_vec / np.linalg.norm(query_vec, axis=1, keepdims=True)

        # --- FAISS search ---
        distances, indices = index.search(query_vec, self.top_k_faiss)

        # --- Convert FAISS results to Document objects ---
        retrieved_docs = self._result_to_document(
            distances=distances[0],
            indices=indices[0],
            chunks=chunks,
            metas=metas,
            folder=folder
        )

        # --- Cross-encoder scores ---
        scores = self.chunk_relevance_filter.is_relevant(
            query=query,
            docs=retrieved_docs,
        )

        # --- Take TOP-3 documents ---
        top_k = self.rerankers_cfg["top_chunks"]
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        filt_docs = [retrieved_docs[i] for i in top_indices]

        self.std_out_logger.debug(f"[RELEVANT] {folder}: kept {len(filt_docs)} chunks")

        self._log_kept_docs( filt_docs, folder)

        return filt_docs

    def detect_dominance_and_filter(self, docs: List[Document], gap_threshold=3.0):
        """
        Detect a dominant similarity cluster using FAISS similarities only.
        If a large gap is found, keep ONLY the dominant chunks.
        """

        if len(docs) < 3:
            return docs, False

        # 1) Sort by similarity (ONLY variable that matters)
        docs_sorted = sorted(
            docs,
            key=lambda d: d.metadata.get("faiss_similarity", 0.0),
            reverse=True
        )

        sims = [d.metadata.get("faiss_similarity", 0.0) for d in docs_sorted]

        # 2) Compute similarity gaps
        gaps = []
        for i in range(len(sims) - 1):
            ratio = sims[i] / max(sims[i + 1], 1e-9)
            gaps.append(ratio)

        # 3) Find largest gap
        max_gap = max(gaps)
        max_idx = gaps.index(max_gap)

        # 4) No dominance
        if max_gap < gap_threshold:
            return docs, False

        # 5) Dominant cluster = chunks 0..max_idx
        dominant_docs = docs_sorted[:max_idx + 1]

        return dominant_docs, True

    def run_faiss_search(self, query: str):
        root_path = os.path.join(self.docs_path, self.bot_profile)

        inner_folders = [
            f for f in os.listdir(root_path)
            if os.path.isdir(os.path.join(root_path, f))
        ]

        all_results = []

        self.file_logger.init_log_dump_file("FAISS")
        self.file_logger.print_to_file_query_(query)

        for folder in inner_folders:
            folder_path = os.path.join(root_path, folder)
            self.std_out_logger.info(f"--- Processing folder: {folder} ---")

            try:
                index, chunks, meta = self._get_temp_FAISS(folder_path)
            except Exception as e:
                self.std_out_logger.error(f"[SKIP] {folder}: {e}")
                continue

            try:
                faiss_hits = self._run_search(query, index, chunks, meta,folder)
                all_results.extend(faiss_hits)  # flatten
            except Exception as e:
                self.std_out_logger.error(f"[SEARCH ERROR] {folder}: {e}")
                continue


        #all_results,dom_detected= DominanceDetector.detect_dominance_and_filter(all_results,self.std_out_logger)
        self.file_logger.close_log_dump_file()
        return all_results