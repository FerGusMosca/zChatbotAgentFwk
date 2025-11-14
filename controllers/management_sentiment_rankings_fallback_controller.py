from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import websockets
from pathlib import Path
from common.config.settings import settings

class ManagementSentimentRankingsFallbackController:
    def __init__(self):
        # Initialize router
        self.router = APIRouter(prefix="/management_sentiment_rankings_fallback")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            # Render main HTML view
            return self.templates.TemplateResponse(
                "management_sentiment_rankings_fallback.html",
                {"request": request}
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

            return JSONResponse({"message": "ok", "bot_response": resp})
