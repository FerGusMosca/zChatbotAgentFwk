import re

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import websockets
from pathlib import Path
from common.config.settings import settings, get_settings
from data_access_layer.security_calendar_manager import SecurityCalendarManager


class ManagementSentimentRankingsFallbackController:
    def __init__(self):
        # Initialize router
        self.router = APIRouter(prefix="/management_sentiment_rankings_fallback")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)
        self.manager = SecurityCalendarManager(get_settings().research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            # Render main HTML view
            return self.templates.TemplateResponse(
                "management_sentiment_rankings_fallback.html",
                {"request": request}
            )

        import re

        import re

        def eval_footer( resp: str, yearInput: int,
                        k10Selector: str = None,
                        quarterSelector: str = None) -> str:
            """
            Appends SEC filing calendar dates per symbol at the end of the response text.
            Selectors are STRINGS:
              - k10Selector == "K10"
              - quarterSelector in {"Q1","Q2","Q3"}
            Fully guarded. On error returns resp + error message.
            """

            def _fmt_date(v):
                if not v:
                    return "unknown"
                if hasattr(v, "strftime"):
                    return v.strftime("%Y-%m-%d")
                return str(v)

            try:
                match = re.search(r"Company:\s*([A-Z0-9,\s]+)", resp)
                if not match:
                    return resp

                # Clean symbols (avoid 'TEAM  S' etc.)
                symbols = [
                    s.strip().upper()
                    for s in match.group(1).replace("\n", " ").split(",")
                    if s.strip()
                ]

                footer_lines = []

                for symbol in symbols:
                    try:
                        rows = self.manager.get(symbol, yearInput)
                        if not rows:
                            footer_lines.append(f"{symbol}: filing date unknown")
                            continue

                        row = rows[0]

                        if k10Selector == "K10":
                            date_val = row.get("k10_filing_date")
                            label = "K10"
                        elif quarterSelector in {"Q1", "Q2", "Q3"}:
                            date_val = row.get(f"q{quarterSelector[1]}_filing_date")
                            label = quarterSelector
                        else:
                            footer_lines.append(f"{symbol}: filing selector not provided")
                            continue

                        footer_lines.append(
                            f"{symbol} {label} filing date: {_fmt_date(date_val)}"
                        )

                    except Exception as e:
                        footer_lines.append(
                            f"{symbol}: error resolving filing date -> "
                            f"{type(e).__name__}: {str(e)}"
                        )

                footer = "\n\nSEC Filing Calendar:\n" + "\n".join(footer_lines)
                return resp + footer

            except Exception as e:
                return (
                        resp
                        + "\n\n[ERROR] An error occurred while determining SEC filing calendars: "
                        + f"{type(e).__name__}: {str(e)}"
                )

        @self.router.post("/analyze")
        async def analyze(
            freeText: str = Form(...),
            k10Selector: str = Form(...),
            quarterSelector: str = Form(""),
            yearInput: str = Form(...)
        ):
            # Build final query string
            suffix = f" Usa el archivo {quarterSelector or ''} del {k10Selector} del {yearInput}"
            query_final = f"{freeText.strip()}.{suffix}"

            # Connect to fallback bot WebSocket
            uri = settings.ranking_fallback_url
            async with websockets.connect(uri) as ws:
                await ws.send(query_final)
                resp = await ws.recv()
            resp = eval_footer(resp,yearInput,k10Selector,quarterSelector)
            return JSONResponse({"message": "ok", "bot_response": resp})
