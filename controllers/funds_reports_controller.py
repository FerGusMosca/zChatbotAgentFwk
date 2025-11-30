# controllers/funds_reports_controller.py

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import websockets
from common.config.settings import settings
from common.util.app_logger import AppLogger


class FundsReportsController:
    def __init__(self):
        self.router = APIRouter(prefix="/funds_reports")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)
        self.logger = AppLogger.get_logger("FundsReportsController")

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("funds_reports.html", {"request": request})

        @self.router.post("/analyze")
        async def analyze(query: str = Form(...)):
            if not query.strip():
                self.logger.error("Empty query received")
                return JSONResponse({"message": "error", "bot_response": "La consulta no puede estar vacía."})

            prompt = query.strip()
            uri = settings.funds_reports_url

            self.logger.info(f"[FundsReports] Connecting to bot at {uri}")
            self.logger.info(f"[FundsReports] Prompt: {prompt}")

            try:
                async with websockets.connect(uri) as ws:
                    self.logger.info("[FundsReports] WebSocket connection established")

                    await ws.send(prompt)
                    self.logger.info("[FundsReports] Prompt sent — waiting for reply...")

                    response = await ws.recv()
                    self.logger.info("[FundsReports] Response received")

                return JSONResponse({"message": "ok", "bot_response": response})

            except Exception as e:
                self.logger.error(f"[FundsReports] ERROR: {e}")
                return JSONResponse({"message": "error", "bot_response": f"Error conectando al bot: {e}"})
