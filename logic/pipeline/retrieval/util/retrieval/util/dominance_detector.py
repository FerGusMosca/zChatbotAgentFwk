from typing import List

import numpy as np
from langchain_core.documents import Document


class DominanceDetector:

    @staticmethod
    def detect_dominance_and_filter(docs: List[Document], logger, z_threshold=3.2):

        logger.info("[DOM] Starting dominance detection (Z-SCORE OUTLIER)")

        if len(docs) < 5:
            logger.info("[DOM] Not enough docs — skip dominance filter")
            return docs, False

        # ---- extract scores ----
        docs_sorted = sorted(
            docs,
            key=lambda d: d.metadata.get("dominance_score", 0.0),
            reverse=True
        )
        sims = np.array([d.metadata.get("dominance_score", 0.0) for d in docs_sorted])

        logger.info(f"[DOM] SIMS (top 10): {sims[:10].tolist()}")

        # ---- stats (exclude top) ----
        rest = sims[1:]
        mean_rest = np.mean(rest)
        std_rest = np.std(rest)

        logger.info(f"[DOM] mean_rest={mean_rest:.6f}, std_rest={std_rest:.6f}")

        if std_rest < 1e-9:
            logger.info("[DOM] std ≈ 0 → cannot detect outliers → skip")
            return docs, False

        # ---- compute z-scores ----
        zscores = (sims - mean_rest) / std_rest
        logger.info(f"[DOM] zscores (top 10): {zscores[:10].tolist()}")

        # ---- detect dominant chunks ----
        dominant_indices = np.where(zscores >= z_threshold)[0].tolist()

        logger.info(f"[DOM] dominant_indices = {dominant_indices}")

        if len(dominant_indices) == 0:
            logger.info("[DOM] No dominance detected → return full set")
            return docs, False

        # ---- keep only dominant docs ----
        dominant_docs = [docs_sorted[i] for i in dominant_indices]

        logger.info(f"[DOM] Dominance detected → keeping {len(dominant_docs)} chunks")

        for i, d in zip(dominant_indices, dominant_docs):
            short = d.page_content[:120].replace("\n", " ")
            logger.info(f"[DOM][KEEP] rank={i + 1} sim={sims[i]:.6f} | text={short}")

        return dominant_docs, True

