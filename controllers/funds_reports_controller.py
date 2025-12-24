# controllers/funds_reports_controller.py
import json

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
        self.zh_processed_folders_file=settings.zh_processed_folders_file
        self.templates = Jinja2Templates(directory=templates_path)
        self.logger = AppLogger.get_logger("FundsReportsController")

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            folders = self._load_successful_folders()
            return self.templates.TemplateResponse(
                "funds_reports.html",
                {
                    "request": request,
                    "processed_folders": folders
                }
            )

        @self.router.post("/analyze")
        async def analyze(
                query: str = Form(...),
                processed_folder: str = Form(None)
        ):
            if not query.strip():
                self.logger.error("Empty query received")
                return JSONResponse({
                    "message": "error",
                    "bot_response": "La consulta no puede estar vacía."
                })

            prompt = query.strip()
            folder = processed_folder.strip() if processed_folder else "LAST_INGESTION"

            uri = settings.funds_reports_url

            self.logger.info(f"[FundsReports] Connecting to bot at {uri}")
            self.logger.info(f"[FundsReports] Prompt: {prompt}")
            self.logger.info(f"[FundsReports] Selected folder: {folder}")

            try:
                async with websockets.connect(
                        uri,
                        ping_interval=None,
                        close_timeout=300,
                        ping_timeout=300
                ) as ws:

                    if(folder!=""):
                        self.logger.info(f"[FundsReports] Sending query {query[0:10]} to {folder} ...")
                        await ws.send(json.dumps({
                            "query": query,
                            "chunks_folder": folder
                        }))
                    else:
                        self.logger.info(f"[FundsReports] Sending query {query[0:10]} to default folder ...")
                        await ws.send(json.dumps(query))

                    self.logger.info("[FundsReports] Payload sent — waiting for reply...")

                    response = await ws.recv()
                    self.logger.info("[FundsReports] Response received")

                return JSONResponse({
                    "message": "ok",
                    "bot_response": response
                })

            except Exception as e:
                self.logger.error(f"[FundsReports] ERROR: {e}")
                return JSONResponse({
                    "message": "error",
                    "bot_response": f"Error conectando al bot: {e}"
                })

        # ============================
        # Internal helpers
        # ============================
    def _load_successful_folders(self):
        try:
            with open(self.zh_processed_folders_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            history = data.get("processed_history", [])
            folders = [
                item["dest_folder"]
                for item in history
                if item.get("status") == "success" and item.get("dest_folder")
            ]

            # Remove duplicates, preserve order
            seen = set()
            unique_folders = []
            for f in folders:
                if f not in seen:
                    seen.add(f)
                    unique_folders.append(f)

            return unique_folders

        except Exception as e:
            self.logger.error(f"[FundsReports] Failed loading processed folders: {e}")
            return []
