# deep_company_analysis_controller.py
import asyncio
import json
import os.path
import time
from typing import Optional

import websockets
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

    SINGLE_SEC_TOPIC_REP = "document_tagging_single_security"

    DEF_TAG_MODEL="sentence-transformers/all-mpnet-base-v2"

    REF_DOC_TYPE_10_K= "K_Q_10"


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
                            msg = await ws.recv()

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
                            #yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                            continue

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

        def _normalize_topics(tag_name: str, topic_list: str) -> dict[str, list[str]]:
            cleaned = [
                line.replace('\\"', '')
                .replace('"', '')
                .replace("'", '')
                .rstrip(',')
                .strip()
                for line in topic_list.splitlines()
                if line.strip()
            ]

            return {tag_name: cleaned}

        @self.router.post("/analyze_topics")
        async def analyze_topics(
                symbol: str = Form(...),
                doc_type: str = Form(...),
                year: str = Form(...),
                tag_name: str = Form(...),
                topic_list: str = Form(...),
                quarter: str = Form(None),
                free_text: str = Form(None)
        ):
            """
            Extract and analyze topics from document via MCP service
            Streams progress messages in real-time using Server-Sent Events
            """
            import websockets
            from fastapi.responses import StreamingResponse
            import asyncio

            async def event_generator():
                try:
                    # Validate and parse inputs
                    symbol_upper = symbol.upper().strip()
                    year_str = year.strip()
                    tag_name_clean = tag_name.strip()
                    tag_json_clean = json.dumps(_normalize_topics(tag_name_clean, topic_list))

                    # Send initial progress
                    yield f"data: {json.dumps({'type': 'progress', 'message': f'🔍 Validating symbol {symbol_upper}...'})}\n\n"

                    # Validate symbol exists
                    results = self.sec_mgr.search(symbol_upper)
                    if not results:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Symbol {symbol_upper} not found in database'})}\n\n"
                        return

                    # Find exact match
                    security = next((x for x in results if x.symbol.upper() == symbol_upper), results[0])
                    portfolio = DeepCompanyAnalysisController.DEFAULT_REMOTE_PORTF

                    yield f"data: {json.dumps({'type': 'progress', 'message': f'✅ Symbol validated: {security.symbol}'})}\n\n"

                    # Determine report name and source based on doc_type
                    if doc_type == DeepCompanyAnalysisController.DOC_TYPE_10K:
                        report_name =DeepCompanyAnalysisController.SINGLE_SEC_TOPIC_REP
                        source = f"{portfolio}/K10"
                        proc_doc_type = DeepCompanyAnalysisController.REF_DOC_TYPE_10_K
                    elif doc_type == DeepCompanyAnalysisController.DOC_TYPE_10Q:
                        report_name = DeepCompanyAnalysisController.SINGLE_SEC_TOPIC_REP
                        source = f"{portfolio}/Q10"
                        proc_doc_type = DeepCompanyAnalysisController.REF_DOC_TYPE_10_K
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': f'Invalid doc_type: {doc_type}'})}\n\n"
                        return

                    yield f"data: {json.dumps({'type': 'progress', 'message': f'📊 Preparing analysis for {source}...'})}\n\n"

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
                                "tag_model": DeepCompanyAnalysisController.DEF_TAG_MODEL,
                                "doc_type": proc_doc_type,
                                "source": source,
                                "year": year_str,
                                "tag_json": tag_json_clean,
                                "tag_dedup": False
                            }
                        }
                    }

                    # Add quarter if it's a 10Q
                    if doc_type == DeepCompanyAnalysisController.DOC_TYPE_10Q and quarter:
                        quarter_num = quarter.replace('Q', '').strip()
                        payload["params"]["arguments"]["quarter"] = quarter_num

                    yield f"data: {json.dumps({'type': 'progress', 'message': '🚀 Connecting to MCP service...'})}\n\n"

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

                        yield f"data: {json.dumps({'type': 'progress', 'message': '✅ Connected to MCP service'})}\n\n"

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

                                yield f"data: {json.dumps({'type': 'progress', 'message': f'📝 Job started: {job_id}'})}\n\n"

                        # Stream ALL progress messages in real-time
                        final_result = None

                        last_keepalive = time.time()

                        while True:
                            if time.time() - last_keepalive > 30:
                                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                                last_keepalive = time.time()

                            try:
                                msg = await ws.recv()

                                msg_data = json.loads(msg)

                                # Check if it's a progress message
                                if msg_data.get("method") == "job/progress":
                                    message = msg_data.get("params", {}).get("message", "")

                                    # Send progress message to frontend immediately
                                    yield f"data: {json.dumps({'type': 'progress', 'message': message})}\n\n"

                                    # Try to parse as JSON (completion event)
                                    try:
                                        event_data = json.loads(message)
                                        print(f"[MCP EVENT] {event_data.get('event')} - has result: {bool(event_data.get('result'))}")

                                        if event_data.get("event") == "completed":
                                            final_result = event_data.get("result")
                                            break
                                    except:
                                        # Not a JSON message, just a progress update
                                        pass
                            except asyncio.TimeoutError:
                                yield f"data: {json.dumps({'type': 'keepalive'})}\n\n"
                                continue

                    # Send final result
                    if final_result:
                        yield f"data: {json.dumps({'type': 'result', 'data': final_result})}\n\n"
                    else:
                        yield f"data: {json.dumps({'type': 'error', 'message': 'Analysis completed but no final result received', 'job_id': job_id})}\n\n"

                except ValueError as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
                except Exception as e:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'MCP invocation failed: {str(e)}'})}\n\n"

            return StreamingResponse(
                event_generator(),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"  # Disable nginx buffering
                }
            )

        @self.router.post("/free_analysis")
        async def free_analysis(
                symbol: str = Form(...),
                free_text: str = Form(...),
                prompt: str = Form(...)
        ):
            try:
                payload = {
                    "query": free_text,
                    "prompt": prompt
                }

                payload_str = json.dumps(payload)
                uri = settings.standard_llm_query_bot

                print(f"[free_analysis] Invoking LLM bot at {uri}")

                # TIMEOUT FIX - Disable pings, increase timeout
                async with websockets.connect(
                        uri,
                        ping_interval=None,  # Disable keepalive pings
                        close_timeout=600  # 10 minutes timeout
                ) as ws:
                    await ws.send(payload_str)

                    # Wait with long timeout
                    response = await asyncio.wait_for(
                        ws.recv(),
                        timeout=600  # 10 minutes
                    )

                return JSONResponse({
                    "status": "completed",
                    "symbol": symbol.upper(),
                    "analysis": {
                        "response": response
                    }
                })

            except asyncio.TimeoutError:
                return JSONResponse(
                    {
                        "status": "error",
                        "message": "LLM response took too long (>10 minutes)"
                    },
                    status_code=504
                )
            except Exception as e:
                return JSONResponse(
                    {
                        "status": "error",
                        "message": str(e)
                    },
                    status_code=500
                )
