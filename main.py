from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import uvicorn

from common.config.settings import get_settings

# Controllers ya existentes
from controllers.calendar_controller import CalendarController
from controllers.management_competition_controller import ManagementCompetitionController
from controllers.management_news_indexed_controller import NewsIndexedController
from controllers.management_sentiment_controller import ManagementSentimentController
from controllers.management_sentiment_rankings_controller import ManagementSentimentRankingsController
from controllers.management_sentiment_rankings_fallback_controller import ManagementSentimentRankingsFallbackController

# 🔥 NUEVO CONTROLLER
from controllers.portfolio_securities_controller import PortfolioSecuritiesController
from controllers.process_news_controller import ProcessNewsController

settings = get_settings()
app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Static folder
app.mount("/static", StaticFiles(directory="static"), name="static")


# ===========================
#       MAIN DASHBOARD
# ===========================
@app.get("/", response_class=HTMLResponse)
async def main_page(request: Request):
    return templates.TemplateResponse("main_dashboard.html", {"request": request})


# ===========================
#       CONTROLLERS
# ===========================

# Management Sentiment
management_sentiment = ManagementSentimentController()
app.include_router(management_sentiment.router)

# Competition Analysis
management_competition = ManagementCompetitionController()
app.include_router(management_competition.router)

# News Indexed
mgmt_sentiment_ranking = NewsIndexedController()
app.include_router(mgmt_sentiment_ranking.router)

# Sentiment Rankings (RAG)
mgmt_sentiment_ranking = ManagementSentimentRankingsController()
app.include_router(mgmt_sentiment_ranking.router)

# Sentiment Rankings Fallback
mgmt_sentiment_ranking_fallback = ManagementSentimentRankingsFallbackController()
app.include_router(mgmt_sentiment_ranking_fallback.router)

# Calendar Viewer
calendar = CalendarController()
app.include_router(calendar.router)

# Portfolio Securities
process_news = PortfolioSecuritiesController()
app.include_router(process_news.router)

# Process News
process_news = ProcessNewsController()
app.include_router(process_news.router)


# ===========================
#           RUN
# ===========================
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(settings.port))
