from __future__ import annotations   # ← esta línea SOLO UNA VEZ al inicio del archivo
from typing import List

from langchain_core.documents import Document


class ChunksDebugger:

    # FILE: the class that has the logger (usually HybridRetriever or similar)
    # Replace or add this static method

    @staticmethod
    def _log_prefetch_documents(docs: List[Document], key: str, logger) -> None:
        logger.debug(f"----{key.upper()} CHUNKS RETURNED ({len(docs)}) ----")
        for i, doc in enumerate(docs, start=1):
            score = doc.metadata.get("score", 0.0)
            source = doc.metadata.get("source", "unknown")
            preview = doc.page_content.replace("\n", " ").replace("\r", " ")[:120]
            if len(doc.page_content) > 120:
                preview += "..."
            logger.debug(f"CHUNK[{i:02d}]: [score={score:.4f} src={source}] {preview}")

    @staticmethod
    def _log_retrieved_document(docs,key,logger):
        logger.debug(f"----{key} CHUNKS RETURNED ----")
        for i, doc in enumerate(docs, start=1):
            logger.debug(f"CHUNK[{i:02d}]: {doc.to_log_string()}")