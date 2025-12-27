from fastapi import APIRouter, Request, Form, Body, Query
from fastapi.responses import HTMLResponse
from pathlib import Path

from starlette.responses import StreamingResponse
from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.dto.update_security_request import UpdateSecurityRequest
from common.util.app_logger import AppLogger

from data_access_layer.manager_portfolios import PortfolioManager

import csv
import io
from fastapi.responses import StreamingResponse

from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager




class PortfolioSecuritiesController:
    def __init__(self):
        self.router = APIRouter(prefix="/portfolio_securities")

        base = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("PortfolioSecuritiesController")

        self.portfolio_mgr = PortfolioManager(settings.research_connection_string)
        self.ps_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            portfolios = self.portfolio_mgr.get_all()
            return self.templates.TemplateResponse(
                "portfolio_securities.html",
                {"request": request, "portfolios": portfolios, "securities": []}
            )

        from fastapi import Query

        @self.router.get("/load", response_class=HTMLResponse)
        async def load_get(
                request: Request,
                portfolio_id: int = Query(...),
                page: int = Query(1),
                page_size: int = Query(20),
                ticker_filter: str | None = Query(None),
                symbol_filter: str | None = Query(None),
        ):
            portfolios = self.portfolio_mgr.get_all()
            page_data = self.ps_mgr.get_paged(
                portfolio_id=portfolio_id,
                page=page,
                page_size=page_size,
                ticker_filter=ticker_filter,
                symbol_filter=symbol_filter,
            )

            return self.templates.TemplateResponse(
                "portfolio_securities.html",
                {
                    "request": request,
                    "portfolios": portfolios,
                    "selected_portfolio": portfolio_id,
                    "page_data": page_data,
                    "ticker_filter": ticker_filter,
                    "symbol_filter": symbol_filter,
                },
            )

        @self.router.post("/load", response_class=HTMLResponse)
        async def load_post(
                request: Request,
                portfolio_id: int = Form(...),
                page: int = Form(1),
                page_size: int = Form(20),
                ticker_filter: str | None = Form(None),
                symbol_filter: str | None = Form(None),
        ):
            portfolios = self.portfolio_mgr.get_all()
            page_data = self.ps_mgr.get_paged(
                portfolio_id=portfolio_id,
                page=page,
                page_size=page_size,
                ticker_filter=ticker_filter,
                symbol_filter=symbol_filter,
            )

            return self.templates.TemplateResponse(
                "portfolio_securities.html",
                {
                    "request": request,
                    "portfolios": portfolios,
                    "selected_portfolio": portfolio_id,
                    "page_data": page_data,
                    "ticker_filter": ticker_filter,
                    "symbol_filter": symbol_filter,
                },
            )

        @self.router.post("/update")
        async def update_security(
                security_id: int = Form(...),
                symbol: str | None = Form(None),
                name: str | None = Form(None)
        ):
            try:
                result = self.ps_mgr.update(security_id, symbol, name)
                return result
            except Exception as ex:
                self.logger.error(f"Update failed for security_id {security_id}: {ex}")
                return {"status": "error", "message": str(ex)}

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
                    s.symbol,
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



