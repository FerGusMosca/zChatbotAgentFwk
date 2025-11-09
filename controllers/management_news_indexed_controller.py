from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import websockets
from common.config.settings import settings
from common.util.app_logger import AppLogger

class NewsIndexedController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_news_indexed")
        base_path = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base_path / "templates")
        self.questions_path = base_path / "static" / "questions"
        self.logger = AppLogger.get_logger("NewsIndexedController")

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("management_news_indexed.html", {"request": request})

        @self.router.post("/analyze")
        async def analyze(symbol: str = Form(...)):
            # Load question template
            question_file = self.questions_path / "news_summary_indexed.txt"
            with open(question_file, "r", encoding="utf-8") as f:
                template_text = f.read()

            prompt = template_text.format(symbol=symbol.strip().upper())

            print(f"Invoking bot {settings.news_indexed_url} w/ message: {prompt}")
            uri = settings.news_indexed_url
            async with websockets.connect(uri) as ws:
                await ws.send(prompt)
                response = await ws.recv()

            return JSONResponse({"message": "ok", "bot_response": response})
