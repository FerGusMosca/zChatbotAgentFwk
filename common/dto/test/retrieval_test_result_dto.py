from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime


@dataclass
class StageMetricsDTO:
    stage_type: str = ""   # bi_encoder | cross_encoder | fusion | mmr | dedup
    source: str = ""
    retrieved_chunks: List[str] = field(default_factory=list)
    gold_hits: List[str] = field(default_factory=list)
    dropped_gold_chunks: List[str] = field(default_factory=list)
    hallucinated_chunks: List[str] = field(default_factory=list)
    recall: Optional[float] = None
    precision: Optional[float] = None
    llm_judgement: Optional[dict] = None

    def normalize_from_llm_judgement(self) -> None:
        """
        Normalize recall / precision from llm_judgement based on evaluation_type.
        Safe, idempotent, and non-throwing.
        """

        if not self.llm_judgement or not isinstance(self.llm_judgement, dict):
            return

        eval_type = self.llm_judgement.get("evaluation_type")

        # ---- BI-ENCODER: recall-focused ----
        if eval_type == "bi_encoder_recall":
            recall_label = self.llm_judgement.get("recall_assessment")

            if recall_label:
                mapping = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}
                self.recall = mapping.get(recall_label)
            else:
                relevant = self.llm_judgement.get("relevant_chunks", [])
                self.recall = 1.0 if len(relevant) > 0 else 0.0

        # ---- CROSS-ENCODER: precision-focused ----
        elif eval_type == "cross_encoder_precision":
            precision = self.llm_judgement.get("precision")
            if isinstance(precision, (int, float)):
                self.precision = float(precision)

        # ---- BM25: binary lexical hit ----
        elif eval_type == "bm25_precision":
            relevant = self.llm_judgement.get("relevant_chunks")
            if isinstance(relevant, int) and relevant > 0:
                self.precision = 1.0
                self.recall = 1.0
            else:
                self.precision = 0.0
                self.recall = 0.0

        # Unknown evaluation_type → ignore silently


@dataclass
class RetrievalTestResultDTO:
    """
    Root DTO representing the full evaluation result of a single query
    across all retrieval pipeline stages.
    This object is meant to be filled incrementally by RetrievalHarnessTester.
    """

    # ---- schema / identity ----
    schema_version: str = None
    query_id: str = ""
    query_type: str = ""   # specific | lexical | broad | analytical
    query: str = ""

    # Immutable baseline defining the expected relevant chunks
    gold_chunks: List[str] = field(default_factory=list)

    # ---- run metadata ----
    run_date: datetime = field(default_factory=datetime.utcnow)
    corpus_hash: str = ""   # Hash identifying the corpus version
    params_hash: str = ""   # Hash identifying retrieval parameters

    # ---- per-stage results ----
    stages: Dict[str, StageMetricsDTO] = field(
        default_factory=lambda: {
            "faiss_bi_encoder": StageMetricsDTO(stage_type="bi_encoder"),
            "faiss_cross_encoder": StageMetricsDTO(stage_type="cross_encoder"),
            "bm25": StageMetricsDTO(),
            "fusion": StageMetricsDTO(),
            "mmr": StageMetricsDTO(),
            "dedup": StageMetricsDTO(),
        }
    )

    # ---- final holistic evaluation ----
    final_llm_score: Optional[float] = None
    final_notes: Optional[str] = None
