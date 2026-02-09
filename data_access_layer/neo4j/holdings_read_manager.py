# holdings_read_manager.py
"""
Manager for reading 13F Holdings data from Neo4j
"""

from neo4j import GraphDatabase
from typing import List, Optional, Tuple

from common.dto.fund_security_ownership.crowded_trade_dto import CrowdedTradeDTO
from common.dto.fund_security_ownership.period_dto import PeriodDTO


class HoldingsReadManager:
    """
    Manager for reading institutional holdings from Neo4j
    Handles all 13F holdings read queries
    """

    def __init__(
            self,
            neo4j_uri: str,
            neo4j_user: str,
            neo4j_pass: str,
    ):
        self.driver = GraphDatabase.driver(
            neo4j_uri,
            auth=(neo4j_user, neo4j_pass),
        )

    def close(self):
        self.driver.close()

    # ---------- Available Periods ----------
    def get_available_periods(self) -> List[PeriodDTO]:
        """Get all available year/quarter combinations"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH ()-[h:HOLDS]->()
                WITH DISTINCT h.year AS year, h.quarter AS quarter
                RETURN year, quarter
                ORDER BY year DESC, quarter DESC
            """)

            return [
                PeriodDTO(year=record["year"], quarter=record["quarter"])
                for record in result
            ]

    # ---------- #1 Crowded Trades ----------
    def get_crowded_trades(
            self,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
            min_crowd_score: Optional[float] = None
    ) -> Tuple[List[CrowdedTradeDTO], int]:
        """
        Get crowded trades ranked by crowd_score DESC
        Returns: (list of DTOs, total count)
        """
        with self.driver.session() as session:
            # Build WHERE clause
            where_clause = ""
            if min_crowd_score is not None:
                where_clause = "WHERE crowd_score >= $min_crowd_score"

            # Data query
            data_query = f"""
                MATCH (m:Manager)-[h:HOLDS {{year: $year, quarter: $quarter}}]->(a:Asset)
                WITH a,
                     COUNT(DISTINCT m) AS owners,
                     SUM(h.weight) AS total_weight
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                {where_clause}
                RETURN a.name AS asset,
                       owners,
                       total_weight,
                       crowd_score
                ORDER BY crowd_score DESC
                SKIP $offset
                LIMIT $limit
            """

            params = {
                "year": year,
                "quarter": quarter,
                "offset": offset,
                "limit": limit,
            }
            if min_crowd_score is not None:
                params["min_crowd_score"] = min_crowd_score

            result = session.run(data_query, params)

            data = [
                CrowdedTradeDTO(
                    rank=offset + idx + 1,
                    asset=record["asset"],
                    owners=record["owners"],
                    total_weight=record["total_weight"],
                    crowd_score=record["crowd_score"],
                )
                for idx, record in enumerate(result)
            ]

            # Count query
            count_query = f"""
                MATCH (m:Manager)-[h:HOLDS {{year: $year, quarter: $quarter}}]->(a:Asset)
                WITH a,
                     COUNT(DISTINCT m) AS owners,
                     SUM(h.weight) AS total_weight
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                {where_clause}
                RETURN COUNT(*) AS total
            """

            count_params = {"year": year, "quarter": quarter}
            if min_crowd_score is not None:
                count_params["min_crowd_score"] = min_crowd_score

            total = session.run(count_query, count_params).single()["total"]

            return data, total

    # ---------- #2 Capitulation Trades ----------
    def get_capitulation_trades(
            self,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
            min_owners: int = 5
    ) -> Tuple[List[CrowdedTradeDTO], int]:
        """
        Get capitulation trades ranked by crowd_score ASC
        Filtered by min_owners to remove noise
        Returns: (list of DTOs, total count)
        """
        with self.driver.session() as session:
            # Data query
            data_query = """
                MATCH (m:Manager)-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset)
                WITH a,
                     COUNT(DISTINCT m) AS owners,
                     SUM(h.weight) AS total_weight
                WHERE owners >= $min_owners
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                RETURN a.name AS asset,
                       owners,
                       total_weight,
                       crowd_score
                ORDER BY crowd_score ASC
                SKIP $offset
                LIMIT $limit
            """

            result = session.run(data_query, {
                "year": year,
                "quarter": quarter,
                "min_owners": min_owners,
                "offset": offset,
                "limit": limit,
            })

            data = [
                CrowdedTradeDTO(
                    rank=offset + idx + 1,
                    asset=record["asset"],
                    owners=record["owners"],
                    total_weight=record["total_weight"],
                    crowd_score=record["crowd_score"],
                )
                for idx, record in enumerate(result)
            ]

            # Count query
            count_query = """
                MATCH (m:Manager)-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset)
                WITH a, COUNT(DISTINCT m) AS owners
                WHERE owners >= $min_owners
                RETURN COUNT(*) AS total
            """

            total = session.run(count_query, {
                "year": year,
                "quarter": quarter,
                "min_owners": min_owners,
            }).single()["total"]

            return data, total