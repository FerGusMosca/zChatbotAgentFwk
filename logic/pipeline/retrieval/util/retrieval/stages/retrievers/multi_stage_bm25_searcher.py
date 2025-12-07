# FILE: multi_stage_bm25_searcher.py
# All comments MUST be in English.

import os
import json
import re
from typing import List, Dict, Tuple

from langchain_core.documents import Document
from langchain_community.retrievers import BM25Retriever

from logic.pipeline.retrieval.util.retrieval.util.dominance_detector import DominanceDetector
from logic.pipeline.retrieval.util.retrieval.util.retrieval_logger import RetrievalLogger

# ---------------------------------------------------------
# Static filenames (do NOT place in config)
# ---------------------------------------------------------
_CHUNKS_FILE = "chunks.txt"
_METADATA_FILE = "metadata.json"


class MultiStageBM25Searcher:
    """
    BM25 sharded retrieval.
    This mirrors the structure of MultiStageFaissSearcher but performs
    lexical retrieval using BM25 instead of embedding search.

    For each shard (folder):
        - Load chunks + metadata
        - Build BM25 index
        - Execute lexical search
        - Log selected chunks
    """

    # -----------------------------------------------------
    def __init__(self, docs_path: str, bot_profile: str, top_k_bm25: int, std_out_logger
                 ,dump_on_logs=False,dump_log_folder=None):
        """
        Args:
            docs_path: root directory where bot profiles are stored
            bot_profile: folder inside docs_path that defines this bot corpus
            top_k_bm25: number of BM25 hits per shard
            logger: logging object with .info() / .debug() / .error()
        """
        self.docs_path = docs_path
        self.bot_profile = bot_profile
        self.top_k_bm25 = top_k_bm25
        self.std_out_logger = std_out_logger
        self.file_logger = RetrievalLogger(dump_on_logs, dump_log_folder)

        # Static filenames
        self.chunk_file = _CHUNKS_FILE
        self.meta_file = _METADATA_FILE

    # -----------------------------------------------------
    def _load_shard_data(self, folder_path: str) -> Tuple[List[str], List[Dict]]:
        """
        Load chunk texts + metadata from a shard folder.

        Returns:
            chunks: List[str]
            metadata: List[Dict]
        """
        c_path = os.path.join(folder_path, self.chunk_file)
        m_path = os.path.join(folder_path, self.meta_file)

        if not (os.path.isfile(c_path) and os.path.isfile(m_path)):
            raise ValueError("Shard missing chunks or metadata files.")

        raw = open(c_path, encoding="utf-8").read()
        chunks = [x.strip() for x in re.split(r"\n\s*\n", raw) if x.strip()]

        metadata = json.load(open(m_path, encoding="utf-8"))

        if len(chunks) != len(metadata):
            raise ValueError("Chunk count does not match metadata count.")

        return chunks, metadata

    # -----------------------------------------------------
    def _build_bm25_index(self, chunks: List[str]) -> BM25Retriever:
        """
        Build a BM25Retriever object from the chunk list.
        """
        docs = [Document(page_content=t) for t in chunks]
        retriever = BM25Retriever.from_documents(docs)
        retriever.k = self.top_k_bm25
        return retriever

    # -----------------------------------------------------
    def _log_hits(self, folder: str, hits: List[Document]):
        """
        Log retrieved chunks from a shard.
        """
        for rank, doc in enumerate(hits, start=1):
            text = doc.page_content
            self.file_logger.print_to_file_chunk_("BM25",folder=folder,rank=rank,text=text)


    # -----------------------------------------------------
    def _run_bm25_on_shard(
            self,
            query: str,
            folder: str,
            chunks: List[str],
            metadata: List[Dict]
    ) -> List[Document]:

        retriever = self._build_bm25_index(chunks)
        hits = retriever.invoke(query)

        # BM25Okapi scorer (real scores)
        okapi = retriever.vectorizer
        scores = okapi.get_scores(query)

        enriched = []
        for i, doc in enumerate(hits):
            idx = chunks.index(doc.page_content)
            dominance_score = scores[idx]

            enriched.append(
                Document(
                    page_content=doc.page_content,
                    metadata={
                        **metadata[idx],
                        "source_folder": folder,
                        "bm25_rank": i + 1,
                        "dominance_score": dominance_score
                    }
                )
            )

        #self._log_hits(folder, enriched)
        return enriched

    def _bm25_global_topk(self, docs: List[Document], query: str) -> List[Document]:
        """
        Apply a single global BM25 over the merged shard results.
        Returns exactly self.top_k_bm25 docs.
        All comments in English.
        """

        # 1) Extract raw texts
        texts = [d.page_content for d in docs]

        # 2) Build global BM25
        retriever = BM25Retriever.from_documents(
            [Document(page_content=t) for t in texts]
        )
        retriever.k = self.top_k_bm25

        # 3) Run global BM25
        hits = retriever.invoke(query)

        # 4) Re-attach original metadata
        out = []
        for h in hits:
            # find original document
            idx = texts.index(h.page_content)
            orig = docs[idx]

            out.append(
                Document(
                    page_content=orig.page_content,
                    metadata=orig.metadata
                )
            )

        self._log_hits("ALL", hits)
        return out

    # -----------------------------------------------------
    def run_bm25_search(self, query: str) -> List[Document]:
        """
        Traverse every top-level folder and every internal subfolder,
        loading BM25 chunks + metadata and running BM25 on each shard.
        """
        root_path = os.path.join(self.docs_path, self.bot_profile)

        top_folders = [
            f for f in os.listdir(root_path)
            if os.path.isdir(os.path.join(root_path, f))
        ]

        all_results: List[Document] = []

        self.file_logger.init_log_dump_file("BM25")
        self.file_logger.print_to_file_query_(query)

        for folder in top_folders:
            folder_path = os.path.join(root_path, folder)
            self.std_out_logger.info(f"--- Processing BM25 folder: {folder} ---")

            # Mirror FAISS behaviour: walk internal folders
            current_folder_hits = []
            for inner_root, _, _ in os.walk(folder_path):

                chunk_file = os.path.join(inner_root, "chunks.txt")
                meta_file = os.path.join(inner_root, "metadata.json")

                if not (os.path.isfile(chunk_file) and os.path.isfile(meta_file)):
                    continue

                try:
                    chunks, metas = self._load_shard_data(inner_root)
                except Exception as e:
                    self.std_out_logger.error(f"[BM25_SKIP] {folder} / {inner_root}: {e}")
                    continue

                try:
                    current_folder_hits = self._run_bm25_on_shard(
                        query=query,
                        folder=folder,
                        chunks=chunks,
                        metadata=metas
                    )
                    all_results.extend(current_folder_hits)
                except Exception as e:
                    self.std_out_logger.error(f"[BM25_SEARCH_ERROR] {folder} / {inner_root}: {e}")
                    continue

        all_results=self._bm25_global_topk(all_results,query)

        #all_results,dom_detected= DominanceDetector.detect_dominance_and_filter(all_results,self.std_out_logger)
        self.file_logger.close_log_dump_file()
        return all_results



