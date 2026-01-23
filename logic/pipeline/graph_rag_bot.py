# ===== graph_rag_bot.py =====
import re
from neo4j import GraphDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from common.util.app_logger import AppLogger
from logic.util.builder.llm_factory import LLMFactory


class GraphRAGBot:

    def __init__(
            self,
            vector_store_path,
            prompt_name,
            retrieval_score_threshold=0.4,
            llm_prov: str = "openai",
            model_name: str = "gpt-4o",
            temperature: float = 0.0,
            top_k: int = 4,
    ):
        self.logger = AppLogger.get_logger(__name__)

        # ---- Neo4j config (HARDCODED FOR NOW) ----
        self.neo4j_uri = "bolt://localhost:7687"
        self.neo4j_user = "neo4j"
        self.neo4j_pass = "test1234"

        self.driver = GraphDatabase.driver(
            self.neo4j_uri,
            auth=(self.neo4j_user, self.neo4j_pass)
        )

        # ---- LLM ----
        self.llm = LLMFactory.create(
            provider=llm_prov,
            model_name=model_name,
            temperature=temperature,
        )

        self.prompt = ChatPromptTemplate.from_messages([
            ("system",
             "You are a financial analyst assistant. "
             "Explain the results returned from a graph database query. "
             "Do NOT invent data. Use only the provided context."),
            ("human", "{question}\n\nData:\n{context}")
        ])

        self.logger.info("GraphRAGBot initialized.")

    # ---------------- Intent detection (CORREGIDO CON REGEX) ----------------
    def _extract_asset(self, question: str) -> str:
        pattern = re.compile(r"(show\s+all\s+owners\s+of|owners\s+of|dueños\s+de)", re.IGNORECASE)
        clean_q = pattern.sub("", question).strip()
        return clean_q

    def _extract_manager(self, question: str) -> str:
        pattern = re.compile(r"(show\s+holdings\s+of|holdings\s+of|tenencias\s+de)", re.IGNORECASE)
        clean_q = pattern.sub("", question).strip()
        return clean_q

    def _resolve_asset(self, asset_hint: str) -> str:
        with self.driver.session() as session:
            cypher = """
            MATCH (a:Asset)
            WHERE toLower(a.cusip) CONTAINS toLower($hint) 
               OR toLower(a.name) CONTAINS toLower($hint)
               OR toLower(a.ticker) CONTAINS toLower($hint)
            RETURN a.cusip AS cusip
            LIMIT 1
            """
            rec = session.run(cypher, hint=asset_hint).single()
            # Si encontramos el CUSIP real en la DB, lo devolvemos.
            # Si no, devolvemos el hint original (fallback).
            return rec["cusip"] if rec else asset_hint

    def _detect_intent(self, question: str) -> dict:
        q = question.lower()

        if "owners" in q or "dueños" in q:
            return {
                "intent": "owners_of_asset",
                "entity": self._extract_asset(question)
            }

        if "holdings" in q or "tenencias" in q:
            return {
                "intent": "holdings_of_manager",
                "entity": self._extract_manager(question)
            }

        return {"intent": "unknown"}

    # ---------------- Cypher templates ----------------
    def _run_cypher(self, intent: str, entity: str):
        with self.driver.session() as session:

            if intent == "holdings_of_manager":
                cypher = """
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toLower(m.name) CONTAINS toLower($name)
                RETURN a.cusip AS asset, a.name as asset_name, h.weight AS weight
                ORDER BY h.weight DESC
                LIMIT 20
                """
                result = session.run(cypher, name=entity)
                return [dict(r) for r in result]

            if intent == "owners_of_asset":
                cypher = """
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE a.cusip = $asset OR toLower(a.name) CONTAINS toLower($asset)
                RETURN m.name AS manager, h.weight AS weight
                ORDER BY h.weight DESC
                LIMIT 20
                """
                result = session.run(cypher, asset=entity)
                return [dict(r) for r in result]

            return []

    # ---------------- LLM stage ----------------
    def _stage_llm(self, question: str, rows: list) -> str:
        chain = self.prompt | self.llm.get_client() | StrOutputParser()

        context = "\n".join(str(r) for r in rows)

        return chain.invoke({
            "question": question,
            "context": context
        })

    # ---------------- Public entry ----------------
    def handle(self, question: str) -> str:
        self.logger.info("[GraphRAG] question_received", {"q": question})

        intent_dto = self._detect_intent(question)

        if intent_dto["intent"] == "unknown":
            return "Unsupported GraphRAG query."

        entity = intent_dto["entity"]

        entity = entity.strip()

        if intent_dto["intent"] == "owners_of_asset":
            entity = self._resolve_asset(entity)

        rows = self._run_cypher(
            intent_dto["intent"],
            entity
        )

        if not rows:
            return f"No results found in graph for entity: {intent_dto['entity']}"

        return self._stage_llm(question, rows)
