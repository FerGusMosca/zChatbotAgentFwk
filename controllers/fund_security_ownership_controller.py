# fund_security_ownership_controller.py
"""
Controller for Fund Security Ownership Analysis
Provides institutional sentiment analysis based on 13F reports (Crowding & Capitulation)
"""

import os.path
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.config.settings import settings
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
            """#3 - Portfolio Viewer - HARDCODED DATA"""

            hardcoded_portfolios = {
                "berkshire": {
                    "manager": {"cik": "0001067983", "name": "Berkshire Hathaway Inc"},
                    "holdings": [
                        {"cusip": "037833100", "name": "Apple Inc.", "ticker": "AAPL", "weight": 45.2,
                         "shares": 915560000, "value": 174300000000},
                        {"cusip": "060505104", "name": "Bank of America Corp", "ticker": "BAC", "weight": 10.8,
                         "shares": 1032852006, "value": 41500000000},
                        {"cusip": "023135106", "name": "American Express Co", "ticker": "AXP", "weight": 8.7,
                         "shares": 151610700, "value": 33400000000},
                        {"cusip": "191216100", "name": "Coca-Cola Co", "ticker": "KO", "weight": 7.5,
                         "shares": 400000000, "value": 28800000000},
                        {"cusip": "169656105", "name": "Chevron Corporation", "ticker": "CVX", "weight": 5.2,
                         "shares": 126093326, "value": 20000000000},
                    ]
                },
                "bridgewater": {
                    "manager": {"cik": "0001350694", "name": "Bridgewater Associates LP"},
                    "holdings": [
                        {"cusip": "922908363", "name": "Vanguard FTSE Emerging Markets ETF", "ticker": "VWO",
                         "weight": 8.5, "shares": 45678901, "value": 2100000000},
                        {"cusip": "464287200", "name": "iShares Core S&P 500 ETF", "ticker": "IVV", "weight": 7.2,
                         "shares": 3456789, "value": 1800000000},
                        {"cusip": "742718109", "name": "Procter & Gamble Co", "ticker": "PG", "weight": 5.1,
                         "shares": 8765432, "value": 1300000000},
                    ]
                }
            }

            manager_key = manager_name.lower()
            matched_portfolio = None

            for key, portfolio in hardcoded_portfolios.items():
                if key in manager_key or manager_key in key:
                    matched_portfolio = portfolio
                    break

            if not matched_portfolio:
                matched_portfolio = hardcoded_portfolios["berkshire"]

            holdings = matched_portfolio["holdings"]
            total = len(holdings)
            paginated = holdings[offset:offset + limit]

            return JSONResponse({
                "status": "ok",
                "data": paginated,
                "selected_manager": matched_portfolio["manager"],
                "managers_found": [matched_portfolio["manager"]],
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
            })

        @self.router.post("/asset_ownership")
        async def get_asset_owners(
                asset_identifier: str = Form(...),
                year: str = Form(...),
                quarter: str = Form(...),
                offset: int = Form(0),
                limit: int = Form(100)
        ):
            """#4 - Asset Ownership - HARDCODED DATA"""

            hardcoded_assets = {
                "aapl": {
                    "asset": {"cusip": "037833100", "name": "Apple Inc.", "ticker": "AAPL"},
                    "stats": {
                        "total_owners": 4398,
                        "total_weight": 2654872.31,
                        "total_shares": 15234567890,
                        "total_value": 2870000000000,
                        "crowd_score": 11675432198.7
                    },
                    "owners": [
                        {"cik": "0001067983", "name": "Berkshire Hathaway Inc", "weight": 45.2, "shares": 915560000,
                         "value": 174300000000},
                        {"cik": "0000102909", "name": "Vanguard Group Inc", "weight": 8.1, "shares": 1287439123,
                         "value": 245000000000},
                        {"cik": "0001364742", "name": "BlackRock Inc", "weight": 6.7, "shares": 1045678901,
                         "value": 199000000000},
                    ]
                },
                "msft": {
                    "asset": {"cusip": "594918104", "name": "Microsoft Corporation", "ticker": "MSFT"},
                    "stats": {
                        "total_owners": 4521,
                        "total_weight": 2847593.45,
                        "total_shares": 7456789012,
                        "total_value": 3120000000000,
                        "crowd_score": 12876543210.5
                    },
                    "owners": [
                        {"cik": "0000102909", "name": "Vanguard Group Inc", "weight": 8.9, "shares": 678901234,
                         "value": 284000000000},
                        {"cik": "0001364742", "name": "BlackRock Inc", "weight": 7.4, "shares": 567890123,
                         "value": 237500000000},
                    ]
                }
            }

            asset_key = asset_identifier.lower()
            matched_asset = None

            for key, asset_data in hardcoded_assets.items():
                if (key in asset_key or
                        asset_key in key or
                        asset_key == asset_data["asset"]["cusip"].lower() or
                        asset_key in asset_data["asset"]["name"].lower()):
                    matched_asset = asset_data
                    break

            if not matched_asset:
                matched_asset = hardcoded_assets["aapl"]

            owners = matched_asset["owners"]
            paginated = owners[offset:offset + limit]

            return JSONResponse({
                "status": "ok",
                "data": paginated,
                "selected_asset": matched_asset["asset"],
                "assets_found": [matched_asset["asset"]],
                "stats": matched_asset["stats"],
                "pagination": {
                    "offset": offset,
                    "limit": limit,
                    "total": len(owners),
                    "has_more": (offset + limit) < len(owners)
                },
                "query_params": {
                    "year": year,
                    "quarter": quarter
                }
            })

        @self.router.post("/search_managers")
        async def search_managers(query: str = Form(...)):
            """Search for managers by name - HARDCODED"""

            all_managers = [
                {"cik": "0001067983", "name": "Berkshire Hathaway Inc"},
                {"cik": "0000102909", "name": "Vanguard Group Inc"},
                {"cik": "0001364742", "name": "BlackRock Inc"},
                {"cik": "0001037389", "name": "State Street Corporation"},
                {"cik": "0001350694", "name": "Bridgewater Associates LP"},
                {"cik": "0001273087", "name": "Geode Capital Management"},
                {"cik": "0000093751", "name": "Price T Rowe Associates"},
                {"cik": "0001167557", "name": "Northern Trust Corp"},
                {"cik": "0000895421", "name": "Morgan Stanley"},
                {"cik": "0001697748", "name": "Renaissance Technologies LLC"},
                {"cik": "0001336528", "name": "Citadel Advisors LLC"},
                {"cik": "0001061165", "name": "Two Sigma Investments LP"},
            ]

            query_lower = query.lower()
            matches = [m for m in all_managers if query_lower in m["name"].lower()]

            return JSONResponse({
                "status": "ok",
                "managers": matches[:20]
            })

        @self.router.post("/search_assets")
        async def search_assets(query: str = Form(...)):
            """Search for assets - HARDCODED"""

            all_assets = [
                {"cusip": "037833100", "name": "Apple Inc.", "ticker": "AAPL"},
                {"cusip": "594918104", "name": "Microsoft Corporation", "ticker": "MSFT"},
                {"cusip": "02079K305", "name": "Alphabet Inc. Class A", "ticker": "GOOGL"},
                {"cusip": "023135106", "name": "Amazon.com Inc.", "ticker": "AMZN"},
                {"cusip": "67066G104", "name": "NVIDIA Corporation", "ticker": "NVDA"},
                {"cusip": "30303M102", "name": "Meta Platforms Inc.", "ticker": "META"},
                {"cusip": "88160R101", "name": "Tesla Inc.", "ticker": "TSLA"},
            ]

            query_lower = query.lower()
            matches = [a for a in all_assets
                       if query_lower in a["name"].lower()
                       or query_lower in (a["ticker"] or "").lower()
                       or query_lower in a["cusip"].lower()]

            return JSONResponse({
                "status": "ok",
                "assets": matches[:20]
            })