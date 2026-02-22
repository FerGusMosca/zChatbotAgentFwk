# controllers/bias_dashboard_controller.py
"""
Controller for the Bias Fund main dashboard.

Owns:
  - Which symbols appear in the ticker tape
  - Which symbols appear in the chart switcher
  - Dashboard HTML serving
  - API endpoints that expose symbol configs to the frontend

Uses TradingViewClient only as a generic transport/config builder.
"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.util.std_in_out.root_locator import RootLocator
from service_client.trading_view.tradingview_client import TradingViewClient, TVSymbol

# ── Symbol definitions (business decision — lives here, not in the client) ─────

TICKER_TAPE_SYMBOLS: list[TVSymbol] = [
    TVSymbol("AMEX:SPY",    "SPY",    "SPDR S&P 500 ETF"),
    TVSymbol("NASDAQ:QQQ",  "QQQ",    "Invesco QQQ / Nasdaq 100"),
    TVSymbol("CBOE:VIX",    "VIX",    "CBOE Volatility Index"),
    TVSymbol("NASDAQ:TLT",  "TLT",    "iShares 20+ Year Treasury Bond ETF"),
    TVSymbol("TVC:US10Y",   "US10Y",  "US 10-Year Treasury Yield"),
    TVSymbol("TVC:US02Y",   "US02Y",  "US 2-Year Treasury Yield"),
    TVSymbol("COMEX:GC1!",  "Gold",   "Gold Futures"),
    TVSymbol("FX:EURUSD",   "EUR/USD","Euro / US Dollar"),
]

CHART_SWITCHER_SYMBOLS: list[TVSymbol] = [
    TVSymbol("AMEX:SPY",    "SPY",    "S&P 500 ETF"),
    TVSymbol("NASDAQ:QQQ",  "QQQ",    "Nasdaq 100 ETF"),
    TVSymbol("CBOE:VIX",    "VIX",    "Volatility Index"),
    TVSymbol("NASDAQ:TLT",  "TLT",    "20yr Treasury ETF"),
    TVSymbol("TVC:US01Y",   "US01Y",  "US 1-Year Treasury Yield"),
    TVSymbol("TVC:US02Y",   "US02Y",  "US 2-Year Treasury Yield"),
    TVSymbol("TVC:US05Y",   "US05Y",  "US 5-Year Treasury Yield"),
    TVSymbol("TVC:US10Y",   "US10Y",  "US 10-Year Treasury Yield"),
]


# ── Controller ─────────────────────────────────────────────────────────────────

class BiasDashboardController:
    """
    Routes:
        GET  /                       → Main dashboard HTML
        GET  /api/tv/ticker_symbols  → Ticker tape symbols JSON
        GET  /api/tv/chart_symbols   → Chart switcher symbols JSON
        GET  /api/tv/ticker_config   → Full ticker tape widget config JSON
        GET  /api/tv/chart_config/<symbol> → Chart widget config for a symbol
    """

    def __init__(self):
        self.router    = APIRouter()
        self.tv        = TradingViewClient()

        templates_path = os.path.join(RootLocator.get_root(), "templates")
        self.templates = Jinja2Templates(directory=templates_path)

        # ── HTML page ────────────────────────────────────────────────────────

        @self.router.get("/", response_class=HTMLResponse)
        async def dashboard(request: Request):
            return self.templates.TemplateResponse(
                "main_dashboard.html", {"request": request}
            )

        # ── Symbol lists (for building the switcher UI) ───────────────────────

        @self.router.get("/api/tv/ticker_symbols")
        async def ticker_symbols():
            """Symbol metadata for the ticker tape bar."""
            return JSONResponse(
                TradingViewClient.symbols_to_json(TICKER_TAPE_SYMBOLS)
            )

        @self.router.get("/api/tv/chart_symbols")
        async def chart_symbols():
            """Symbol metadata for the hero chart switcher tabs."""
            return JSONResponse(
                TradingViewClient.symbols_to_json(CHART_SWITCHER_SYMBOLS)
            )

        # ── Widget configs (ready-to-use by the frontend JS) ──────────────────

        @self.router.get("/api/tv/ticker_config")
        async def ticker_config():
            """Full ticker tape widget config — pass directly to new TradingView.widget()."""
            config = self.tv.build_ticker_tape_config(TICKER_TAPE_SYMBOLS)
            return JSONResponse(config)

        @self.router.get("/api/tv/chart_config/{tv_symbol:path}")
        async def chart_config(tv_symbol: str):
            """
            Chart widget config for a given symbol string.
            e.g. GET /api/tv/chart_config/AMEX:SPY
            Returns config ready for new TradingView.MediumWidget(config).
            """
            # Find matching TVSymbol or create a minimal one on the fly
            match = next(
                (s for s in CHART_SWITCHER_SYMBOLS if s.symbol == tv_symbol),
                TVSymbol(tv_symbol, tv_symbol.split(":")[-1], tv_symbol)
            )
            config = self.tv.build_chart_config(match)
            return JSONResponse(config)