import asyncio
import datetime
import json
import os
import shlex
import uuid

from fastapi import APIRouter, Request, Form
import websockets
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path
import subprocess

from pydantic import BaseModel
from starlette.responses import StreamingResponse
from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.util.app_logger import AppLogger
from common.util.std_in_out.root_locator import RootLocator
from common.util.ui.process_stream_runner import ProcessStreamRunner
from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager
from common.dto.ingest_state import ingest_state
from service_client.mcp_client.download_news_mcp_client import DownloadNewsMCPClient
from service_client.mcp_client.rag_ingest_mcp_client import RAGIngestMCPClient


class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str


BOT_NEWS_QUERY_PATH = Path(__file__).parent.parent / "static" / "bot_querys" / "bot_11_query"
class ProcessNewsController:

    def _resolve_news_root_folder(
            self,
            full_path: str,
            news_folder_rel_path: str
    ) -> str:
        """
        Returns the relative path starting at news_folder_rel_path.
        If full_path is a file, strips the filename.
        If full_path is a directory, keeps it intact.
        """
        p = Path(full_path)

        parts = p.parts
        if news_folder_rel_path not in parts:
            raise ValueError(f"{news_folder_rel_path} not found in path")

        idx = parts.index(news_folder_rel_path)

        # If path has a suffix, it's a file → drop filename
        end = -1 if p.suffix else len(parts)

        relative_parts = parts[idx:end]

        return str(Path(*relative_parts).as_posix())

    def __init__(self):
        self.router = APIRouter(prefix="/process_news")

        # Store last generated report in memory
        self.last_news_output_file = None

        base = RootLocator.get_root()
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("ProcessNewsController")

        self.sec_mgr = PortfolioSecuritiesManager(settings.research_connection_string)


        @self.router.get("/", response_class=HTMLResponse)
        async def main(request: Request):

            request.session.clear()
            request.session["sid"] = str(uuid.uuid4())
            ingest_state.register_callback(request.session["sid"], on_news_ingested)

            return self.templates.TemplateResponse(
                "process_news.html",
                {"request": request}
            )

        @self.router.get("/search")
        async def search(query: str):
            if not query or len(query.strip()) < 2:
                return []
            items = self.sec_mgr.search(query)
            return [
                {
                    "security_id": x.id,
                    "symbol": x.symbol,
                    "name": x.name
                }
                for x in items
            ]



        @self.router.post("/download_news")
        async def download_news(symbol: str = Form(...)):
            """
            Endpoint to trigger news download via MCP client.
            Streams messages in real-time, saves final path or error in controller.
            """
            client = DownloadNewsMCPClient(
                symbol=symbol,
                portfolio="SINGLE_STOCKS",
                uri=settings.reports_mcp_server
            )

            async def wrapped_generator():
                # Stream all messages from the client in real-time
                async for msg in client.execute_and_stream():


                    # After stream completes, check result
                    if client.last_output_file:
                        self.last_news_output_file = client.last_output_file
                        yield msg
                        yield f"[CONTROLLER] Success - Final path saved: {self.last_news_output_file}\n\n"
                        return
                    elif client.download_error:
                        error_msg = client.last_error or "Unknown download error"
                        self.last_error = error_msg  # Optional: store in controller too
                        yield msg
                        yield f"[CONTROLLER] ERROR: {error_msg}\n\n"
                        # No need to "cut repetition" → async for already finishes the loop
                    else:
                        yield msg


            return StreamingResponse(
                wrapped_generator(),
                media_type="text/event-stream"
            )
        @self.router.get("/download_last")
        async def download_last():
            # comment: send last generated report if available
            if not self.last_news_output_file or not os.path.exists(self.last_news_output_file):
                return PlainTextResponse("No report available.", status_code=404)

            f = open(self.last_news_output_file, "rb")
            filename = os.path.basename(self.last_news_output_file)
            return StreamingResponse(
                f,
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}"
                }
            )

        @self.router.get("/download_prompt")
        async def download_prompt():
            # comment: absolute path to prompt file
            prompt_path = Path(__file__).parent.parent / "prompts" / "news_prompt.txt"

            if not prompt_path.exists():
                return PlainTextResponse("Prompt file not found.", status_code=404)

            f = open(prompt_path, "rb")
            return StreamingResponse(
                f,
                media_type="text/plain",
                headers={
                    "Content-Disposition": "attachment; filename=news_prompt.txt"
                }
            )

        async def query_bot11( query: str, chunks_path: str) -> str:
            """Queries news bot via WebSocket. Returns response or error string."""
            try:
                template_path = BOT_NEWS_QUERY_PATH
                prompt = template_path.read_text().lstrip().format(
                    query=query,
                    folder=chunks_path.rstrip("/")
                )

                self.logger.info(f"[News Bot] Querying {query} – folder: {chunks_path}")

                async with websockets.connect(settings.news_reports_url, ping_interval=None,open_timeout=60) as ws:
                    await ws.send(prompt)
                    response = await asyncio.wait_for(ws.recv(), timeout=180)

                self.logger.info("[News Bot] Response received")
                return response

            except Exception as e:
                self.logger.exception(f"[News Bot] Error querying bot11: {e}")
                return f"Error querying News Bot: {str(e)}"

        async def on_news_ingested( query: str, path: str) -> str:
            try:
                self.logger.info(f"[NEWS INGESTED] symbol={query} path={path}")

                response = await query_bot11(query, path)
                return response

            except Exception as e:
                self.logger.exception(f"[ON_NEWS_INGESTED] Error: {e}")
                return f"Ingestion OK but News Bot failed: {str(e)}"

        @self.router.post("/ingest_news")
        async def ingest_news(request: Request, symbol: str = Form(...)):
            """
            Endpoint to trigger RAG ingest via MCP client.
            Requires last_output_file from previous download.
            """

            if not self.last_news_output_file:
                return PlainTextResponse("❌ No downloaded news found. Run news download first.", status_code=400)

            downloaded_path = os.path.dirname(self.last_news_output_file)
            news_path = self._resolve_news_root_folder(downloaded_path, settings.news_folder_rel_path)

            client = RAGIngestMCPClient(
                mode="incremental",
                source=downloaded_path,
                dest_root=settings.news_vendor,
                chunk_name=settings.news_chunks_rel_path,
                embedding_model=settings.news_embedding_model,
                clustering_model=settings.news_embedding_model,
                log_posfix=symbol,
                uri=settings.ingest_mcp_server
            )

            async def wrapped_generator():
                async for msg in client.execute_and_stream():
                    yield msg

                    if client.last_output_folder:
                        self.last_ingest_folder = client.last_output_folder
                        session_id = request.session.get("sid")
                        ingest_state.ready_by_session[session_id] = True
                        ingest_state.context_by_session[session_id] = self.last_ingest_folder
                        yield f"[CONTROLLER] Success - Ingest folder: {self.last_ingest_folder}\n\n"
                        return
                    elif client.ingest_error:
                        error_msg = client.last_error or "Unknown ingest error"
                        self.last_error = error_msg
                        yield f"[CONTROLLER] ERROR: {error_msg}\n\n"

            return StreamingResponse(wrapped_generator(), media_type="text/event-stream")



