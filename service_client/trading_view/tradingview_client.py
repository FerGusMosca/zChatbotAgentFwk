# service_client/tradingview_client.py
"""
TradingView Service Client — Generic
--------------------------------------
Responsible for:
  - Holding TradingView credentials (from settings)
  - Providing widget configuration builders (ticker tape, chart)
  - Defining the TVSymbol data contract

NOT responsible for:
  - Which symbols to show (that's the controller's job)
  - Business logic about what instruments are relevant

Usage:
    from service_client.tradingview_client import TradingViewClient, TVSymbol

    client = TradingViewClient()
    config = client.build_ticker_tape_config(symbols, color_theme="dark")
    config = client.build_chart_config(symbol, height=300)
"""

from dataclasses import dataclass, asdict
from common.config.settings import settings


# ── Data contract ──────────────────────────────────────────────────────────────

@dataclass
class TVSymbol:
    """A single TradingView symbol entry."""
    symbol: str        # TradingView symbol string  e.g. "AMEX:SPY"
    label: str         # Short display label          e.g. "SPY"
    description: str   # Full name / tooltip

    def to_dict(self) -> dict:
        return asdict(self)

    def to_ticker_entry(self) -> dict:
        """Format for ticker tape widget symbols array."""
        return {"proName": self.symbol, "title": self.label}


# ── Client ─────────────────────────────────────────────────────────────────────

class TradingViewClient:
    """
    Generic TradingView integration client.
    Builds widget configuration dicts ready to pass to the frontend.
    Credentials loaded from settings for future scraping/private API use.
    """

    # TradingView widget script URL
    WIDGET_SCRIPT_URL = "https://s3.tradingview.com/tv.js"

    def __init__(self):
        self._user = settings.tw_user
        self._pwd  = settings.tw_pwd

    # ── Ticker tape ────────────────────────────────────────────────────────────

    def build_ticker_tape_config(
        self,
        symbols: list[TVSymbol],
        *,
        color_theme: str = "dark",
        is_transparent: bool = True,
        show_symbol_logo: bool = True,
        display_mode: str = "adaptive",
        locale: str = "en",
    ) -> dict:
        """
        Build config dict for TradingView Ticker Tape widget.
        Pass the result directly to `new TradingView.widget(config)` in JS.
        """
        return {
            "colorTheme":      color_theme,
            "isTransparent":   is_transparent,
            "showSymbolLogo":  show_symbol_logo,
            "displayMode":     display_mode,
            "locale":          locale,
            "symbols":         [s.to_ticker_entry() for s in symbols],
        }

    # ── Mini / Medium chart ────────────────────────────────────────────────────

    def build_chart_config(
        self,
        symbol: TVSymbol,
        *,
        height: int = 300,
        color_theme: str = "dark",
        is_transparent: bool = True,
        chart_type: str = "area",
        line_color: str = "#58A6FF",
        top_color: str = "rgba(88,166,255,0.12)",
        bottom_color: str = "rgba(88,166,255,0)",
        locale: str = "en",
    ) -> dict:
        """
        Build config dict for TradingView MediumWidget (area chart).
        Pass the result to `new TradingView.MediumWidget(config)` in JS.
        The `container_id` must be set by the caller (unique per render).
        """
        return {
            "symbols":          [[symbol.symbol, symbol.symbol]],
            "chartOnly":        False,
            "width":            "100%",
            "height":           height,
            "locale":           locale,
            "colorTheme":       color_theme,
            "isTransparent":    is_transparent,
            "autosize":         True,
            "showVolume":       False,
            "scalePosition":    "right",
            "scaleMode":        "Normal",
            "fontFamily":       "IBM Plex Mono, monospace",
            "fontSize":         "10",
            "noTimeScale":      False,
            "valuesTracking":   "1",
            "changeMode":       "price-and-percent",
            "chartType":        chart_type,
            "lineColor":        line_color,
            "lineWidth":        2,
            "backgroundColor":  "rgba(0,0,0,0)",
            "topColor":         top_color,
            "bottomColor":      bottom_color,
        }

    # ── Serialization helpers ──────────────────────────────────────────────────

    @staticmethod
    def symbols_to_json(symbols: list[TVSymbol]) -> list[dict]:
        """Serialize a list of TVSymbol to plain dicts for JSON responses."""
        return [s.to_dict() for s in symbols]