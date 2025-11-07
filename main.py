from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn

from common.config.settings import get_settings
from controllers.management_sentiment_controller import ManagementSentimentController

settings = get_settings()
app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.TemplateResponse("main_dashboard.html", {"request": request})

# ✅ Management Sentiment
management_sentiment = ManagementSentimentController()
app.include_router(management_sentiment.router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(settings.port))
