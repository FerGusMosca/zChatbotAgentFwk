from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from common.util.app_logger import AppLogger
from common.config.settings import get_settings
from data_access_layer.security_calendar_manager import SecurityCalendarManager


class CalendarController:
    def __init__(self):
        self.router = APIRouter(prefix="/calendar")
        base_path = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base_path / "templates")
        self.logger = AppLogger.get_logger("CalendarController")
        self.manager = SecurityCalendarManager(get_settings().research_connection_string)

        @self.router.get("/view", response_class=HTMLResponse)
        async def view_calendar(request: Request, symbol: str, year: int):
            result = self.manager.get(symbol, year)
            calendar = result[0] if result else None

            return self.templates.TemplateResponse(
                "calendar_view.html",
                {
                    "request": request,
                    "symbol": symbol,
                    "year": year,
                    "calendar": calendar
                }
            )
