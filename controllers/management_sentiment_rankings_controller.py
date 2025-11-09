from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import websockets
from common.config.settings import settings
from common.util.app_logger import AppLogger

class ManagementSentimentRankingsController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_sentiment_rankings")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("management_sentiment_rankings.html", {"request": request})

        @self.router.post("/analyze")
        async def analyze(query: str = Form(...)):
            if not query.strip():
                return JSONResponse({"message": "error", "bot_response": "❌ La consulta no puede estar vacía."})

            prompt = query.strip()
            print(f"Invoking bot {settings.sentiment_ranking_url} w/ message: {prompt}")
            uri = settings.sentiment_ranking_url
            async with websockets.connect(uri) as ws:
                await ws.send(prompt)
                response = await ws.recv()
            return JSONResponse({"message": "ok", "bot_response": response})

        self.logger = AppLogger.get_logger("ManagementSentimentRankingsController")
