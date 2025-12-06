# FILE: multi_stage_faiss_searcher.py

import os
import json
import numpy as np
import faiss
import re
from typing import List, Dict, Any, Tuple

from langchain_core.documents import Document
from sentence_transformers import SentenceTransformer

from logic.pipeline.retrieval.util.retrieval.stages.common.chunk_relevance_filter import ChunkRelevanceFilter


class MultiStageFaissSearcher:
    def __init__(self, faiss_cfg,rerankers_cfg, docs_path, bot_profile, top_k_faiss, logger):
        self.faiss_cfg = faiss_cfg
        self.rerankers_cfg=rerankers_cfg
        self.top_k_faiss = top_k_faiss
        self.docs_path = docs_path
        self.bot_profile = bot_profile
        self.logger = logger

        # Load model once at init
        self.model = SentenceTransformer(self.faiss_cfg["embedding_model"])
        self.normalize_embeddings = self.faiss_cfg.get("normalize_L2", True)
        self.chunk_relevance_filter=ChunkRelevanceFilter(self.rerankers_cfg["chunk_filter_model"])

    def _get_temp_FAISS(self, folder_path: str) -> Tuple[faiss.IndexFlatIP, List[str], List[Dict]]:
        """
        Build temporary in-memory FAISS index from a single folder.
        Returns: (index, chunks_list, metadata_list)
        """
        all_emb = []
        all_chunks = []
        all_meta = []

        for root, _, files in os.walk(folder_path):
            c = os.path.join(root, "chunks.txt")
            m = os.path.join(root, "metadata.json")
            e = os.path.join(root, "embeddings.npy")

            if not (os.path.isfile(c) and os.path.isfile(m) and os.path.isfile(e)):
                continue

            raw = open(c, encoding="utf-8").read()
            chunks = [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]
            meta = json.load(open(m, encoding="utf-8"))
            emb = np.load(e).astype("float32")

            # LOG: added folder + chunk count + preview
            #self.logger.debug(f"[ADD] {folder_path}  chunks={len(chunks)}")

            all_chunks.extend(chunks)
            all_meta.extend(meta)
            all_emb.append(emb)

        if not all_emb:
            raise ValueError(f"No embeddings in {folder_path}")

        all_emb = np.vstack(all_emb)
        faiss.normalize_L2(all_emb)

        dim = all_emb.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(all_emb)

        return index, all_chunks, all_meta

    def _log_kept_docs(self, filtered_docs, folder):
        for rank, doc in enumerate(filtered_docs, start=1):
            text = doc.page_content

            preview = text.replace("\n", " ").strip()[:120]
            if len(text) > 120:
                preview += "..."

            self.logger.debug(
                f"[KEEP] {folder} | top={rank} | preview: {preview}"
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

            '''
            preview = chunk_text.replace("\n", " ").strip()[:120]
            if len(chunk_text) > 120:
                preview += "..."
            self.logger.debug(
                f"[MATCH] {folder} | rank={rank:02d} | sim={similarity:.4f} | preview: {preview}"
            )
            '''

            results.append(Document(
                page_content=chunk_text,
                metadata={
                    **metas[idx],
                    "source_folder": folder,
                    "faiss_similarity": float(similarity),
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

        self.logger.debug(f"[RELEVANT] {folder}: kept {len(filt_docs)} chunks")

        self._log_kept_docs( filt_docs, folder)

        return filt_docs

    def run_faiss_search(self, query: str):
        root_path = os.path.join(self.docs_path, self.bot_profile)

        inner_folders = [
            f for f in os.listdir(root_path)
            if os.path.isdir(os.path.join(root_path, f))
        ]

        all_results = []

        for folder in inner_folders:
            folder_path = os.path.join(root_path, folder)
            self.logger.info(f"--- Processing folder: {folder} ---")

            try:
                index, chunks, meta = self._get_temp_FAISS(folder_path)
            except Exception as e:
                self.logger.error(f"[SKIP] {folder}: {e}")
                continue

            try:
                faiss_hits = self._run_search(query, index, chunks, meta,folder)
                all_results.extend(faiss_hits)  # flatten
            except Exception as e:
                self.logger.error(f"[SEARCH ERROR] {folder}: {e}")
                continue

        return all_results