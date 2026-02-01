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
    DEFAULT_REMOTE_PORTF="US_BIGCAP_EX"
    DOC_TYPE_10K="10K"
    DOC_TYPE_10Q="10Q"

    SINGLE_SEC_SENTIMENT_10K_REP="sentiment_summary_single_security_report_k10"
    SINGLE_SEC_SENTIMENT_10Q_REP = "sentiment_summary_single_security_report_q10"

    def __init__(self):
        self.router = APIRouter(prefix="/deep_company_analysis")

        templates_path = os.path.join(RootLocator.get_root(), "templates")
        self.templates = Jinja2Templates(directory=templates_path)

        # Initialize PortfolioSecuritiesManager for symbol validation
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
            Validate if symbol exists in backend by searching in PortfolioSecuritiesManager
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
            Analyze sentiment of document by invoking MCP service
            """
            try:
                import websockets

                # Validate and parse inputs
                symbol_upper = symbol.upper().strip()
                year_str = year.strip()

                # Validate symbol exists
                results = self.sec_mgr.search(symbol_upper)
                if not results:
                    return JSONResponse({
                        "status": "error",
                        "message": f"Symbol {symbol_upper} not found in database"
                    }, status_code=404)

                # Find exact match
                security = next((x for x in results if x.symbol.upper() == symbol_upper), results[0])
                portfolio = DeepCompanyAnalysisController.DEFAULT_REMOTE_PORTF

                # Determine report name based on doc_type
                if doc_type == DeepCompanyAnalysisController.DOC_TYPE_10K:
                    report_name = DeepCompanyAnalysisController.SINGLE_SEC_SENTIMENT_10K_REP
                elif doc_type == DeepCompanyAnalysisController.DOC_TYPE_10Q:
                    report_name = DeepCompanyAnalysisController.SINGLE_SEC_SENTIMENT_10Q_REP
                else:
                    raise ValueError(f"Invalid doc_type: {doc_type}. Must be '10K' or '10Q'")

                # Build MCP payload
                payload = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "run_report",
                        "arguments": {
                            "report": report_name,
                            "symbol": symbol_upper,
                            "portfolio": portfolio,
                            "year": year_str
                        }
                    }
                }

                # Add quarter if it's a 10Q
                if doc_type == DeepCompanyAnalysisController.DOC_TYPE_10Q and quarter:
                    # Extract quarter number (Q1 -> 1)
                    quarter_num = quarter.replace('Q', '').strip()
                    payload["params"]["arguments"]["quarter"] = quarter_num

                # Invoke MCP
                async with websockets.connect(settings.reports_mcp_server) as ws:
                    # First, list tools (handshake)
                    await ws.send(json.dumps({
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {}
                    }))
                    await asyncio.sleep(0.2)

                    # Then, call the report
                    await ws.send(json.dumps(payload))

                    # Wait for initial response (job accepted)
                    response = await ws.recv()
                    initial_result = json.loads(response)

                    # Extract job_id
                    job_id = None
                    if "result" in initial_result and "content" in initial_result["result"]:
                        content = initial_result["result"]["content"][0]
                        if content.get("type") == "text":
                            job_data = json.loads(content["text"])
                            job_id = job_data.get("job_id")

                    # Collect progress messages until completion
                    final_result = None
                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=120.0)
                            msg_data = json.loads(msg)

                            # Check if it's a progress message with completion event
                            if msg_data.get("method") == "job/progress":
                                message = msg_data.get("params", {}).get("message", "")

                                # Try to parse as JSON (completion event)
                                try:
                                    event_data = json.loads(message)
                                    if event_data.get("event") == "completed":
                                        final_result = event_data.get("result")
                                        break
                                except:
                                    # Not a JSON message, continue
                                    pass
                        except asyncio.TimeoutError:
                            break

                # Return the final result
                if final_result:
                    return JSONResponse(final_result)
                else:
                    return JSONResponse({
                        "status": "error",
                        "message": "Analysis completed but no final result received",
                        "job_id": job_id
                    })

            except ValueError as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=400
                )
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": f"MCP invocation failed: {str(e)}"},
                    status_code=500
                )

        @self.router.post("/analyze_topics")
        async def analyze_topics(
                symbol: str = Form(...),
                doc_type: str = Form(...),
                year: str = Form(...),
                topics: str = Form(...),
                quarter: str = Form(None),
                free_text: str = Form(None)
        ):
            """
            Extract and analyze topics from document
            TODO: Implement actual topic extraction
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
                            "key_phrases": ["machine learning deployment", "AI-driven productivity"]
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
            TODO: Implement actual LLM call
            """
            try:
                # Placeholder response
                result = {
                    "status": "ok",
                    "symbol": symbol.upper(),
                    "prompt": prompt,
                    "analysis": {
                        "response": "Placeholder analysis response",
                        "extracted_concepts": ["Concept 1", "Concept 2"]
                    },
                    "message": "Free analysis completed (placeholder)"
                }
                return JSONResponse(result)
            except Exception as e:
                return JSONResponse(
                    {"status": "error", "message": str(e)},
                    status_code=400
                )