from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path
import subprocess

from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.util.app_logger import AppLogger
from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager


class ProcessNewsController:

    def __init__(self):
        self.router = APIRouter(prefix="/process_news")

        base = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("ProcessNewsController")

        self.sec_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def main(request: Request):
            return self.templates.TemplateResponse(
                "process_news.html",
                {"request": request}
            )

        @self.router.get("/search")
        async def search(query: str):
            if not query or len(query.strip()) < 2:
                return []
            items = self.sec_mgr.search(query)
            return [
                {
                    "security_id": x.id,
                    "ticker": x.ticker,
                    "name": x.name
                }
                for x in items
            ]

        @self.router.post("/run")
        async def run(security_id: int = Form(...), date: str = Form(...)):

            sec = self.sec_mgr.get(security_id)
            symbol = sec.ticker

            cmd = [
                "docker", "run", "--rm",
                "alienzimzum/zz-run-report:latest",
                "RunReport", "report=process_news",
                f"symbol={symbol}",
                f"date={date}"
            ]

            self.logger.info(f"Running: {' '.join(cmd)}")

            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            output = proc.stdout + "\n\n" + proc.stderr
            return PlainTextResponse(output)
