from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

class ManagementSentimentController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_sentiment")
        templates_path = Path(__file__).parent.parent / "templates"
        self.templates = Jinja2Templates(directory=templates_path)
        self.router.get("/", response_class=HTMLResponse)(self.main_page)

    async def main_page(self, request: Request):
        return self.templates.TemplateResponse("management_sentiment.html", {"request": request})
