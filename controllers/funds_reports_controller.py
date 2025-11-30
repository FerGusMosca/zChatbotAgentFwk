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

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("funds_reports.html", {"request": request})

        @self.router.post("/analyze")
        async def analyze(query: str = Form(...)):
            if not query.strip():
                return JSONResponse({"message": "error", "bot_response": "Query cannot be empty."})

            prompt = query.strip()
            log = self.logger

            log.info("==========================================")
            log.info("[FundsReports] New incoming request")
            log.info(f"[FundsReports] Query: {prompt}")
            log.info("==========================================")

            uri = settings.funds_reports_url
            log.info(f"[FundsReports] Target WebSocket URL: {uri}")

            try:
                log.info("[FundsReports] Attempting WebSocket connection...")

                async with websockets.connect(
                        uri,
                        ping_interval=20,
                        ping_timeout=20,
                        close_timeout=5,
                        max_size=10_000_000
                ) as ws:

                    log.info("[FundsReports] WebSocket connected successfully.")
                    log.info("[FundsReports] Sending prompt to bot...")
                    await ws.send(prompt)

                    log.info("[FundsReports] Waiting for bot response...")
                    response = await ws.recv()

                    log.info("[FundsReports] Bot response received.")
                    log.info("[FundsReports] DONE")
                    return JSONResponse({"message": "ok", "bot_response": response})

            except Exception as e:
                log.error("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
                log.error("[FundsReports] ERROR during WebSocket communication")
                log.error(f"[FundsReports] Exception type: {type(e).__name__}")
                log.error(f"[FundsReports] Exception details: {e}")
                log.error("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

                return JSONResponse({
                    "message": "error",
                    "bot_response": f"Error connecting to bot: {e}"
                })
