from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from pathlib import Path

from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.util.app_logger import AppLogger

from data_access_layer.manager_portfolios import PortfolioManager
from data_access_layer.manager_portfolio_securities import PortfolioSecuritiesManager


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
                "portfolio_securities.html",
                {
                    "request": request,
                    "portfolios": portfolios,
                    "selected_portfolio": portfolio_id,
                    "page_data": page_data
                }
            )
