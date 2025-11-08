from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import websockets
from common.config.settings import settings
from common.util.app_logger import AppLogger


class ManagementSentimentController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_sentiment")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("management_sentiment.html", {"request": request})


        @self.router.post("/analyze")
        async def analyze(
                symbol: str = Form(...),
                report: str = Form(...),
                year: int = Form(...),
                quarter: str = Form(None)
        ):
            if report == "Q10" and quarter:
                prompt = f"Analizá el {quarter} {year} del {report} de {symbol}"
            else:
                prompt = f"Analizá el informe anual {year} del {report} de {symbol}"
            print(f"Invoking bot {settings.management_sentiment_url} w/ message {prompt}")
            uri = settings.management_sentiment_url
            async with websockets.connect(uri) as ws:
                await ws.send(prompt)
                response = await ws.recv()
            return JSONResponse({"message": "ok", "bot_response": response})

        self.logger = AppLogger.get_logger("ManagementSentimentController")