# FILE: context_compression.py
# All comments MUST be in English.

import json
from typing import List
from sentence_transformers import SentenceTransformer, util

from logic.pipeline.retrieval.util.retrieval.stages.common.weighted_fusion import RetrievedDocument


class ContextCompressor:
    """
    Offline context compression using MMR.
    ALL settings are mandatory and come from config file – no defaults.
    """

    # Config section and keys – used exactly as defined in JSON
    COMPRESSION_SETTINGS = "compression"
    ENABLED_KEY = "enabled"
    MODEL_KEY = "model"
    TOP_K_KEY = "top_k"
    MMR_LAMBDA_KEY = "mmr_lambda"
    DEVICE_KEY = "device"
    MAX_CHARS_TO_COMP_KEY="max_chars_to_comp"

    def __init__(
        self,
        compression_settings_path: str,
        logger= None,
    ):
        if not compression_settings_path:
            raise ValueError("compression_settings_path is required")

        self.logger = logger

        try:
            with open(compression_settings_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"Compression config file not found: {compression_settings_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in compression config: {e}")

        cfg = raw_config.get(self.COMPRESSION_SETTINGS)
        if cfg is None:
            raise KeyError(f"Missing section '{self.COMPRESSION_SETTINGS}' in config file")

        # Mandatory fields – will raise KeyError if missing
        self.enabled: bool = cfg[self.ENABLED_KEY]
        self.model_name: str = cfg[self.MODEL_KEY]
        self.top_k: int = cfg[self.TOP_K_KEY]
        self.mmr_lambda: float = cfg[self.MMR_LAMBDA_KEY]
        self.device: str = cfg[self.DEVICE_KEY]
        self.max_chars_to_comp :str=cfg[self.MAX_CHARS_TO_COMP_KEY]

        if self.enabled:
            self.logger.info(f"Loading compression model '{self.model_name}' on {self.device}")
            self.model = SentenceTransformer(self.model_name, device=self.device)
        else:
            self.logger.info("Context compression is disabled via config")
            self.model = None

    def _am_i_competent(self,docs):
        full_ctx=""
        for doc in docs:
            full_ctx+=doc.text


        return len(full_ctx)>self.max_chars_to_comp



    def compress(self, docs: List[RetrievedDocument], query: str) -> List[RetrievedDocument]:
        """Offline MMR compression – production-grade logging"""
        if not self.enabled:
            self.logger.debug("MMR compression: DISABLED via config")
            return docs

        if not self._am_i_competent(docs):
            self.logger.warning("MMR compression disabled because small context")
            return docs

        if not docs:
            self.logger.info("MMR compression: 0 docs received → returning empty")
            return docs

        if not query.strip():
            self.logger.warning("MMR compression: empty query → skipping compression")
            return docs


        original_count = len(docs)
        if original_count <= self.top_k:
            self.logger.info(f"MMR compression: {original_count} docs ≤ top_k({self.top_k}) → no compression needed")
            return docs

        self.logger.debug(f"MMR compression START → {original_count} docs | top_k={self.top_k} | λ={self.mmr_lambda}")

        texts = [doc.text for doc in docs]

        # Encoding
        query_emb = self.model.encode(query, convert_to_tensor=True, show_progress_bar=False)
        doc_embs = self.model.encode(texts, convert_to_tensor=True, show_progress_bar=False)

        selected_indices = []
        candidate_indices = list(range(len(docs)))

        for i in range(min(self.top_k, len(docs))):
            candidate_embs_current = doc_embs[candidate_indices]
            relevance = util.cos_sim(query_emb, candidate_embs_current)[0]

            if selected_indices and self.mmr_lambda < 1.0:
                selected_embs = doc_embs[selected_indices]
                diversity = util.cos_sim(candidate_embs_current, selected_embs).max(dim=1).values
                #mmr_scores = self.mmr_lambda * relevance - (1.0 - self.mmr_lambda) * diversity
                mmr_scores = (1.0 - self.mmr_lambda) * relevance - self.mmr_lambda * diversity
            else:
                mmr_scores = relevance

            best_local_idx = int(mmr_scores.argmax())
            best_global_idx = candidate_indices[best_local_idx]

            selected_indices.append(best_global_idx)
            candidate_indices.pop(best_local_idx)

            '''
            self.logger.info(f"MMR step {i + 1}/{self.top_k}: selected doc #{best_global_idx} "
                              f"| rel={relevance[best_local_idx]:.3f}")
            '''

        result = [docs[i] for i in selected_indices]
        reduction = original_count - len(result)

        self.logger.info(
            f"MMR compression DONE → {original_count} → {len(result)} docs "
            f"(-{reduction} | -{reduction / original_count:.0%})"
        )

        return result

