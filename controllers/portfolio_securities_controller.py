from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from pathlib import Path

from starlette.responses import StreamingResponse
from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.util.app_logger import AppLogger

from data_access_layer.manager_portfolios import PortfolioManager

import csv
import io
from fastapi.responses import StreamingResponse

from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager


class PortfolioSecuritiesController:
    def __init__(self):
        self.router = APIRouter(prefix="/process_news")

        base = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("PortfolioSecuritiesController")

        self.portfolio_mgr = PortfolioManager(settings.research_connection_string)
        self.ps_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            portfolios = self.portfolio_mgr.get_all()
            return self.templates.TemplateResponse(
                "process_news.html",
                {"request": request, "portfolios": portfolios, "securities": []}
            )

        @self.router.post("/load", response_class=HTMLResponse)
        async def load(
                request: Request,
                portfolio_id: int = Form(...),
                page: int = Form(1),
                page_size: int = Form(20)
        ):
            portfolios = self.portfolio_mgr.get_all()
            page_data = self.ps_mgr.get_paged(portfolio_id, page, page_size)

            return self.templates.TemplateResponse(
                "process_news.html",
                {
                    "request": request,
                    "portfolios": portfolios,
                    "selected_portfolio": portfolio_id,
                    "page_data": page_data
                }
            )

        @self.router.get("/export_csv", response_class=StreamingResponse)
        async def export_csv(portfolio_id: int):
            items = self.ps_mgr.get_full(portfolio_id)

            output = io.StringIO()
            writer = csv.writer(output)

            writer.writerow(["ID", "Ticker", "Name", "CIK", "Added", "Active", "Weight"])

            for s in items:
                writer.writerow([
                    s.id,
                    s.ticker,
                    s.name,
                    s.cik,
                    s.added_at,
                    s.is_active,
                    s.weight
                ])

            output.seek(0)

            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename=portfolio_{portfolio_id}.csv"
                }
            )

        @self.router.get("/search")
        async def search(query: str):
            if not query or len(query.strip()) < 2:
                return []

            items = self.ps_mgr.search(query)
            return [
                {
                    "security_id": x.id,
                    "ticker": x.ticker,
                    "name": x.name,
                    "cik": x.cik
                }
                for x in items
            ]

        @self.router.post("/add_single")
        async def add_single(portfolio_id: int = Form(...), security_id: int = Form(...)):
            try:
                self.ps_mgr.add_single(portfolio_id, security_id)
                return {"status": "ok"}
            except Exception as ex:
                return {"status": "error", "message": str(ex)}

        @self.router.post("/import_csv")
        async def import_csv(
                portfolio_id: int = Form(...),
                csv_text: str = Form(...)
        ):
            try:
                result = self.ps_mgr.import_csv(portfolio_id, csv_text)
                return {"status": "ok", "report": result}
            except Exception as ex:
                return {"status": "error", "message": str(ex)}



