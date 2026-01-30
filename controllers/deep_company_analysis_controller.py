# deep_company_analysis_controller.py
import asyncio
import json
import os.path
from typing import Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from common.config.settings import settings
from common.util.std_in_out.root_locator import RootLocator
from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager


class DeepCompanyAnalysisController:
    """
    Controller for Deep Company Analysis
    Simple form-based analysis of company documents and free text
    """

    def __init__(self):
        self.router = APIRouter(prefix="/deep_company_analysis")

        templates_path = os.path.join(RootLocator.get_root(), "templates")
        self.templates = Jinja2Templates(directory=templates_path)

        # Initialize SecurityManager for symbol validation
        self.sec_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def deep_company_analysis_page(request: Request):
            """Main page for deep company analysis"""
            return self.templates.TemplateResponse(
                "deep_company_analysis.html",
                {"request": request}
            )

        @self.router.post("/validate_symbol")
        async def validate_symbol(symbol: str = Form(...)):
            """
            Validate if symbol exists in backend by searching in SecurityManager
            """
            try:
                symbol_upper = symbol.upper().strip()

                # Search for the security
                results = self.sec_mgr.search(symbol_upper)

                if not results:
                    return JSONResponse({
                        "status": "error",
                        "valid": False,
                        "symbol": symbol_upper,
                        "message": f"Symbol {symbol_upper} not found in database"
                    })

                # Find exact match (prioritize exact symbol match)
                exact_match = next((x for x in results if x.symbol.upper() == symbol_upper), None)

                if exact_match:
                    return JSONResponse({
                        "status": "ok",
                        "valid": True,
                        "symbol": exact_match.symbol,
                        "security_id": exact_match.id,
                        "name": exact_match.name,
                        "message": f"Symbol {exact_match.symbol} found: {exact_match.name}"
                    })

                # If no exact match but results exist, return first result
                first_result = results[0]
                return JSONResponse({
                    "status": "ok",
                    "valid": True,
                    "symbol": first_result.symbol,
                    "security_id": first_result.id,
                    "name": first_result.name,
                    "message": f"Symbol {first_result.symbol} found: {first_result.name}"
                })

            except Exception as e:
                return JSONResponse(
                    {"status": "error", "valid": False, "message": str(e)},
                    status_code=400
                )

        @self.router.post("/analyze_sentiment")
        async def analyze_sentiment(
                symbol: str = Form(...),
                doc_type: str = Form(...),
                year: str = Form(...),
                quarter: str = Form(None),
                free_text: str = Form(None)
        ):
            """
            Analyze sentiment of document or free text
            TODO: Implement actual sentiment analysis
            """
            try:
                # Placeholder response
                result = {
                    "status": "ok",
                    "symbol": symbol.upper(),
                    "doc_type": doc_type,
                    "year": year,
                    "quarter": quarter,
                    "analysis": {
                        "overall_tone": 0.72,
                        "confidence_level": 0.85,
                        "defensive_language": 0.15,
                        "forward_looking": 0.68,
                        "key_sentiment_signals": [
                            "Bullish on AI initiatives",
                            "Cautious on macro environment",
                            "Confident in margin expansion"
                        ]
                    },
                    "message": "Sentiment analysis completed (placeholder)"
                }
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=400
                )

        @self.router.post("/analyze_topics")
        async def analyze_topics(
                symbol: str = Form(...),
                doc_type: str = Form(...),
                year: str = Form(...),
                topics: str = Form(...),  # New: user-provided topics
                quarter: str = Form(None),
                free_text: str = Form(None)
        ):
            """
            Extract and analyze topics from document or free text
            TODO: Implement actual topic extraction using provided topics
            """
            try:
                # Parse topics (one per line)
                topic_list = [t.strip() for t in topics.split('\n') if t.strip()]

                # Placeholder response
                result = {
                    "status": "ok",
                    "symbol": symbol.upper(),
                    "doc_type": doc_type,
                    "year": year,
                    "quarter": quarter,
                    "topics_requested": topic_list,
                    "topics": [
                        {
                            "topic": "AI Integration",
                            "relevance": 0.92,
                            "mentions": 15,
                            "key_phrases": ["machine learning deployment", "AI-driven productivity", "model training"]
                        },
                        {
                            "topic": "Cost Management",
                            "relevance": 0.78,
                            "mentions": 8,
                            "key_phrases": ["operational efficiency", "margin expansion", "cost discipline"]
                        },
                        {
                            "topic": "Market Competition",
                            "relevance": 0.65,
                            "mentions": 6,
                            "key_phrases": ["competitive dynamics", "market share", "differentiation"]
                        }
                    ],
                    "message": f"Topic analysis completed for {len(topic_list)} topics (placeholder)"
                }
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=400
                )

        @self.router.post("/free_analysis")
        async def free_analysis(
                symbol: str = Form(...),
                free_text: str = Form(...),
                prompt: str = Form(...)
        ):
            """
            Custom LLM-based analysis with user-provided prompt
            Only available for FREE_TEXT document type
            TODO: Implement actual LLM call
            """
            try:
                # Placeholder response
                result = {
                    "status": "ok",
                    "symbol": symbol.upper(),
                    "prompt": prompt,
                    "analysis": {
                        "response": "Based on the provided text and your prompt, here are the key concepts:\n\n"
                                    "1. Strategic Initiatives: The company is focusing on AI-driven automation to improve operational efficiency by 15-20%.\n\n"
                                    "2. Market Position: Management emphasized maintaining market leadership through continuous innovation and customer-centric approach.\n\n"
                                    "3. Risk Factors: Key concerns include supply chain volatility and regulatory scrutiny in international markets.\n\n"
                                    "4. Financial Outlook: Guidance suggests 10-12% revenue growth with expanding margins due to operating leverage.",
                        "extracted_concepts": [
                            "AI automation strategy",
                            "15-20% efficiency target",
                            "Market leadership focus",
                            "Supply chain risks",
                            "10-12% revenue growth guidance"
                        ]
                    },
                    "message": "Free analysis completed (placeholder)"
                }
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=400
                )