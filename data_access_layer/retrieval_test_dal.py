import json
import pyodbc
from typing import Dict

from common.dto.test.retrieval_test_result_dto import RetrievalTestResultDTO


class RetrievalTestDAL:
    """
    Data Access Layer for persisting retrieval test results.

    Responsibilities:
    - Serialize RetrievalTestResultDTO
    - Call SQL Server stored procedures
    - One test persisted at a time (append-only)
    """

    def __init__(self, connection_string: str, std_out_logger):
        self.connection_string = connection_string
        self.std_out_logger = std_out_logger

    # ------------------------------------------------------------------
    # PUBLIC API
    # ------------------------------------------------------------------

    def persist_tests(self, tests: Dict[str, RetrievalTestResultDTO]) -> None:
        """
        Persist all tests contained in RetrievalHarnessTester.tests.

        :param tests: dict[test_id -> RetrievalTestResultDTO]
        """

        if not tests:
            self.std_out_logger.debug("[DAL_SKIP] No retrieval tests to persist")
            return

        for test_id, dto in tests.items():
            try:
                self._persist_single_test(dto)
            except Exception as exc:
                self.std_out_logger.error(
                    f"[DAL_PERSIST_ERROR] {test_id} → {exc}"
                )

    # ------------------------------------------------------------------
    # INTERNAL
    # ------------------------------------------------------------------

    def persist_single_test(self, dto: RetrievalTestResultDTO) -> None:
        """
        Persist a single RetrievalTestResultDTO using stored procedure.
        """

        self.std_out_logger.debug(
            f"[DAL_PERSIST_TEST] {dto.query_id} → persisting retrieval test"
        )

        stages_payload = self._build_stages_payload(dto)

        with pyodbc.connect(self.connection_string) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                EXEC persist_retrieval_test
                    @query_id=?,
                    @query_type=?,
                    @query=?,
                    @gold_chunks=?,
                    @schema_version=?,
                    @run_date=?,
                    @corpus_hash=?,
                    @params_hash=?,
                    @final_llm_score=?,
                    @final_notes=?,
                    @stages_json=?
                """,
                dto.query_id,
                dto.query_type,
                dto.query,
                json.dumps(dto.gold_chunks),
                dto.schema_version,
                dto.run_date,
                dto.corpus_hash,
                dto.params_hash,
                dto.final_llm_score,
                dto.final_notes,
                json.dumps(stages_payload),
            )

            conn.commit()

        self.std_out_logger.debug(
            f"[DAL_PERSIST_OK] {dto.query_id} → test persisted successfully"
        )

    def _build_stages_payload(self, dto: RetrievalTestResultDTO) -> list:
        """
        Convert StageMetricsDTO objects into a JSON-serializable structure
        compatible with persist_retrieval_test.
        """

        stages = []

        for stage_name, stage in dto.stages.items():

            # Skip stages that were never evaluated
            if (
                not stage.retrieved_chunks
                and stage.llm_judgement is None
                and stage.recall is None
                and stage.precision is None
            ):
                continue

            stages.append(
                {
                    "stage_name": stage_name,
                    "stage_type": stage.stage_type,
                    "retrieved_chunks": json.dumps(stage.retrieved_chunks),
                    "gold_hits": json.dumps(stage.gold_hits),
                    "dropped_gold_chunks": json.dumps(stage.dropped_gold_chunks),
                    "hallucinated_chunks": json.dumps(stage.hallucinated_chunks),
                    "recall": stage.recall,
                    "precision": stage.precision,
                    "llm_judgement": json.dumps(stage.llm_judgement)
                    if stage.llm_judgement is not None
                    else None,
                }
            )

        return stages
