from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import httpx
from common.config.settings import settings
import websockets
class ManagementSentimentController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_sentiment")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)
        self.router.get("/", response_class=HTMLResponse)(self.main_page)
        self.router.post("/analyze")(self.analyze)

    async def main_page(self, request: Request):
        return self.templates.TemplateResponse("management_sentiment.html", {"request": request})

    async def analyze(self, symbol: str = Form(...), report: str = Form(...), year: int = Form(...)):
        prompt = f"Analizá el Q3 {year} del {report} de {symbol}"
        uri = settings.management_sentiment_url
        async with websockets.connect(uri) as ws:
            await ws.send(prompt)
            response = await ws.recv()
        return JSONResponse({"message": "ok", "bot_response": response})
