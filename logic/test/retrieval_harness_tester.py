import json
from typing import List, Dict
import hashlib

from langchain_core.documents import Document
from common.dto.test.retrieval_test_result_dto import RetrievalTestResultDTO, StageMetricsDTO
from common.util.loader.prompt_loader import PromptLoader
from data_access_layer.retrieval_test_dal import RetrievalTestDAL
from logic.util.builder.llm_factory import LLMFactory


class RetrievalHarnessTester:
    """
    Orchestrates retrieval pipeline testing for a battery of queries.

    - One RetrievalTestResultDTO per query
    - Queries are identified by a stable hash + optional index
    - Persistence is intentionally out of scope (handled later)
    """

    def __init__(self, testing_harness_cfg: dict, llm_prov,model_name,temperature, std_out_logger):
        """
        :param testing_harness_cfg: dict-based config (same pattern as rerankers_cfg)
        :param llm_prov: LLM provider instance (used later)
        :param std_out_logger: logger with debug / info / warning
        """

        self.testing_harness_cfg = testing_harness_cfg
        self.llm_prov = llm_prov
        self.std_out_logger = std_out_logger


        self.enabled = testing_harness_cfg.get("enabled", False)
        self.connection_string = testing_harness_cfg.get("connection_string")
        self.testing_prompt = testing_harness_cfg.get("testing_prompt")

        self.test_mgr =   RetrievalTestDAL(self.connection_string,std_out_logger)


        # Battery of tests: key -> RetrievalTestResultDTO
        self.tests: Dict[str, RetrievalTestResultDTO] = {}

        if not self.enabled:
            self.std_out_logger.debug("[TESTING_HARNESS_DISABLED] Harness is disabled")
        else:
            self._load_llm_judges(llm_prov,model_name,temperature)



    # ------------------------------------------------------------------
    # BI-ENCODER (FAISS) RETRIEVAL EVALUATION
    # ------------------------------------------------------------------

    def evaluate_bi_encoder_retrieval(
            self,
            query: str,
            source:str,
            retrieved_docs: List[Document]
    ) -> None:
        """
        Evaluate bi-encoder (FAISS) retrieval stage for a given query.

        This evaluates:
        - Structural recall / precision (gold_chunks vs retrieved)
        - Semantic recall via LLM judge (BI_ENCODER_TESTING)
        """

        if not self.enabled:
            self.std_out_logger.debug("[FAISS_SKIP] Testing harness disabled")
            return

        if not self.testing_harness_cfg["process_bi_encoder"]:
            self.std_out_logger.debug("[FAISS_BI_ENCODER_SKIP] Skipping bi encoder testing for settings")
            return

        last_test = self._get_last_query_added()#we don't have the original question. so last test is ok
        if last_test is not None:
            test_id=last_test.query_id
            dto = self.tests[test_id]
        else:
            raise Exception(f"[FAISS_LLM_INITIALIZE_ERROR] : Could not find a last test to process!")

        stage_name = f"faiss_bi_encoder_{source}"
        stage = dto.stages.setdefault(stage_name, StageMetricsDTO(stage_type="bi_encoder",source=source))

        # ------------------------------------------------------------
        # 1) Structural evaluation (IDs)
        # ------------------------------------------------------------

        retrieved_chunk_ids = [
            self._extract_chunk_id(doc) for doc in retrieved_docs
        ]
        stage.retrieved_chunks = retrieved_chunk_ids
        stage.source=source

        self.std_out_logger.debug(
            f"[FAISS_TEST] {test_id} → evaluating {len(retrieved_chunk_ids)} chunks"
        )

        self._compute_stage_metrics(dto, stage_name)

        # ------------------------------------------------------------
        # 2) Build prompt string (NO templating magic)
        # ------------------------------------------------------------

        chunks_block = []
        for idx, doc in enumerate(retrieved_docs):
            chunks_block.append(
                f"[{idx}]\n{doc.page_content.strip()}"
            )

        prompt = (
            f"{self.bi_encoder_prompt}\n\n"
            f"QUESTION:\n{query}\n\n"
            f"RETRIEVED CHUNKS:\n"
            f"{'|'.join(chunks_block)}"
        )

        self.std_out_logger.debug(
            f"[FAISS_LLM_JUDGE] {test_id} → invoking LLM with {len(retrieved_docs)} chunks"
        )

        # ------------------------------------------------------------
        # 3) Invoke LLM (correct API)
        # ------------------------------------------------------------

        try:
            llm_raw_response = self.llm.invoke(prompt)
        except Exception as exc:
            self.std_out_logger.error(
                f"[FAISS_LLM_ERROR] {test_id} → {exc}"
            )
            return

        # ------------------------------------------------------------
        # 4) Parse JSON response
        # ------------------------------------------------------------

        try:
            llm_judgement = self._safe_json_load(llm_raw_response)
        except Exception as exc:
            self.std_out_logger.error(
                f"[FAISS_LLM_PARSE_ERROR] {test_id} → {exc} | raw={llm_raw_response[:500]}"
            )
            return

        # ------------------------------------------------------------
        # 5) Persist raw semantic judgement (append-only)
        # ------------------------------------------------------------

        stage.llm_judgement = llm_judgement
        stage.normalize_from_llm_judgement()

        self.std_out_logger.debug(
            f"[FAISS_LLM_DONE] {test_id} → recall_assessment="
            f"{llm_judgement.get('recall_assessment')}"
        )

    def evaluate_cross_encoder_retrieval(
            self,
            query: str,
            query_label:str,
            filtered_docs: List[Document]
    ) -> None:
        """
        Evaluate cross-encoder retrieval stage.

        Focus:
        - Precision / noise of filtered chunks
        - Semantic relevance (LLM judge)
        """

        if not self.enabled:
            self.std_out_logger.debug("[CROSS_SKIP] Testing harness disabled")
            return

        last_test = self._get_last_query_added()#we don't have the original question. so last test is ok
        if last_test is not None:
            test_id=last_test.query_id
            dto = self.tests[test_id]
        else:
            raise Exception(f"[FAISS_LLM_INITIALIZE_ERROR] : Could not find a last test to process!")

        stage_name = "faiss_cross_encoder"
        stage = dto.stages[stage_name]

        # ------------------------------------------------------------
        # 1) Structural stats
        # ------------------------------------------------------------

        retrieved_chunk_ids = [
            self._extract_chunk_id(doc) for doc in filtered_docs
        ]
        stage.retrieved_chunks = retrieved_chunk_ids

        self.std_out_logger.debug(
            f"[CROSS_TEST] {test_id} → evaluating {len(filtered_docs)} filtered chunks"
        )

        # ------------------------------------------------------------
        # 2) Build prompt
        # ------------------------------------------------------------

        chunks_block = []
        for idx, doc in enumerate(filtered_docs):
            chunks_block.append(
                f"[{idx}]\n{doc.page_content.strip()}"
            )

        prompt = (
            f"{self.cross_encoder_prompt}\n\n"
            f"QUESTION:\n{query}\n\n"
            f"RETAINED CHUNKS:\n"
            f"{'|'.join(chunks_block)}"
        )

        self.std_out_logger.debug(
            f"[CROSS_LLM_JUDGE] {test_id} → invoking LLM with {len(filtered_docs)} chunks"
        )

        # ------------------------------------------------------------
        # 3) Invoke LLM
        # ------------------------------------------------------------

        try:
            llm_raw_response = self.llm.invoke(prompt)
        except Exception as exc:
            self.std_out_logger.error(
                f"[CROSS_LLM_ERROR] {test_id} → {exc}"
            )
            return

        # ------------------------------------------------------------
        # 4) Parse JSON
        # ------------------------------------------------------------

        try:
            llm_judgement = self._safe_json_load(llm_raw_response)
        except Exception as exc:
            self.std_out_logger.error(
                f"[CROSS_LLM_PARSE_ERROR] {test_id} → {exc} | raw={llm_raw_response[:500]}"
            )
            return

        # ------------------------------------------------------------
        # 5) Persist results
        # ------------------------------------------------------------

        stage.llm_judgement = llm_judgement
        stage.normalize_from_llm_judgement()

        self.std_out_logger.debug(
            f"[CROSS_LLM_DONE] {test_id} → precision="
            f"{llm_judgement.get('precision')} | noise_ratio="
            f"{llm_judgement.get('noise_ratio')}"
        )

    def evaluate_bm25_retrieval(
            self,
            query: str,
            query_label: str,
            retrieved_docs: List[Document]
    ) -> None:
        """
        Evaluate BM25 retrieval stage.

        Focus:
        - Lexical precision (keyword match)
        - Noise from generic / coincidental matches
        """

        if not self.enabled:
            self.std_out_logger.debug("[BM25_SKIP] Testing harness disabled")
            return

        last_test = self._get_last_query_added()#we don't have the original question. so last test is ok
        if last_test is not None:
            test_id=last_test.query_id
            dto = self.tests[test_id]
        else:
            raise Exception(f"[FAISS_LLM_INITIALIZE_ERROR] : Could not find a last test to process!")

        stage_name = "bm25"
        stage = dto.stages[stage_name]

        # ------------------------------------------------------------
        # 1) Structural stats
        # ------------------------------------------------------------

        retrieved_chunk_ids = [
            self._extract_chunk_id(doc) for doc in retrieved_docs
        ]
        stage.retrieved_chunks = retrieved_chunk_ids

        self.std_out_logger.debug(
            f"[BM25_TEST] {test_id} → evaluating {len(retrieved_docs)} chunks"
        )

        # ------------------------------------------------------------
        # 2) Build prompt
        # ------------------------------------------------------------

        chunks_block = []
        for idx, doc in enumerate(retrieved_docs):
            chunks_block.append(
                f"[{idx}]\n{doc.page_content.strip()}"
            )

        prompt = (
            f"{self.bm25_prompt}\n\n"
            f"QUESTION:\n{query}\n\n"
            f"RETRIEVED CHUNKS:\n"
            f"{'|'.join(chunks_block)}"
        )

        self.std_out_logger.debug(
            f"[BM25_LLM_JUDGE] {test_id} → invoking LLM with {len(retrieved_docs)} chunks"
        )

        # ------------------------------------------------------------
        # 3) Invoke LLM
        # ------------------------------------------------------------

        try:
            llm_raw_response = self.llm.invoke(prompt)
        except Exception as exc:
            self.std_out_logger.error(
                f"[BM25_LLM_ERROR] {test_id} → {exc}"
            )
            return

        # ------------------------------------------------------------
        # 4) Parse JSON
        # ------------------------------------------------------------

        try:
            llm_judgement = self._safe_json_load(llm_raw_response)
        except Exception as exc:
            self.std_out_logger.error(
                f"[BM25_LLM_PARSE_ERROR] {test_id} → {exc} | raw={llm_raw_response[:500]}"
            )
            return

        # ------------------------------------------------------------
        # 5) Persist + normalize
        # ------------------------------------------------------------

        stage.llm_judgement = llm_judgement
        stage.normalize_from_llm_judgement()

        self.std_out_logger.debug(
            f"[BM25_LLM_DONE] {test_id} → precision="
            f"{llm_judgement.get('precision')} | noise_ratio="
            f"{llm_judgement.get('noise_ratio')}"
        )

    def persist_last_query_tests(self, query: str) -> None:
        """
        Persist the DTO corresponding to the latest test run for the given query.
        Fully guarded against missing keys / unexpected states.
        """

        if not query or not isinstance(query, str):
            self.std_out_logger.error(
                "[TEST_PERSIST_ERROR] Invalid query input"
            )
            return

        try:
            last_test_id = self._get_last_query_id(query)
        except Exception as exc:
            self.std_out_logger.error(
                f"[TEST_PERSIST_ERROR] Failed resolving last test id → {exc}"
            )
            return

        if not last_test_id:
            self.std_out_logger.warning(
                "[TEST_PERSIST_SKIP] No tests found for query hash"
            )
            return

        dto = self.tests.get(last_test_id)
        if dto is None:
            self.std_out_logger.error(
                f"[TEST_PERSIST_ERROR] test_id='{last_test_id}' not found in tests registry"
            )
            return

        try:
            self.std_out_logger.debug(
                f"[TEST_PERSIST] Persisting last test → {last_test_id}"
            )
            self.test_mgr.persist_single_test(dto)
        except Exception as exc:
            self.std_out_logger.error(
                f"[TEST_PERSIST_ERROR] Persist failed for test_id='{last_test_id}' → {exc}"
            )

    def initialize_query(self, query:str, query_type: str = None, gold_chunks: List[str] = []):

        query_hash = self._hash_query(query)
        query_idx =  self._get_last_query_id(query)
        query_idx= self._extract_query_idx_posfix(query_idx)
        test_id = f"{query_hash}_{query_idx}"

        if test_id in self.tests:
            return test_id

        dto = RetrievalTestResultDTO(
            query_id=test_id,
            schema_version=self.testing_harness_cfg["schema_version"],
            query=query,
            query_type=query_type,
            gold_chunks=gold_chunks,
        )

        self.tests[test_id] = dto

        self.std_out_logger.debug(
            f"[TEST_CREATED] {test_id} → query_type={query_type}, gold_chunks={len(gold_chunks)}"
        )

    # ------------------------------------------------------------------
    # INTERNAL UTILITIES
    # ------------------------------------------------------------------

    def _load_llm_judges(self, llm_prov, model_name, temperature):
        """
        Initialize LLM judges and load testing prompts.

        This method is expected to be called once during harness initialization.
        """

        self.std_out_logger.info("[LLM_JUDGES_INIT] Initializing LLM judges for retrieval testing")

        # --- Prompt loader ---
        self.std_out_logger.debug(
            f"[LLM_JUDGES_PROMPT_LOADER] loading prompt file='{self.testing_harness_cfg.get('testing_prompt')}'"
        )

        self.prompt_loader = PromptLoader(
            self.testing_harness_cfg["testing_prompt"],
            self.std_out_logger
        )

        # --- LLM initialization ---
        self.std_out_logger.debug(
            f"[LLM_JUDGES_LLM_CREATE] provider='{llm_prov}', model='{model_name}', temperature={temperature}"
        )

        self.llm = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )

        self._load_bi_encoder_judge_prompt()
        self._load_cross_encoder_judge_prompt()
        self._load_bm25_judge_prompt()
        pass

    def _get_or_create_test_id(
            self,
            query: str,
            query_type: str=None,
            gold_chunks: List[str]=[],
            query_idx: int = 0
    ) -> str:
        """
        Return an existing test_id for the given query, or create a new one
        if it does not exist.

        The test_id is derived from a stable hash of the query plus an index,
        allowing multiple runs of the same logical question.
        """

        test_id = self._get_last_query_id(query)

        if test_id in self.tests:
            return test_id

        return self.initialize_query(query,query_type,gold_chunks)

    def _hash_query(self,query):
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]

    def _extract_query_idx_posfix(self,query_idx):

        if query_idx is not None:
            return int(query_idx.split("_")[-1]) +1
        else:
            return 0

    def _get_last_query_added(self):
        if not self.tests:
            return None
        last_key = next(reversed(self.tests))
        return self.tests[last_key]

    def _get_last_query_id(self, query: str) -> str | None:
        """
        Return the latest test_id for a given query based on hash + numeric suffix.
        Example: <hash>_0, <hash>_1, ... -> returns the highest suffix.
        """

        query_hash =  self._hash_query(query)
        prefix = f"{query_hash}_"

        matching_ids = [
            test_id for test_id in self.tests.keys()
            if test_id.startswith(prefix)
        ]

        if not matching_ids:
            return None

        def extract_suffix(tid: str) -> int:
            try:
                return int(tid.split("_")[-1])
            except ValueError:
                return -1

        matching_ids.sort(key=extract_suffix)
        return matching_ids[-1]

    def _extract_chunk_id(self, doc: Document) -> str:
        """
        Extract a stable chunk identifier from a LangChain Document.

        This MUST match the identifier format used in dto.gold_chunks.
        """

        source = doc.metadata.get("source_pdf", "UNKNOWN")
        rank = doc.metadata.get("faiss_rank", "NA")

        return f"{source}::faiss_rank={rank}"

    def _compute_stage_metrics(
        self,
        dto: RetrievalTestResultDTO,
        stage_name: str
    ) -> None:
        """
        Compute recall / precision and diagnostic lists
        for a given retrieval stage.

        Assumes:
        - dto.gold_chunks is immutable ground truth
        - stage.retrieved_chunks is already populated
        """

        stage = dto.stages[stage_name]

        gold_set = set(dto.gold_chunks)
        retrieved_set = set(stage.retrieved_chunks)

        stage.gold_hits = sorted(gold_set & retrieved_set)
        stage.dropped_gold_chunks = sorted(gold_set - retrieved_set)
        stage.hallucinated_chunks = sorted(retrieved_set - gold_set)

        # Recall
        if gold_set:
            stage.recall = len(stage.gold_hits) / len(gold_set)
        else:
            stage.recall = None
            self.std_out_logger.debug(
                f"[{stage_name.upper()}_SKIP] No gold chunks defined"
            )

        # Precision
        if retrieved_set:
            stage.precision = len(stage.gold_hits) / len(retrieved_set)
        else:
            stage.precision = None
            self.std_out_logger.debug(
                f"[{stage_name.upper()}_SKIP] No retrieved chunks"
            )

        # Diagnostics
        if stage.dropped_gold_chunks:
            self.std_out_logger.debug(
                f"[{stage_name.upper()}_DROP] "
                f"{dto.query_id} → dropped gold chunks: {stage.dropped_gold_chunks}"
            )

        if stage.hallucinated_chunks:
            self.std_out_logger.debug(
                f"[{stage_name.upper()}_HALLUCINATION] "
                f"{dto.query_id} → extra chunks: {stage.hallucinated_chunks}"
            )

    def _load_bi_encoder_judge_prompt(self) -> None:
        """
        Load BI-ENCODER LLM judge prompt used for FAISS retrieval evaluation.
        """

        self.std_out_logger.debug(
            "[LLM_JUDGES_PROMPT_LOAD] tag='BI_ENCODER_TESTING'"
        )

        self.bi_encoder_prompt = self.prompt_loader.extract_section(
            self.testing_harness_cfg["testing_prompt"],
            "BI_ENCODER_TESTING"
        )

        if not self.bi_encoder_prompt:
            self.std_out_logger.error(
                "[LLM_JUDGES_PROMPT_MISSING] tag='BI_ENCODER_TESTING' not found or empty"
            )
            raise ValueError("Missing BI_ENCODER_TESTING prompt")

        self.std_out_logger.info(
            "[LLM_JUDGES_READY] BI-ENCODER retrieval judge successfully initialized"
        )

    def _load_cross_encoder_judge_prompt(self) -> None:
        """
        Load CROSS-ENCODER LLM judge prompt used for precision / noise evaluation.
        """

        self.std_out_logger.debug(
            "[LLM_JUDGES_PROMPT_LOAD] tag='CROSS_ENCODER_TESTING'"
        )

        self.cross_encoder_prompt = self.prompt_loader.extract_section(
            self.testing_harness_cfg["testing_prompt"],
            "CROSS_ENCODER_TESTING"
        )

        if not self.cross_encoder_prompt:
            self.std_out_logger.error(
                "[LLM_JUDGES_PROMPT_MISSING] tag='CROSS_ENCODER_TESTING' not found or empty"
            )
            raise ValueError("Missing CROSS_ENCODER_TESTING prompt")

        self.std_out_logger.info(
            "[LLM_JUDGES_READY] CROSS-ENCODER retrieval judge successfully initialized"
        )

    def _load_bm25_judge_prompt(self) -> None:
        """
        Load BM25 LLM judge prompt used for lexical precision / noise evaluation.
        """

        self.std_out_logger.debug(
            "[LLM_JUDGES_PROMPT_LOAD] tag='BM25_TESTING'"
        )

        self.bm25_prompt = self.prompt_loader.extract_section(
            self.testing_harness_cfg["testing_prompt"],
            "BM25_TESTING"
        )

        if not self.bm25_prompt:
            self.std_out_logger.error(
                "[LLM_JUDGES_PROMPT_MISSING] tag='BM25_TESTING' not found or empty"
            )
            raise ValueError("Missing BM25_TESTING prompt")

        self.std_out_logger.info(
            "[LLM_JUDGES_READY] BM25 retrieval judge successfully initialized"
        )

    def _safe_json_load(self, raw: str) -> dict:
        """
        Safely parse JSON coming from LLMs.
        Strips markdown fences and extra text if present.
        """

        text = raw.strip()

        # Remove ```json ... ``` fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first and last fence
            text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        return json.loads(text)