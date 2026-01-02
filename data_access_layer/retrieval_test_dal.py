import json
import pyodbc
from typing import Dict

from langchain_core.documents import Document

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

    def persist_retrieval(self, query: str) -> int:
        """
        Persist retrieval execution and return DB-generated retrieval_id.
        """

        self.std_out_logger.debug("[DAL_PERSIST_RETRIEVAL] persisting retrieval")

        with pyodbc.connect(self.connection_string) as conn:
            cursor = conn.cursor()

            cursor.execute(
                "EXEC dbo.sp_insert_retrieval @query=?",
                query
            )

            row = cursor.fetchone()
            conn.commit()

        if row is None or row[0] is None:
            raise RuntimeError("[DAL_PERSIST_RETRIEVAL_ERROR] retrieval_id not returned")

        retrieval_id = int(row[0])

        self.std_out_logger.debug(
            f"[DAL_PERSIST_RETRIEVAL_OK] retrieval_id={retrieval_id}"
        )

        return retrieval_id

    def persist_retrieval_chunk(
            self,
            retr_id: str,
            stage: str,
            folder: str,
            query: str,
            doc: Document
    ) -> None:
        """
        Persist a single retrieval chunk (LangChain Document) using stored procedure.
        """

        md = doc.metadata or {}

        with pyodbc.connect(self.connection_string) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                EXEC dbo.sp_insert_retrieval_chunk
                    @retrieval_id=?,
                    @stage=?,
                    @folder=?,
                    @source_pdf=?,
                    @query=?,
                    @chunk_text=?,
                    @faiss_similarity=?,
                    @faiss_distance=?,
                    @faiss_rank=?,
                    @dominance_score=?,
                    @cross_encoder_score=?,
                    @metadata=?
                """,
                retr_id,
                stage,
                folder,
                md.get("source_pdf"),
                query,
                doc.page_content,
                md.get("faiss_similarity"),
                md.get("faiss_distance"),
                md.get("faiss_rank"),
                md.get("dominance_score"),
                md.get("cross_encoder_score"),  # puede venir None
                json.dumps(md),
            )

            conn.commit()


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
                    "source": stage.source,
                    "llm_judgement": json.dumps(stage.llm_judgement)
                    if stage.llm_judgement is not None
                    else None,
                }
            )

        return stages
