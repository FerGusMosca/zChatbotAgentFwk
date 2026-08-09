# fund_security_ownership_controller.py
"""
Controller for Fund Security Ownership Analysis
Provides institutional sentiment analysis based on 13F reports (Crowding & Capitulation)

v2 — adds:
     · /aggregates_status + /build_aggregates : the pre-computed layer that makes
       every ranking fast (and that the transition reports need)
     · /crowd_transitions + /transition_matrix : tier changes between two quarters
     · /new_positions                          : assets institutions just entered
     · /size_buckets                           : crowding grouped by asset size
"""

import os.path
import threading
from dataclasses import asdict
from typing import Optional, List

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.config.settings import settings
from common.dto.fund_security_ownership.manager_dto import ManagerDTO
from common.util.std_in_out.root_locator import RootLocator
from data_access_layer.neo4j.holdings_read_manager import HoldingsReadManager


class FundSecurityOwnershipController:
    """
    Controller for Fund Security Ownership Analysis
    Analyzes institutional holdings from 13F filings stored in Neo4j
    """

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 1000
    MIN_OWNERS_CAPITULATION = 5

    def __init__(self):
        self.router = APIRouter(prefix="/fund_security_ownership")

        templates_path = os.path.join(RootLocator.get_root(), "templates")
        self.templates = Jinja2Templates(directory=templates_path)

        # Initialize Manager for Neo4j access
        self.holdings_mgr = HoldingsReadManager(
            neo4j_uri=settings.neo4j_uri,
            neo4j_user=settings.neo4j_user,
            neo4j_pass=settings.neo4j_pwd,
        )

        # Build state shared with the UI progress panel
        self._build_lock = threading.Lock()
        self._build_state = {
            "running": False,
            "current": None,
            "done": [],
            "failed": [],
            "message": "",
        }

        self._setup_routes()

    # =====================================================================
    #  Aggregate build (background)
    # =====================================================================
    def _run_build(self, periods: List[dict]):
        try:
            self.holdings_mgr.ensure_indexes()

            for p in periods:
                label = f"{p['year']} Q{p['quarter']}"
                with self._build_lock:
                    self._build_state["current"] = label
                    self._build_state["message"] = f"Aggregating {label}…"
                try:
                    total = self.holdings_mgr.build_period_aggregates(
                        p["year"], p["quarter"]
                    )
                    with self._build_lock:
                        self._build_state["done"].append(
                            {"period": label, "assets": total}
                        )
                except Exception as e:
                    with self._build_lock:
                        self._build_state["failed"].append(
                            {"period": label, "error": str(e)}
                        )
        finally:
            with self._build_lock:
                self._build_state["running"] = False
                self._build_state["current"] = None
                self._build_state["message"] = "Done"

    def _setup_routes(self):
        """Setup all API routes"""

        @self.router.get("/", response_class=HTMLResponse)
        async def fund_security_ownership_page(request: Request):
            """Main page for fund security ownership analysis"""
            return self.templates.TemplateResponse(
                "fund_security_ownership.html",
                {"request": request}
            )

        @self.router.get("/available_periods")
        async def get_available_periods(refresh: int = 0):
            """Get all available year/quarter combinations from Neo4j"""
            try:
                periods = self.holdings_mgr.get_available_periods(
                    force_refresh=bool(refresh)
                )

                return JSONResponse({
                    "status": "ok",
                    "periods": [asdict(p) for p in periods]
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  AGGREGATES
        # =================================================================
        @self.router.get("/aggregates_status")
        async def aggregates_status():
            """Which periods are pre-computed + progress of a running build"""
            try:
                rows = self.holdings_mgr.get_aggregate_status()
                with self._build_lock:
                    build = dict(self._build_state)

                return JSONResponse({
                    "status": "ok",
                    "periods": [asdict(r) for r in rows],
                    "build": build,
                })
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/build_aggregates")
        async def build_aggregates(
                year: Optional[str] = Form(None),
                quarter: Optional[str] = Form(None),
                rebuild_all: int = Form(0),
        ):
            """
            Pre-computes :AssetPeriodStats for one period (or all of them).
            Runs in the background; poll /aggregates_status for progress.
            """
            try:
                with self._build_lock:
                    if self._build_state["running"]:
                        return JSONResponse({
                            "status": "error",
                            "message": "A build is already running",
                        }, status_code=409)

                if rebuild_all:
                    periods = [
                        {"year": p.year, "quarter": p.quarter}
                        for p in self.holdings_mgr.get_available_periods(force_refresh=True)
                    ]
                elif year and quarter:
                    periods = [{"year": year, "quarter": quarter}]
                else:
                    return JSONResponse({
                        "status": "error",
                        "message": "Pass year+quarter or rebuild_all=1",
                    }, status_code=400)

                with self._build_lock:
                    self._build_state = {
                        "running": True,
                        "current": None,
                        "done": [],
                        "failed": [],
                        "message": "Starting…",
                    }

                threading.Thread(
                    target=self._run_build, args=(periods,), daemon=True
                ).start()

                return JSONResponse({
                    "status": "ok",
                    "queued": len(periods),
                })

            except Exception as e:
                with self._build_lock:
                    self._build_state["running"] = False
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  #1 CROWDED TRADES
        # =================================================================
        @self.router.post("/crowded_trades")
        async def get_crowded_trades(
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100),
                min_crowd_score: Optional[float] = Form(None),
                size_bucket: Optional[str] = Form(None),
        ):
            """
            #1 - Crowded Trades (Ranking Descendente)
            Returns assets ranked by crowd_score (owners * total_weight)
            """
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                data, total = self.holdings_mgr.get_crowded_trades(
                    year=year,
                    quarter=quarter,
                    offset=offset,
                    limit=limit,
                    min_crowd_score=min_crowd_score,
                    size_bucket=size_bucket or None,
                )

                return JSONResponse({
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "query_params": {
                        "year": year,
                        "quarter": quarter,
                        "min_crowd_score": min_crowd_score,
                        "size_bucket": size_bucket,
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  #2 CAPITULATION
        # =================================================================
        @self.router.post("/capitulation_trades")
        async def get_capitulation_trades(
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100),
                min_owners: int = Form(5),
                size_bucket: Optional[str] = Form(None),
        ):
            """
            #2 - Capitulation Trades (Ranking Ascendente)
            Returns assets with lowest crowd_score (filtered by min_owners)
            """
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                data, total = self.holdings_mgr.get_capitulation_trades(
                    year=year,
                    quarter=quarter,
                    offset=offset,
                    limit=limit,
                    min_owners=min_owners,
                    size_bucket=size_bucket or None,
                )

                return JSONResponse({
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "query_params": {
                        "year": year,
                        "quarter": quarter,
                        "min_owners": min_owners,
                        "size_bucket": size_bucket,
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  #5 CROWD TRANSITIONS  (two quarters)
        # =================================================================
        @self.router.post("/crowd_transitions")
        async def get_crowd_transitions(
                from_year: str = Form(...),
                from_quarter: str = Form(...),
                to_year: str = Form(...),
                to_quarter: str = Form(...),
                direction: str = Form("LOADING"),
                min_tier_jump: int = Form(1),
                min_owners: int = Form(5),
                size_bucket: Optional[str] = Form(None),
                offset: int = Form(0),
                limit: int = Form(100),
        ):
            """Assets that changed crowding tier between two quarters"""
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                for y, q in ((from_year, from_quarter), (to_year, to_quarter)):
                    if not self.holdings_mgr.has_aggregates(y, q):
                        return JSONResponse({
                            "status": "error",
                            "message": f"Period {y} Q{q} is not pre-computed yet — "
                                       f"run Build aggregates first",
                            "needs_build": True,
                        }, status_code=409)

                data, total = self.holdings_mgr.get_crowd_transitions(
                    from_year=from_year,
                    from_quarter=from_quarter,
                    to_year=to_year,
                    to_quarter=to_quarter,
                    direction=direction,
                    min_tier_jump=min_tier_jump,
                    min_owners=min_owners,
                    size_bucket=size_bucket or None,
                    offset=offset,
                    limit=limit,
                )

                return JSONResponse({
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "tier_labels": HoldingsReadManager.TIER_LABELS,
                    "query_params": {
                        "from": f"{from_year} Q{from_quarter}",
                        "to": f"{to_year} Q{to_quarter}",
                        "direction": direction,
                        "min_tier_jump": min_tier_jump,
                        "min_owners": min_owners,
                        "size_bucket": size_bucket,
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/transition_matrix")
        async def get_transition_matrix(
                from_year: str = Form(...),
                from_quarter: str = Form(...),
                to_year: str = Form(...),
                to_quarter: str = Form(...),
        ):
            """5x5 tier-to-tier count matrix between two quarters"""
            try:
                matrix = self.holdings_mgr.get_transition_matrix(
                    from_year=from_year,
                    from_quarter=from_quarter,
                    to_year=to_year,
                    to_quarter=to_quarter,
                )
                return JSONResponse({
                    "status": "ok",
                    "matrix": matrix,
                    "tier_labels": HoldingsReadManager.TIER_LABELS,
                })
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  #6 NEW POSITIONS  (two quarters)
        # =================================================================
        @self.router.post("/new_positions")
        async def get_new_positions(
                from_year: str = Form(...),
                from_quarter: str = Form(...),
                to_year: str = Form(...),
                to_quarter: str = Form(...),
                min_owners: int = Form(5),
                brand_new_only: int = Form(0),
                size_bucket: Optional[str] = Form(None),
                offset: int = Form(0),
                limit: int = Form(100),
        ):
            """Assets institutions entered between the two quarters"""
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                for y, q in ((from_year, from_quarter), (to_year, to_quarter)):
                    if not self.holdings_mgr.has_aggregates(y, q):
                        return JSONResponse({
                            "status": "error",
                            "message": f"Period {y} Q{q} is not pre-computed yet — "
                                       f"run Build aggregates first",
                            "needs_build": True,
                        }, status_code=409)

                data, total = self.holdings_mgr.get_new_positions(
                    from_year=from_year,
                    from_quarter=from_quarter,
                    to_year=to_year,
                    to_quarter=to_quarter,
                    min_owners=min_owners,
                    brand_new_only=bool(brand_new_only),
                    size_bucket=size_bucket or None,
                    offset=offset,
                    limit=limit,
                )

                return JSONResponse({
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "query_params": {
                        "from": f"{from_year} Q{from_quarter}",
                        "to": f"{to_year} Q{to_quarter}",
                        "min_owners": min_owners,
                        "brand_new_only": bool(brand_new_only),
                        "size_bucket": size_bucket,
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =================================================================
        #  #7 SIZE BUCKETS
        # =================================================================
        @self.router.post("/size_buckets")
        async def get_size_buckets(
                year: str = Form(...),
                quarter: str = Form(...),
        ):
            """Crowding grouped by asset size bucket"""
            try:
                if not self.holdings_mgr.has_aggregates(year, quarter):
                    return JSONResponse({
                        "status": "error",
                        "message": f"Period {year} Q{quarter} is not pre-computed yet",
                        "needs_build": True,
                    }, status_code=409)

                rows = self.holdings_mgr.get_size_bucket_stats(year, quarter)

                return JSONResponse({
                    "status": "ok",
                    "data": [asdict(r) for r in rows],
                    "note": "Size is proxied by total institutional dollar value "
                            "(13F filings do not carry market cap).",
                })
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =====================================================================
        # PORTFOLIO VIEWER & ASSET OWNERSHIP
        # =====================================================================

        @self.router.post("/portfolio_viewer")
        async def get_portfolio_holdings(
                manager_name: str = Form(...),
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100)
        ):
            """#3 - Portfolio Viewer"""
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                data, total, matched_manager = self.holdings_mgr.get_portfolio_holdings(
                    manager_name=manager_name,
                    year=year,
                    quarter=quarter,
                    offset=offset,
                    limit=limit,
                )

                response = {
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "query_params": {
                        "year": year,
                        "quarter": quarter
                    }
                }

                if matched_manager:
                    response["selected_manager"] = asdict(matched_manager)
                else:
                    response["message"] = f"No manager found matching '{manager_name}'"

                return JSONResponse(response)

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/search_managers")
        async def search_managers(query: str = Form(...)):
            """Search for managers by name (autocomplete)"""
            try:
                if len(query) < 2:
                    return JSONResponse({"status": "ok", "managers": []})

                managers = self.holdings_mgr.search_managers(query=query, limit=20)

                return JSONResponse({
                    "status": "ok",
                    "managers": [asdict(m) for m in managers]
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/asset_ownership")
        async def get_asset_owners(
                asset_identifier: str = Form(...),
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100)
        ):
            """#4 - Asset Ownership"""
            try:
                limit = min(limit, FundSecurityOwnershipController.MAX_LIMIT)

                data, total, matched_asset, stats = self.holdings_mgr.get_asset_ownership(
                    asset_identifier=asset_identifier,
                    year=year,
                    quarter=quarter,
                    offset=offset,
                    limit=limit,
                )

                response = {
                    "status": "ok",
                    "data": [asdict(d) for d in data],
                    "pagination": {
                        "offset": offset,
                        "limit": limit,
                        "total": total,
                        "has_more": (offset + limit) < total
                    },
                    "query_params": {
                        "year": year,
                        "quarter": quarter
                    }
                }

                if matched_asset:
                    response["selected_asset"] = asdict(matched_asset)
                    response["stats"] = asdict(stats)
                else:
                    response["message"] = f"No asset found matching '{asset_identifier}'"

                return JSONResponse(response)

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/search_assets")
        async def search_assets(query: str = Form(...)):
            """Search for assets by cusip or name (autocomplete)"""
            try:
                if len(query) < 2:
                    return JSONResponse({"status": "ok", "assets": []})

                assets = self.holdings_mgr.search_assets(query=query, limit=20)

                return JSONResponse({
                    "status": "ok",
                    "assets": [asdict(a) for a in assets]
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )
