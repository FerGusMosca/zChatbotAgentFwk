# fund_security_ownership_controller.py
"""
Controller for Fund Security Ownership Analysis
Provides institutional sentiment analysis based on 13F reports (Crowding & Capitulation)
"""

import os.path
from dataclasses import asdict
from typing import Optional, List

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.config.settings import settings
from common.dto.fund_security_ownership.manager_dto import ManagerDTO
from common.util.std_in_out.root_locator import RootLocator
from data_access_layer.neo4j.holdings_read_manager import HoldingsReadManager


# TODO: Adjust import path based on your project structure



class FundSecurityOwnershipController:
    """
    Controller for Fund Security Ownership Analysis
    Analyzes institutional holdings from 13F filings stored in Neo4j
    """

    DEFAULT_LIMIT = 100
    MAX_LIMIT = 1000
    MIN_OWNERS_CAPITULATION = 5

    # Neo4j credentials - hardcoded for now
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASS = "test1234"

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

        self._setup_routes()

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
        async def get_available_periods():
            """Get all available year/quarter combinations from Neo4j"""
            try:
                periods = self.holdings_mgr.get_available_periods()

                return JSONResponse({
                    "status": "ok",
                    "periods": [asdict(p) for p in periods]
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/crowded_trades")
        async def get_crowded_trades(
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100),
                min_crowd_score: Optional[float] = Form(None)
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
                        "min_crowd_score": min_crowd_score
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        @self.router.post("/capitulation_trades")
        async def get_capitulation_trades(
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100),
                min_owners: int = Form(5)
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
                        "min_owners": min_owners
                    }
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=500
                )

        # =====================================================================
        # HARDCODED ENDPOINTS (Portfolio Viewer & Asset Ownership) - TO BE IMPLEMENTED
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