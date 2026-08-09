# holdings_read_manager.py
"""
Manager for reading 13F Holdings data from Neo4j

v2 — adds a pre-computed aggregate layer (:AssetPeriodStats) so the heavy
     "count owners + sum weight for every asset of a period" pass runs ONCE
     per period instead of once per query.

     Everything that used to scan the whole HOLDS graph on each search now
     reads a single node per asset/period.
"""

import time
from datetime import datetime
from neo4j import GraphDatabase
from typing import List, Optional, Tuple

from common.dto.fund_security_ownership.asset_dto import AssetDTO
from common.dto.fund_security_ownership.asset_owner_dto import AssetOwnerDTO
from common.dto.fund_security_ownership.asset_stats_dto import AssetStatsDTO
from common.dto.fund_security_ownership.crowded_trade_dto import CrowdedTradeDTO
from common.dto.fund_security_ownership.crowd_transition_dto import CrowdTransitionDTO
from common.dto.fund_security_ownership.manager_dto import ManagerDTO
from common.dto.fund_security_ownership.new_position_dto import NewPositionDTO
from common.dto.fund_security_ownership.period_dto import PeriodDTO
from common.dto.fund_security_ownership.period_stats_dto import PeriodStatsDTO, SizeBucketStatsDTO
from common.dto.fund_security_ownership.portfolio_holding_dto import PortfolioHoldingDTO


class HoldingsReadManager:
    """
    Manager for reading institutional holdings from Neo4j
    Handles all 13F holdings read queries
    """

    # ---------- Tier thresholds (percentile of crowd_score inside the period) ----------
    # tier 1 = the most crowded 1% ... tier 5 = the abandoned bottom 40%
    TIER_CUTS = [0.01, 0.05, 0.25, 0.60]

    TIER_LABELS = {
        1: "1 · Mega crowded",
        2: "2 · Crowded",
        3: "3 · Moderate",
        4: "4 · Light",
        5: "5 · Abandoned",
    }

    # ---------- Size buckets ----------
    # NOTE: there is no market cap in the graph (13F only carries cusip + value),
    # so size is proxied by the TOTAL INSTITUTIONAL DOLLAR VALUE held in the asset.
    # It correlates strongly with market cap but it is NOT market cap.
    SIZE_CUTS = [
        (200e9, "MEGA"),
        (10e9, "LARGE"),
        (2e9, "MID"),
        (300e6, "SMALL"),
    ]
    SIZE_ORDER = ["MEGA", "LARGE", "MID", "SMALL", "MICRO"]

    PERIODS_CACHE_TTL_SECONDS = 300

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
        self._periods_cache = None
        self._periods_cache_ts = 0.0
        self._seeded = False

    def close(self):
        self.driver.close()

    # =====================================================================
    #  SCHEMA
    # =====================================================================
    def ensure_indexes(self) -> List[str]:
        """
        Creates the indexes the aggregate layer needs. Idempotent.
        Safe to call on every boot.
        """
        statements = [
            "CREATE INDEX aps_period IF NOT EXISTS "
            "FOR (s:AssetPeriodStats) ON (s.year, s.quarter)",

            "CREATE INDEX aps_cusip_period IF NOT EXISTS "
            "FOR (s:AssetPeriodStats) ON (s.cusip, s.year, s.quarter)",

            "CREATE INDEX aps_score IF NOT EXISTS "
            "FOR (s:AssetPeriodStats) ON (s.crowd_score)",

            "CREATE INDEX asset_cusip IF NOT EXISTS "
            "FOR (a:Asset) ON (a.cusip)",

            "CREATE INDEX manager_name IF NOT EXISTS "
            "FOR (m:Manager) ON (m.name)",

            "CREATE INDEX period_key IF NOT EXISTS "
            "FOR (p:Period) ON (p.year, p.quarter)",
        ]

        applied = []
        with self.driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                    applied.append(stmt.split(" ")[2])
                except Exception:
                    pass
        return applied

    # =====================================================================
    #  AGGREGATE BUILD  (run once per period)
    # =====================================================================
    def build_period_aggregates(self, year: str, quarter: str) -> int:
        """
        Collapses every HOLDS edge of a period into one :AssetPeriodStats node
        per asset, then assigns percentile rank, crowding tier and size bucket.

        Returns the number of assets aggregated.
        """
        year = str(year)
        quarter = str(quarter)

        with self.driver.session() as session:

            # -- 1. wipe the previous snapshot of this period --------------
            session.run("""
                MATCH (s:AssetPeriodStats {year: $year, quarter: $quarter})
                DETACH DELETE s
            """, {"year": year, "quarter": quarter})

            # -- 2. aggregate the graph ------------------------------------
            # toString() on both sides: the loader writes year as int and
            # quarter as string, the UI always sends strings.
            session.run("""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH a,
                     COUNT(DISTINCT m) AS owners,
                     SUM(h.weight)     AS total_weight
                CREATE (s:AssetPeriodStats {
                    cusip:        a.cusip,
                    asset:        a.name,
                    year:         $year,
                    quarter:      $quarter,
                    owners:       owners,
                    total_weight: total_weight,
                    crowd_score:  owners * total_weight
                })
            """, {"year": year, "quarter": quarter})

            # -- 3. percentile rank + tier ---------------------------------
            c1, c2, c3, c4 = self.TIER_CUTS
            session.run(f"""
                MATCH (s:AssetPeriodStats {{year: $year, quarter: $quarter}})
                WITH s ORDER BY s.crowd_score DESC
                WITH collect(s) AS rows
                WITH rows, size(rows) AS total
                WHERE total > 0
                UNWIND range(0, total - 1) AS i
                WITH rows[i] AS s, toFloat(i) / toFloat(total) AS pct
                SET s.pct_rank = pct,
                    s.tier = CASE
                        WHEN pct < {c1} THEN 1
                        WHEN pct < {c2} THEN 2
                        WHEN pct < {c3} THEN 3
                        WHEN pct < {c4} THEN 4
                        ELSE 5
                    END
            """, {"year": year, "quarter": quarter})

            # -- 4. size bucket (proxy: institutional dollar value) --------
            mega, large, mid, small = (c[0] for c in self.SIZE_CUTS)
            session.run(f"""
                MATCH (s:AssetPeriodStats {{year: $year, quarter: $quarter}})
                SET s.size_bucket = CASE
                    WHEN s.total_weight >= {mega}  THEN 'MEGA'
                    WHEN s.total_weight >= {large} THEN 'LARGE'
                    WHEN s.total_weight >= {mid}   THEN 'MID'
                    WHEN s.total_weight >= {small} THEN 'SMALL'
                    ELSE 'MICRO'
                END
            """, {"year": year, "quarter": quarter})

            # -- 5. period marker + count ----------------------------------
            total = session.run("""
                MATCH (s:AssetPeriodStats {year: $year, quarter: $quarter})
                RETURN COUNT(s) AS total
            """, {"year": year, "quarter": quarter}).single()["total"]

            session.run("""
                MERGE (p:Period {year: $year, quarter: $quarter})
                SET p.assets = $total, p.built_at = $built_at
            """, {
                "year": year,
                "quarter": quarter,
                "total": total,
                "built_at": datetime.utcnow().isoformat(timespec="seconds"),
            })

        self._periods_cache = None
        return total

    def has_aggregates(self, year: str, quarter: str) -> bool:
        with self.driver.session() as session:
            row = session.run("""
                MATCH (s:AssetPeriodStats {year: $year, quarter: $quarter})
                RETURN COUNT(s) AS total
            """, {"year": str(year), "quarter": str(quarter)}).single()
            return bool(row and row["total"] > 0)

    def get_aggregate_status(self) -> List[PeriodStatsDTO]:
        """One row per available period telling whether it was pre-computed."""
        periods = self.get_available_periods()

        with self.driver.session() as session:
            built = {
                (r["year"], r["quarter"]): (r["assets"], r["built_at"])
                for r in session.run("""
                    MATCH (p:Period)
                    WHERE p.built_at IS NOT NULL
                    RETURN p.year AS year, p.quarter AS quarter,
                           p.assets AS assets, p.built_at AS built_at
                """)
            }

        out = []
        for p in periods:
            key = (str(p.year), str(p.quarter))
            hit = built.get(key)
            out.append(PeriodStatsDTO(
                year=str(p.year),
                quarter=str(p.quarter),
                assets=hit[0] if hit else 0,
                built=hit is not None,
                built_at=hit[1] if hit else None,
            ))
        return out

    # =====================================================================
    #  Available Periods
    # =====================================================================
    def get_available_periods(self, force_refresh: bool = False) -> List[PeriodDTO]:
        """
        Get all available year/quarter combinations.

        Fast path: the :Period markers written by build_period_aggregates.
        Slow path: the original DISTINCT over every HOLDS edge (only used the
        first time, before any aggregate exists).
        Result is cached in memory for PERIODS_CACHE_TTL_SECONDS.
        """
        now = time.time()
        if (not force_refresh
                and self._periods_cache is not None
                and (now - self._periods_cache_ts) < self.PERIODS_CACHE_TTL_SECONDS):
            return self._periods_cache

        with self.driver.session() as session:
            # Once per process (and on every explicit refresh) walk the graph so
            # the :Period markers cover EVERY period, built or not. Without this
            # the fast path below would only ever list the aggregated ones.
            fast = [] if (force_refresh or not self._seeded) else list(session.run("""
                MATCH (p:Period)
                RETURN p.year AS year, p.quarter AS quarter
                ORDER BY year DESC, quarter DESC
            """))

            if fast:
                periods = [
                    PeriodDTO(year=str(r["year"]), quarter=str(r["quarter"]))
                    for r in fast
                ]
            else:
                # First run: walk the graph once and leave a :Period marker for
                # EVERY period found, built or not, so the fast path above keeps
                # returning the full list afterwards.
                result = session.run("""
                    MATCH ()-[h:HOLDS]->()
                    WHERE h.year IS NOT NULL AND h.quarter IS NOT NULL
                    WITH DISTINCT toString(h.year) AS year, toString(h.quarter) AS quarter
                    MERGE (p:Period {year: year, quarter: quarter})
                    RETURN year, quarter
                    ORDER BY year DESC, quarter DESC
                """)
                periods = [
                    PeriodDTO(year=record["year"], quarter=record["quarter"])
                    for record in result
                ]
                self._seeded = True

        self._periods_cache = periods
        self._periods_cache_ts = now
        return periods

    # =====================================================================
    #  #1 Crowded Trades
    # =====================================================================
    def get_crowded_trades(
            self,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
            min_crowd_score: Optional[float] = None,
            size_bucket: Optional[str] = None,
    ) -> Tuple[List[CrowdedTradeDTO], int]:
        """
        Get crowded trades ranked by crowd_score DESC.
        Reads the pre-computed aggregates; falls back to the raw graph when
        the period has not been built yet.
        Returns: (list of DTOs, total count)
        """
        year, quarter = str(year), str(quarter)

        if not self.has_aggregates(year, quarter):
            return self._get_crowded_trades_raw(
                year, quarter, offset, limit, min_crowd_score
            )

        return self._ranked_from_aggregates(
            year=year,
            quarter=quarter,
            offset=offset,
            limit=limit,
            order="DESC",
            min_crowd_score=min_crowd_score,
            min_owners=None,
            size_bucket=size_bucket,
        )

    # =====================================================================
    #  #2 Capitulation Trades
    # =====================================================================
    def get_capitulation_trades(
            self,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
            min_owners: int = 5,
            size_bucket: Optional[str] = None,
    ) -> Tuple[List[CrowdedTradeDTO], int]:
        """
        Get capitulation trades ranked by crowd_score ASC.
        Filtered by min_owners to remove noise.
        """
        year, quarter = str(year), str(quarter)

        if not self.has_aggregates(year, quarter):
            return self._get_capitulation_trades_raw(
                year, quarter, offset, limit, min_owners
            )

        return self._ranked_from_aggregates(
            year=year,
            quarter=quarter,
            offset=offset,
            limit=limit,
            order="ASC",
            min_crowd_score=None,
            min_owners=min_owners,
            size_bucket=size_bucket,
        )

    def _ranked_from_aggregates(
            self,
            year: str,
            quarter: str,
            offset: int,
            limit: int,
            order: str,
            min_crowd_score: Optional[float],
            min_owners: Optional[int],
            size_bucket: Optional[str],
    ) -> Tuple[List[CrowdedTradeDTO], int]:

        filters = []
        params = {
            "year": year,
            "quarter": quarter,
            "offset": offset,
            "limit": limit,
        }

        if min_crowd_score is not None:
            filters.append("s.crowd_score >= $min_crowd_score")
            params["min_crowd_score"] = min_crowd_score
        if min_owners is not None:
            filters.append("s.owners >= $min_owners")
            params["min_owners"] = min_owners
        if size_bucket:
            filters.append("s.size_bucket = $size_bucket")
            params["size_bucket"] = size_bucket

        where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (s:AssetPeriodStats {{year: $year, quarter: $quarter}})
                {where_clause}
                RETURN s.asset        AS asset,
                       s.owners       AS owners,
                       s.total_weight AS total_weight,
                       s.crowd_score  AS crowd_score
                ORDER BY s.crowd_score {order}
                SKIP $offset
                LIMIT $limit
            """, params)

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

            count_params = {k: v for k, v in params.items()
                            if k not in ("offset", "limit")}
            total = session.run(f"""
                MATCH (s:AssetPeriodStats {{year: $year, quarter: $quarter}})
                {where_clause}
                RETURN COUNT(s) AS total
            """, count_params).single()["total"]

        return data, total

    # ---------- legacy fallbacks (period not aggregated yet) -------------
    def _get_crowded_trades_raw(self, year, quarter, offset, limit, min_crowd_score):
        with self.driver.session() as session:
            where_clause = ""
            if min_crowd_score is not None:
                where_clause = "WHERE crowd_score >= $min_crowd_score"

            params = {"year": year, "quarter": quarter,
                      "offset": offset, "limit": limit}
            if min_crowd_score is not None:
                params["min_crowd_score"] = min_crowd_score

            result = session.run(f"""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH a, COUNT(DISTINCT m) AS owners, SUM(h.weight) AS total_weight
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                {where_clause}
                RETURN a.name AS asset, owners, total_weight, crowd_score
                ORDER BY crowd_score DESC
                SKIP $offset LIMIT $limit
            """, params)

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

            count_params = {"year": year, "quarter": quarter}
            if min_crowd_score is not None:
                count_params["min_crowd_score"] = min_crowd_score

            total = session.run(f"""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH a, COUNT(DISTINCT m) AS owners, SUM(h.weight) AS total_weight
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                {where_clause}
                RETURN COUNT(*) AS total
            """, count_params).single()["total"]

        return data, total

    def _get_capitulation_trades_raw(self, year, quarter, offset, limit, min_owners):
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH a, COUNT(DISTINCT m) AS owners, SUM(h.weight) AS total_weight
                WHERE owners >= $min_owners
                WITH a, owners, total_weight, (owners * total_weight) AS crowd_score
                RETURN a.name AS asset, owners, total_weight, crowd_score
                ORDER BY crowd_score ASC
                SKIP $offset LIMIT $limit
            """, {"year": year, "quarter": quarter, "min_owners": min_owners,
                  "offset": offset, "limit": limit})

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

            total = session.run("""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH a, COUNT(DISTINCT m) AS owners
                WHERE owners >= $min_owners
                RETURN COUNT(*) AS total
            """, {"year": year, "quarter": quarter,
                  "min_owners": min_owners}).single()["total"]

        return data, total

    # =====================================================================
    #  #5 Crowding transitions between two quarters
    # =====================================================================
    def get_crowd_transitions(
            self,
            from_year: str,
            from_quarter: str,
            to_year: str,
            to_quarter: str,
            direction: str = "LOADING",   # LOADING | UNLOADING | ALL
            min_tier_jump: int = 1,
            min_owners: int = 5,
            size_bucket: Optional[str] = None,
            offset: int = 0,
            limit: int = 100,
    ) -> Tuple[List[CrowdTransitionDTO], int]:
        """
        Assets that changed crowding tier between two quarters.

        LOADING   -> tier number went DOWN (got more crowded): funds piling in
        UNLOADING -> tier number went UP (got less crowded): funds leaving
        """
        params = {
            "fy": str(from_year), "fq": str(from_quarter),
            "ty": str(to_year), "tq": str(to_quarter),
            "min_tier_jump": int(min_tier_jump),
            "min_owners": int(min_owners),
            "offset": offset, "limit": limit,
        }

        filters = ["b.owners >= $min_owners"]

        if direction == "LOADING":
            filters.append("(a.tier - b.tier) >= $min_tier_jump")
            order = "ORDER BY (a.tier - b.tier) DESC, (b.owners - a.owners) DESC"
        elif direction == "UNLOADING":
            filters.append("(b.tier - a.tier) >= $min_tier_jump")
            order = "ORDER BY (b.tier - a.tier) DESC, (a.owners - b.owners) DESC"
        else:
            filters.append("abs(a.tier - b.tier) >= $min_tier_jump")
            order = "ORDER BY abs(a.tier - b.tier) DESC, abs(b.owners - a.owners) DESC"

        if size_bucket:
            filters.append("b.size_bucket = $size_bucket")
            params["size_bucket"] = size_bucket

        where_clause = "WHERE " + " AND ".join(filters)

        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (b:AssetPeriodStats {{year: $ty, quarter: $tq}})
                MATCH (a:AssetPeriodStats {{cusip: b.cusip, year: $fy, quarter: $fq}})
                {where_clause}
                RETURN b.cusip        AS cusip,
                       b.asset        AS asset,
                       b.size_bucket  AS size_bucket,
                       a.tier         AS from_tier,
                       b.tier         AS to_tier,
                       a.owners       AS from_owners,
                       b.owners       AS to_owners,
                       a.total_weight AS from_weight,
                       b.total_weight AS to_weight,
                       a.crowd_score  AS from_crowd_score,
                       b.crowd_score  AS to_crowd_score
                {order}
                SKIP $offset
                LIMIT $limit
            """, params)

            data = []
            for idx, r in enumerate(result):
                fw = r["from_weight"] or 0.0
                tw = r["to_weight"] or 0.0
                delta_pct = ((tw - fw) / fw * 100.0) if fw else None
                tier_delta = r["from_tier"] - r["to_tier"]

                data.append(CrowdTransitionDTO(
                    rank=offset + idx + 1,
                    cusip=r["cusip"],
                    asset=r["asset"],
                    size_bucket=r["size_bucket"],
                    from_tier=r["from_tier"],
                    to_tier=r["to_tier"],
                    tier_delta=tier_delta,
                    direction="LOADING" if tier_delta > 0 else "UNLOADING",
                    from_owners=r["from_owners"],
                    to_owners=r["to_owners"],
                    owners_delta=r["to_owners"] - r["from_owners"],
                    from_weight=fw,
                    to_weight=tw,
                    weight_delta_pct=delta_pct,
                    from_crowd_score=r["from_crowd_score"],
                    to_crowd_score=r["to_crowd_score"],
                ))

            count_params = {k: v for k, v in params.items()
                            if k not in ("offset", "limit")}
            total = session.run(f"""
                MATCH (b:AssetPeriodStats {{year: $ty, quarter: $tq}})
                MATCH (a:AssetPeriodStats {{cusip: b.cusip, year: $fy, quarter: $fq}})
                {where_clause}
                RETURN COUNT(*) AS total
            """, count_params).single()["total"]

        return data, total

    def get_transition_matrix(
            self,
            from_year: str,
            from_quarter: str,
            to_year: str,
            to_quarter: str,
    ) -> List[dict]:
        """5x5 matrix: how many assets moved from tier X to tier Y."""
        with self.driver.session() as session:
            rows = session.run("""
                MATCH (b:AssetPeriodStats {year: $ty, quarter: $tq})
                MATCH (a:AssetPeriodStats {cusip: b.cusip, year: $fy, quarter: $fq})
                RETURN a.tier AS from_tier, b.tier AS to_tier, COUNT(*) AS assets
                ORDER BY from_tier, to_tier
            """, {"fy": str(from_year), "fq": str(from_quarter),
                  "ty": str(to_year), "tq": str(to_quarter)})

            return [
                {"from_tier": r["from_tier"],
                 "to_tier": r["to_tier"],
                 "assets": r["assets"]}
                for r in rows
            ]

    # =====================================================================
    #  #6 New positions between two quarters
    # =====================================================================
    def get_new_positions(
            self,
            from_year: str,
            from_quarter: str,
            to_year: str,
            to_quarter: str,
            min_owners: int = 5,
            brand_new_only: bool = False,
            size_bucket: Optional[str] = None,
            offset: int = 0,
            limit: int = 100,
    ) -> Tuple[List[NewPositionDTO], int]:
        """
        Assets that appear in the destination quarter and did NOT exist
        (or had fewer than min_owners owners) in the base quarter.

        This is the useful read of the Capitulation screen: instead of the
        left-for-dead names sitting at the bottom of the ranking, it surfaces
        names institutions just started buying.
        """
        params = {
            "fy": str(from_year), "fq": str(from_quarter),
            "ty": str(to_year), "tq": str(to_quarter),
            "min_owners": int(min_owners),
            "offset": offset, "limit": limit,
        }

        filters = ["b.owners >= $min_owners"]
        if brand_new_only:
            filters.append("a IS NULL")
        else:
            filters.append("(a IS NULL OR a.owners < $min_owners)")
        if size_bucket:
            filters.append("b.size_bucket = $size_bucket")
            params["size_bucket"] = size_bucket

        where_clause = "WHERE " + " AND ".join(filters)

        with self.driver.session() as session:
            result = session.run(f"""
                MATCH (b:AssetPeriodStats {{year: $ty, quarter: $tq}})
                OPTIONAL MATCH (a:AssetPeriodStats {{cusip: b.cusip, year: $fy, quarter: $fq}})
                WITH b, a
                {where_clause}
                RETURN b.cusip       AS cusip,
                       b.asset       AS asset,
                       b.size_bucket AS size_bucket,
                       b.owners      AS to_owners,
                       b.total_weight AS to_weight,
                       b.crowd_score AS to_crowd_score,
                       b.tier        AS to_tier,
                       a.owners      AS from_owners
                ORDER BY b.owners DESC, b.total_weight DESC
                SKIP $offset
                LIMIT $limit
            """, params)

            data = [
                NewPositionDTO(
                    rank=offset + idx + 1,
                    cusip=r["cusip"],
                    asset=r["asset"],
                    size_bucket=r["size_bucket"],
                    to_owners=r["to_owners"],
                    to_weight=r["to_weight"],
                    to_crowd_score=r["to_crowd_score"],
                    to_tier=r["to_tier"],
                    from_owners=r["from_owners"] or 0,
                    is_brand_new=r["from_owners"] is None,
                )
                for idx, r in enumerate(result)
            ]

            count_params = {k: v for k, v in params.items()
                            if k not in ("offset", "limit")}
            total = session.run(f"""
                MATCH (b:AssetPeriodStats {{year: $ty, quarter: $tq}})
                OPTIONAL MATCH (a:AssetPeriodStats {{cusip: b.cusip, year: $fy, quarter: $fq}})
                WITH b, a
                {where_clause}
                RETURN COUNT(*) AS total
            """, count_params).single()["total"]

        return data, total

    # =====================================================================
    #  #7 Crowding by size bucket
    # =====================================================================
    def get_size_bucket_stats(self, year: str, quarter: str) -> List[SizeBucketStatsDTO]:
        """Crowding aggregated by size bucket for one period."""
        with self.driver.session() as session:
            rows = session.run("""
                MATCH (s:AssetPeriodStats {year: $year, quarter: $quarter})
                RETURN s.size_bucket        AS size_bucket,
                       COUNT(s)             AS assets,
                       avg(s.owners)        AS avg_owners,
                       sum(s.total_weight)  AS total_weight,
                       avg(s.crowd_score)   AS avg_crowd_score,
                       max(s.crowd_score)   AS max_crowd_score
            """, {"year": str(year), "quarter": str(quarter)})

            by_bucket = {
                r["size_bucket"]: SizeBucketStatsDTO(
                    size_bucket=r["size_bucket"],
                    assets=r["assets"],
                    avg_owners=r["avg_owners"] or 0.0,
                    total_weight=r["total_weight"] or 0.0,
                    avg_crowd_score=r["avg_crowd_score"] or 0.0,
                    max_crowd_score=r["max_crowd_score"] or 0.0,
                )
                for r in rows if r["size_bucket"]
            }

        return [by_bucket[b] for b in self.SIZE_ORDER if b in by_bucket]

    # =====================================================================
    #  #3 Portfolio Viewer
    # =====================================================================
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
        year, quarter = str(year), str(quarter)

        with self.driver.session() as session:
            manager_result = session.run("""
                MATCH (m:Manager)
                WHERE toLower(m.name) CONTAINS toLower($manager_name)
                RETURN m.name AS name
                LIMIT 1
            """, {"manager_name": manager_name})
            manager_record = manager_result.single()

            if not manager_record:
                return [], 0, None

            matched_manager = ManagerDTO(name=manager_record["name"])

            result = session.run("""
                MATCH (m:Manager {name: $manager_name})-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                RETURN a.name AS asset, a.cusip AS cusip, h.weight AS weight
                ORDER BY h.weight DESC
                SKIP $offset LIMIT $limit
            """, {
                "manager_name": matched_manager.name,
                "year": year, "quarter": quarter,
                "offset": offset, "limit": limit,
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

            total = session.run("""
                MATCH (m:Manager {name: $manager_name})-[h:HOLDS]->(a:Asset)
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                RETURN COUNT(*) AS total
            """, {
                "manager_name": matched_manager.name,
                "year": year, "quarter": quarter,
            }).single()["total"]

            return data, total, matched_manager

    # =====================================================================
    #  Search Managers
    # =====================================================================
    def search_managers(self, query: str, limit: int = 20) -> List[ManagerDTO]:
        with self.driver.session() as session:
            result = session.run("""
                MATCH (m:Manager)
                WHERE toLower(m.name) CONTAINS toLower($query)
                RETURN DISTINCT m.name AS name
                ORDER BY m.name
                LIMIT $limit
            """, {"query": query, "limit": limit})

            return [ManagerDTO(name=record["name"]) for record in result]

    # =====================================================================
    #  #4 Asset Ownership
    # =====================================================================
    def get_asset_ownership(
            self,
            asset_identifier: str,
            year: str,
            quarter: str,
            offset: int = 0,
            limit: int = 100,
    ) -> Tuple[List[AssetOwnerDTO], int, Optional[AssetDTO], Optional[AssetStatsDTO]]:
        year, quarter = str(year), str(quarter)

        with self.driver.session() as session:
            asset_result = session.run("""
                MATCH (a:Asset)
                WHERE toLower(a.cusip) CONTAINS toLower($asset_identifier)
                   OR toLower(a.name) CONTAINS toLower($asset_identifier)
                RETURN a.cusip AS cusip, a.name AS name
                LIMIT 1
            """, {"asset_identifier": asset_identifier})
            asset_record = asset_result.single()

            if not asset_record:
                return [], 0, None, None

            matched_asset = AssetDTO(
                cusip=asset_record["cusip"],
                name=asset_record["name"],
                ticker=None,
            )

            stats_result = session.run("""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset {cusip: $cusip})
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                WITH COUNT(DISTINCT m) AS total_owners, SUM(h.weight) AS total_weight
                RETURN total_owners, total_weight,
                       total_owners * total_weight AS crowd_score
            """, {"cusip": matched_asset.cusip, "year": year,
                  "quarter": quarter}).single()

            stats = AssetStatsDTO(
                total_owners=stats_result["total_owners"] or 0,
                total_weight=stats_result["total_weight"] or 0.0,
                crowd_score=stats_result["crowd_score"] or 0.0,
            )

            result = session.run("""
                MATCH (m:Manager)-[h:HOLDS]->(a:Asset {cusip: $cusip})
                WHERE toString(h.year) = $year AND toString(h.quarter) = $quarter
                RETURN m.name AS manager, h.weight AS weight
                ORDER BY h.weight DESC
                SKIP $offset LIMIT $limit
            """, {"cusip": matched_asset.cusip, "year": year, "quarter": quarter,
                  "offset": offset, "limit": limit})

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

    # =====================================================================
    #  Search Assets
    # =====================================================================
    def search_assets(self, query: str, limit: int = 20) -> List[AssetDTO]:
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
                AssetDTO(cusip=record["cusip"], name=record["name"], ticker=None)
                for record in result
            ]
