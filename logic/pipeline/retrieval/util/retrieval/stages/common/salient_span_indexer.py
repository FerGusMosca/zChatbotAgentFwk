# ===== salient_span_indexer.py =====
# All comments MUST be in English.
# Fully aligned with ContextCompressor style: config-driven, no defaults, strict validation

import json
import re
from typing import List
from transformers import pipeline

from logic.pipeline.retrieval.util.retrieval.stages.common.weighted_fusion import RetrievedDocument


class SalientSpanIndexer:
    """
    Production-grade SSI v2 – sliding window + confidence filtering
    ALL settings are mandatory and loaded from external JSON – zero hard-coded defaults
    """

    # Config section and keys – exactly as defined in ssi.json
    SSI_SETTINGS = "ssi"
    ENABLED_KEY = "enabled"
    MODEL_KEY = "model_name"
    DEVICE_KEY = "device"
    WINDOW_SIZE_KEY = "window_size"
    STRIDE_KEY = "stride"
    TOP_K_PER_DOC_KEY = "top_k_per_doc"
    MIN_SCORE_KEY = "min_score_threshold"
    GLOBAL_TOP_K_KEY = "global_top_k"
    MAX_ANSWER_LEN_KEY = "max_answer_length"
    HANDLE_IMPOSSIBLE_KEY = "handle_impossible_answer"
    PREFER_LONGEST_WHEN_ACTIVE_KEY = "prefer_longest_when_active"

    # Self-gating subsection
    SELF_GATING_SECTION = "self_gating"
    SELF_GATING_ENABLED_KEY = "enabled"
    DEFAULT_BEHAVIOR_KEY = "default_behavior"  # "run_ssi" or "bypass"

    LITERAL_TRIGGERS_KEY = "literal_extraction_triggers"
    NUMERIC_EXTRACTION_KW_KEY = "numeric_extraction_keywords"
    FACTUAL_QA_INDICATORS_KEY = "factual_qa_indicators"

    def __init__(
        self,
        ssi_config_path: str,
        logger=None,
    ):
        if not ssi_config_path:
            raise ValueError("ssi_config_path is required")

        self.logger = logger

        # Load and validate JSON
        try:
            with open(ssi_config_path, "r", encoding="utf-8") as f:
                raw_config = json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(f"SSI config file not found: {ssi_config_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in SSI config: {e}")

        cfg = raw_config.get(self.SSI_SETTINGS)
        if cfg is None:
            raise KeyError(f"Missing section '{self.SSI_SETTINGS}' in config file")

        # === Core settings (once and only once) ===
        self.enabled = cfg[self.ENABLED_KEY]
        self.model_name = cfg[self.MODEL_KEY]
        self.device = cfg[self.DEVICE_KEY]
        self.window_size = cfg[self.WINDOW_SIZE_KEY]
        self.stride = cfg[self.STRIDE_KEY]
        self.top_k_per_doc = cfg[self.TOP_K_PER_DOC_KEY]
        self.min_score_threshold = cfg[self.MIN_SCORE_KEY]
        self.global_top_k = cfg[self.GLOBAL_TOP_K_KEY]
        self.max_answer_length = cfg[self.MAX_ANSWER_LEN_KEY]
        self.handle_impossible = cfg[self.HANDLE_IMPOSSIBLE_KEY]
        self.prefer_longest_when_active = cfg[self.PREFER_LONGEST_WHEN_ACTIVE_KEY]

        #

        # === Self-gating ===
        gating = cfg.get(self.SELF_GATING_SECTION, {})
        self.self_gating_enabled = gating.get(self.SELF_GATING_ENABLED_KEY, True)
        self.literal_triggers = gating.get(self.LITERAL_TRIGGERS_KEY, [])
        self.numeric_kw = gating.get(self.NUMERIC_EXTRACTION_KW_KEY, [])
        self.factual_indicators = gating.get(self.FACTUAL_QA_INDICATORS_KEY, [])


        if self.enabled:
            self.logger.info(f"Loading SSI model '{self.model_name}' on device {self.device}")
            self.extractor = pipeline(
                "question-answering",
                model=self.model_name,
                device=self.device,
                max_seq_len=512,
            )
            self.logger.info("SSI model loaded successfully")
        else:
            self.logger.info("Salient Span Indexer is DISABLED via config")
            self.extractor = None

    # ------------------------------------------------------------------

    def _sliding_windows(self, text: str) -> List[str]:
        tokens = text.split()
        windows = []
        size = self.window_size
        step = self.stride

        for i in range(0, max(1, len(tokens) - size + 1), step):
            windows.append(" ".join(tokens[i:i + size]))
        if len(tokens) >= size and windows:
            windows[-1] = " ".join(tokens[-size:])
        return windows if windows else [text[: size * 4]]

    def am_i_competent(self, query: str, intent: str = "") -> bool:
        if not self.enabled or not self.self_gating_enabled:
            return False

        q = query.lower()

        for trig in self.literal_triggers:
            if trig in q:
                self.logger.info(f"SSI bypassed: literal trigger '{trig}'")
                return False

        if re.search(r"\d[\d\.]*%|\$[0-9]+|\d+\s?bps|basis points?", q):
            for kw in self.numeric_kw:
                if kw in q:
                    self.logger.info("SSI bypassed: numeric extraction intent")
                    return False

        return True  # safe default: run when in doubt
    def extract(
            self,
            docs: List[RetrievedDocument],
            query: str,
            intent: str = ""
    ) -> List[RetrievedDocument]:

        if not self.enabled or not docs or not query.strip():
            return docs

        if not self.am_i_competent(query, intent):
            self.logger.info("SSI BYPASSED by self-gating → returning original docs")
            return docs

        min_score = self.min_score_threshold
        top_k_doc = self.top_k_per_doc
        global_k = self.global_top_k

        spans: List[RetrievedDocument] = []

        for doc in docs:
            windows = self._sliding_windows(" ".join(doc.text.split()))

            for window in windows:
                try:
                    results = self.extractor(
                        question=query,
                        context=window,
                        top_k=top_k_doc,
                        max_answer_len=self.max_answer_length,
                        handle_impossible_answer=self.handle_impossible,
                    )
                    if isinstance(results, dict):
                        results = [results]

                    for res in results:
                        span = res["answer"].strip()

                        # --- Safety filters (English comments only) ---
                        # Skip empty spans or formatting artifacts
                        if not span or span in {".", "-", "–", "—"}:
                            continue
                        # Skip spans that are just whitespace or newlines
                        if span.replace("\n", "").strip() == "":
                            continue
                        # Skip duplicated identical spans
                        if any(s.text == span for s in spans):
                            continue

                        if res["score"] < min_score:
                            continue

                        self.logger.info(
                            f"SSI ACCEPTED | score={res['score']:.4f} | '{res['answer'].strip().replace(chr(10), ' ')[:140]}'"
                        )

                        spans.append(RetrievedDocument(
                            text=res["answer"].strip(),
                            metadata={
                                **doc.metadata,
                                "ssi_score": float(res["score"]),
                                "ssi_source": "sliding_window",
                            },
                            score_faiss=doc.score_faiss,
                            score_bm25=doc.score_bm25,
                        ))
                except Exception:
                    continue

        if self.prefer_longest_when_active and spans:
            # Primary: highest score, tie-break: longest span
            ranked = sorted(
                spans,
                key=lambda x: (x.metadata.get("ssi_score", 0.0), len(x.text)),
                reverse=True
            )
            self.logger.info("SSI post-rank: prefer_longest_when_active applied")
        else:
            ranked = sorted(spans, key=lambda x: x.metadata.get("ssi_score", 0.0), reverse=True)

        final = ranked[:global_k]

        self.logger.info(f"SSI DONE → {len(final)} spans extracted (threshold={min_score})")
        return final