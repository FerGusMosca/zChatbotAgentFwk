from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import websockets
from common.config.settings import settings
from common.util.app_logger import AppLogger


class ManagementCompetitionController:
    def __init__(self):
        self.router = APIRouter(prefix="/management_competition")
        base_path = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base_path / "templates")
        self.questions_path = base_path / "static" / "questions"
        self.logger = AppLogger.get_logger("ManagementCompetitionController")

        @self.router.get("/", response_class=HTMLResponse)
        async def main_page(request: Request):
            return self.templates.TemplateResponse("management_competition.html", {"request": request})

        @self.router.post("/analyze")
        async def analyze(
            symbol: str = Form(...),
            report: str = Form(...),
            year: int = Form(...),
            quarter: str = Form(None)
        ):
            # 📄 Choose correct template file
            if report == "Q10" and quarter:
                question_file = self.questions_path / "management_competition_question_Q10.txt"
            else:
                question_file = self.questions_path / "management_competition_question_K10.txt"

            with open(question_file, "r", encoding="utf-8") as f:
                template_text = f.read()

            # 🔄 Replace placeholders
            prompt = template_text.format(
                symbol=symbol,
                report=report,
                year=year,
                quarter=quarter or ""
            )

            print(f"Invoking bot {settings.management_competition_url} w/ message: {prompt}")
            uri = settings.management_competition_url
            async with websockets.connect(uri) as ws:
                await ws.send(prompt)
                response = await ws.recv()
            return JSONResponse({"message": "ok", "bot_response": response})
