# holdings_read_manager.py
"""
Manager for reading 13F Holdings data from Neo4j
"""

from neo4j import GraphDatabase
from typing import List, Optional, Tuple

from common.dto.fund_security_ownership.asset_dto import AssetDTO
from common.dto.fund_security_ownership.asset_owner_dto import AssetOwnerDTO
from common.dto.fund_security_ownership.asset_stats_dto import AssetStatsDTO
from common.dto.fund_security_ownership.crowded_trade_dto import CrowdedTradeDTO
from common.dto.fund_security_ownership.manager_dto import ManagerDTO

from common.dto.fund_security_ownership.period_dto import PeriodDTO
from common.dto.fund_security_ownership.portfolio_holding_dto import PortfolioHoldingDTO


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

    # ---------- #3 Portfolio Viewer ----------
    def get_portfolio_holdings(
            self,
            manager_name: str,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
    ) -> Tuple[List[PortfolioHoldingDTO], int, Optional[ManagerDTO]]:
        """
        Get all holdings for a specific manager
        Returns: (list of holdings, total count, matched manager)
        """
        with self.driver.session() as session:
            # First find the exact manager (case-insensitive CONTAINS)
            manager_query = """
                MATCH (m:Manager)
                WHERE toLower(m.name) CONTAINS toLower($manager_name)
                RETURN m.name AS name
                LIMIT 1
            """

            manager_result = session.run(manager_query, {"manager_name": manager_name})
            manager_record = manager_result.single()

            if not manager_record:
                return [], 0, None

            matched_manager = ManagerDTO(name=manager_record["name"])

            # Get holdings for this manager
            data_query = """
                MATCH (m:Manager {name: $manager_name})-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset)
                RETURN a.name AS asset,
                       a.cusip AS cusip,
                       h.weight AS weight
                ORDER BY h.weight DESC
                SKIP $offset
                LIMIT $limit
            """

            result = session.run(data_query, {
                "manager_name": matched_manager.name,
                "year": year,
                "quarter": quarter,
                "offset": offset,
                "limit": limit,
            })

            data = [
                PortfolioHoldingDTO(
                    cusip=record["cusip"],
                    name=record["asset"],
                    ticker=None,
                    weight=record["weight"],
                    shares=None,
                    value=None,
                )
                for record in result
            ]

            # Count query
            count_query = """
                MATCH (m:Manager {name: $manager_name})-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset)
                RETURN COUNT(*) AS total
            """

            total = session.run(count_query, {
                "manager_name": matched_manager.name,
                "year": year,
                "quarter": quarter,
            }).single()["total"]

            return data, total, matched_manager

    # ---------- Search Managers ----------
    def search_managers(
            self,
            query: str,
            limit: int = 20,
    ) -> List[ManagerDTO]:
        """
        Search for managers by name (autocomplete)
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Manager)
                WHERE toLower(m.name) CONTAINS toLower($query)
                RETURN DISTINCT m.name AS name
                ORDER BY m.name
                LIMIT $limit
            """, {"query": query, "limit": limit})

            return [ManagerDTO(name=record["name"]) for record in result]

    # ---------- #4 Asset Ownership ----------
    def get_asset_ownership(
            self,
            asset_identifier: str,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
    ) -> Tuple[List[AssetOwnerDTO], int, Optional[AssetDTO], Optional[AssetStatsDTO]]:
        """
        Get all institutional owners for a specific asset
        Returns: (list of owners, total count, matched asset, stats)
        """
        with self.driver.session() as session:
            # Find the asset (by cusip or name)
            asset_query = """
                MATCH (a:Asset)
                WHERE toLower(a.cusip) CONTAINS toLower($asset_identifier)
                   OR toLower(a.name) CONTAINS toLower($asset_identifier)
                RETURN a.cusip AS cusip, a.name AS name
                LIMIT 1
            """

            asset_result = session.run(asset_query, {"asset_identifier": asset_identifier})
            asset_record = asset_result.single()

            if not asset_record:
                return [], 0, None, None

            matched_asset = AssetDTO(
                cusip=asset_record["cusip"],
                name=asset_record["name"],
                ticker=None,
            )

            # Stats query FIRST (before consuming data)
            stats_query = """
                MATCH (m:Manager)-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset {cusip: $cusip})
                WITH COUNT(DISTINCT m) AS total_owners,
                     SUM(h.weight) AS total_weight
                RETURN total_owners,
                       total_weight,
                       total_owners * total_weight AS crowd_score
            """

            stats_result = session.run(stats_query, {
                "cusip": matched_asset.cusip,
                "year": year,
                "quarter": quarter,
            }).single()

            stats = AssetStatsDTO(
                total_owners=stats_result["total_owners"],
                total_weight=stats_result["total_weight"],
                crowd_score=stats_result["crowd_score"],
            )

            # Get owners for this asset
            data_query = """
                MATCH (m:Manager)-[h:HOLDS {year: $year, quarter: $quarter}]->(a:Asset {cusip: $cusip})
                RETURN m.name AS manager,
                       h.weight AS weight
                ORDER BY h.weight DESC
                SKIP $offset
                LIMIT $limit
            """

            result = session.run(data_query, {
                "cusip": matched_asset.cusip,
                "year": year,
                "quarter": quarter,
                "offset": offset,
                "limit": limit,
            })

            data = [
                AssetOwnerDTO(
                    cik=None,
                    name=record["manager"],
                    weight=record["weight"],
                    shares=None,
                    value=None,
                )
                for record in result
            ]

            return data, stats.total_owners, matched_asset, stats

    # ---------- Search Assets ----------
    def search_assets(
            self,
            query: str,
            limit: int = 20,
    ) -> List[AssetDTO]:
        """
        Search for assets by cusip or name (autocomplete)
        """
        with self.driver.session() as session:
            result = session.run("""
                MATCH (a:Asset)
                WHERE toLower(a.cusip) CONTAINS toLower($query)
                   OR toLower(a.name) CONTAINS toLower($query)
                RETURN DISTINCT a.cusip AS cusip, a.name AS name
                ORDER BY a.name
                LIMIT $limit
            """, {"query": query, "limit": limit})

            return [
                AssetDTO(
                    cusip=record["cusip"],
                    name=record["name"],
                    ticker=None,  # Not in Neo4j
                )
                for record in result
            ]