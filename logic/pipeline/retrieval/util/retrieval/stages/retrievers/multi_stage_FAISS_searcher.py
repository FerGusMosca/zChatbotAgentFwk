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
from service_client.cross_encoder_client.cross_encoder_client import CrossEncoderClient


class MultiStageFaissSearcher:
    def __init__(self, rerankers_cfg, docs_path, bot_profile, top_k_faiss, std_out_logger
                ,dump_on_logs=False,dump_log_file=None, tester=None):

        self.rerankers_cfg=rerankers_cfg
        self.top_k_faiss = top_k_faiss
        self.docs_path = docs_path
        self.bot_profile = bot_profile
        self.std_out_logger = std_out_logger
        self.use_cross_encoders_thresholds=rerankers_cfg["use_cross_encoders_thresholds"]
        self.file_logger=RetrievalLogger(dump_on_logs,dump_log_file)

        # Load model once at init
        self.model = SentenceTransformer(self.rerankers_cfg["chunk_exploration_model"])
        self.normalize_embeddings = self.rerankers_cfg.get("normalize_L2", True)


        self.index_cache = {}  # Dictionary to cache {folder_name: (faiss_index, chunks_list, metadata_list)}
        self.preloaded = {}  #  track if all indices have been preloaded already

        self.use_run_pod_GPU_for_cross_encoder=self.rerankers_cfg["use_run_pod_GPU_for_cross_encoder"]
        if self.use_run_pod_GPU_for_cross_encoder:
            self.cross_encoder_client= CrossEncoderClient(self.rerankers_cfg["run_pod_url"],self.rerankers_cfg["run_pod_api"],
                                                          self.std_out_logger)
        else:
            self.chunk_relevance_filter = ChunkRelevanceFilter(self.rerankers_cfg["chunk_filter_model"])

        #Tester
        self.tester=tester

        self._load_cross_encoder_thresholds()
        pass

    def _load_cross_encoder_thresholds(self):
        """Load cross-encoder thresholds from rerankers_cfg. Raise error if missing."""
        if "cross_encoder_thresholds" not in self.rerankers_cfg:
            raise KeyError(
                "Missing required section 'cross_encoder_thresholds' in rerankers_cfg. "
                "Add it to the config with thresholds per query type."
            )

        thresholds = self.rerankers_cfg["cross_encoder_thresholds"]
        required_keys = {
            "broad_query",
            "enumeration_query",
            "analytical_query",
            "temporal_query",
            "specific_query",
            "fuzzy_query"
        }

        missing = required_keys - thresholds.keys()
        if missing:
            raise KeyError(f"Missing query types in cross_encoder_thresholds: {missing}")

        self.cross_encoder_thresholds = thresholds

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

    def _filt_fix_cross_encoders(self,folder,query,retrieved_docs,scores,retr_id):
        # --- Take TOP-K documents ---
        top_k = self.rerankers_cfg["top_cross_encoders_chunks"]
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        filt_docs = [retrieved_docs[i] for i in top_indices]

        self.std_out_logger.debug(f"[RELEVANT] {folder}: kept {len(filt_docs)} chunks")

        self._log_kept_docs(filt_docs, folder)

        self.tester.evaluate_persist_cross_encoder_chunks(retr_id=retr_id, folder="ALL", stage="cross_encoder_filtered",
                                                          query=query, docs=filt_docs)

        return filt_docs

    def _filt_cross_encoders_thresholds(self, folder,query, query_label, retrieved_docs, scores,retr_id):
        """
        Filter docs using threshold based on query type.
        """
        # Get threshold for the query type
        try:
            threshold = self.cross_encoder_thresholds[query_label.value]
        except KeyError:
            raise KeyError(f"Unknown query type: {query_label.value}. "
                           f"Available: {list(self.cross_encoder_thresholds.keys())}")

        # Pair docs with scores and filter those above threshold
        paired = list(zip(retrieved_docs, scores))
        filt_paired = [(doc, score) for doc, score in paired if score > threshold]

        # Sort descending by score (best first)
        filt_paired.sort(key=lambda x: x[1], reverse=True)

        # Extract filtered docs
        filt_docs = [doc for doc, _ in filt_paired]

        # Log
        kept = len(filt_docs)
        self.std_out_logger.debug(
            f"[RELEVANT] {folder}: threshold={threshold:.2f} ({query_label.value}) → kept {kept} chunks")

        self._log_kept_docs(filt_docs, folder)
        self.tester.evaluate_persist_cross_encoder_chunks(retr_id=retr_id, folder="ALL", stage="cross_encoder_filtered",
                                                          query=query, docs=filt_docs)

        # Fallback: if nothing passes threshold, keep the best one
        if kept == 0 and retrieved_docs:
            best_idx = scores.index(max(scores))
            filt_docs = [retrieved_docs[best_idx]]
            self.std_out_logger.debug(f"[RELEVANT] {folder}: fallback to best chunk (score={max(scores):.4f})")

        return filt_docs

    def _get_query_vec(self,query):
        query_vec = self.model.encode(
            [query],
            normalize_embeddings=self.normalize_embeddings,
        ).astype("float32")

        if not self.normalize_embeddings:
            query_vec = query_vec / np.linalg.norm(query_vec, axis=1, keepdims=True)

        return query_vec

    def _run_search(
            self,
            query: str,
            query_vec,
            query_label:str,
            index: faiss.IndexFlatIP,
            chunks: List[str],
            metas: List[Dict],
            folder: str,
            retr_id
    ) -> List[Document]:
        """Run FAISS search on a single bank folder and filter relevant chunks."""

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

        self.tester.evaluate_persist_bi_encoder_chunks(retr_id, retrieved_docs,"bi_encoder")
        '''
        # --- Cross-encoder scores ---
        scores = self.chunk_relevance_filter.is_relevant(
            folder=folder,
            query=query,
            docs=retrieved_docs,
            file_logger=self.file_logger
        )
        self.tester.evaluate_bi_encoder_retrieval(query,folder,retrieved_docs)

        if self.use_cross_encoders_thresholds:
            return self._filt_cross_encoders_thresholds(folder,query,query_label,retrieved_docs,scores)
        else:
            return  self._filt_fix_cross_encoders(folder,retrieved_docs,scores)
        '''
        return retrieved_docs


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

    def _preload_all_indices(self, root_path: str):
        """
        Preload all FAISS indices from every bank folder once at startup.
        Loads embeddings, chunks, and metadata into RAM for instant access.
        """
        if root_path in self.preloaded:
            return  # Skip if already preloaded
        self.std_out_logger.info(f"[PRELOAD] Starting preload of all indices from {root_path}")
        inner_folders = [
            f for f in os.listdir(root_path)
            if os.path.isdir(os.path.join(root_path, f))
        ]
        for folder in inner_folders:
            folder_path = os.path.join(root_path, folder)
            try:
                # Reuse existing _get_temp_FAISS to build the index
                index, chunks, meta = self._get_temp_FAISS(folder_path)
                self.index_cache[folder] = (index, chunks, meta)
                self.std_out_logger.info(f"[PRELOAD] {folder}: {index.ntotal} chunks loaded into memory")
            except Exception as e:
                self.std_out_logger.error(f"[PRELOAD ERROR] {folder}: {e}")
        self.preloaded[root_path] = True
        self.std_out_logger.info(f"[PRELOAD] Completed. {len(self.index_cache)} banks now in memory.")

    def run_faiss_search(self, query: str, query_label: str, dynamic_chunks_folder=None,retr_id=None):
        """
        Execute FAISS search with full in-memory preloading.
        First call: preloads all data (slow). Subsequent calls: pure search (fast).
        """
        # Determine root path
        if dynamic_chunks_folder is not None:
            root_path = dynamic_chunks_folder
        else:
            root_path = self.docs_path

        # Preload everything into memory (only once)
        self._preload_all_indices(root_path)

        # Now everything is in RAM → log correct status
        self.std_out_logger.info(
            f"--- FAISS- Searching across {len(self.index_cache)} preloaded folders in {root_path} ---")

        all_results = []
        self.file_logger.init_log_dump_file("FAISS")
        self.file_logger.print_to_file_query_(query)
        query_vec = self._get_query_vec(query)

        # Pure in-memory search loop
        for folder, (index, chunks, meta) in self.index_cache.items():
            try:
                faiss_hits = self._run_search(query, query_vec, query_label, index, chunks, meta, folder,retr_id)
                all_results.extend(faiss_hits)
            except Exception as e:
                self.std_out_logger.error(f"[SEARCH ERROR] {folder}: {e}")

            # --- Cross-encoder scores ---
        self.std_out_logger.info(f"[STARTING_CROSS_ENCODER] --> to process: {len(all_results)}")


        if self.use_run_pod_GPU_for_cross_encoder:
            scores =self.cross_encoder_client.is_relevant(folder="ALL",query=query,docs=all_results,file_logger=self.file_logger)
        else:
            scores = self.chunk_relevance_filter.is_relevant(
                folder="ALL",
                query=query,
                docs=all_results,
                file_logger=self.file_logger
            )
        self.std_out_logger.info(f"[CROSS_ENCODER_FINISHED]: processed {len(all_results)}")

        self.tester.evaluate_bi_encoder_retrieval(query, "ALL", all_results)
        self.tester.evaluate_persist_cross_encoder_chunks(retr_id=retr_id,folder="ALL",stage="cross_encoder",query=query,docs=all_results)

        if self.use_cross_encoders_thresholds:
            all_results= self._filt_cross_encoders_thresholds("ALL", query, query_label, all_results, scores,retr_id)
        else:
            all_results= self._filt_fix_cross_encoders("ALL",query, all_results, scores,retr_id)

        self.std_out_logger.info(f"[CROSS_ENCODER_FILTERS_FINISHED]: OUT {len(all_results)}")
        self.tester.evaluate_cross_encoder_retrieval(query, query_label, all_results)
        self.file_logger.close_log_dump_file()
        return all_results