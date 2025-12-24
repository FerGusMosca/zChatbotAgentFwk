import asyncio
import datetime
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
from common.util.ui.process_stream_runner import ProcessStreamRunner
from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager
from common.dto.ingest_state import ingest_state

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
        self.last_output_file = None

        base = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("ProcessNewsController")

        self.sec_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        #TO TEST


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
                    "ticker": x.ticker,
                    "name": x.name
                }
                for x in items
            ]

        @self.router.post("/run_stream")
        async def run_stream(symbol: str = Form(...)):
            try:
                # Generate unique identifier based on timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

                # Build full path to commands_mgr.ini using settings (no hardcoding)
                commands_ini = str(Path(settings.commands_ini_path) / "commands_mgr.ini")

                # Documents folder path from settings
                documents_path = settings.documents_path
                news_folder_rel_path=settings.news_folder_rel_path

                # Command template file name from settings
                prcess_news_cmd_file = settings.docker_process_news_cmd

                # Load command template
                template_path = (
                        Path(__file__).parent.parent /
                        "static" / "containers_cmds" / prcess_news_cmd_file
                )
                template_raw = template_path.read_text()

                # Inject variables into template (single-line Windows command)
                cmd_str = template_raw.format(
                    timestamp=timestamp,
                    commands_ini=commands_ini,
                    documents_path=documents_path,
                    news_folder_rel_path=news_folder_rel_path,
                    symbol=symbol
                )

                # Convert command string into argument list
                cmd = shlex.split(cmd_str, posix=False)

            except KeyError as ex:
                return PlainTextResponse(f"❌ Missing template variable: {ex}", status_code=500)
            except Exception as ex:
                return PlainTextResponse(f"❌ Error preparing command: {ex}", status_code=500)

            # Callback executed for each stdout line
            def on_line(line: str):
                # Detect "saved" event and extract output file path
                if '"path":' in line:
                    try:
                        part = line.split('"path":', 1)[1]
                        extracted = part.split('"')[1]  # first quoted string
                        self.last_output_file = extracted
                        self.logger.info(f"[OK] Extracted output file: {self.last_output_file}")
                    except Exception as ex:
                        self.logger.error(
                            f"[FAIL] Could not extract path from line: {line.strip()} | Error: {ex}"
                        )

            # Stream process output to the UI in real time
            return StreamingResponse(
                ProcessStreamRunner.stream_process(
                    cmd=cmd,
                    logger=self.logger,
                    tag="DOWNLOAD",
                    on_line=on_line
                ),
                media_type="text/plain; charset=utf-8"
            )

        @self.router.get("/download_last")
        async def download_last():
            # comment: send last generated report if available
            if not self.last_output_file or not os.path.exists(self.last_output_file):
                return PlainTextResponse("No report available.", status_code=404)

            f = open(self.last_output_file, "rb")
            filename = os.path.basename(self.last_output_file)
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
        async def ingest_news(request: Request,symbol: str = Form(...)):
            try:
                # Safety check: ensure we have a downloaded file from run_stream
                if not self.last_output_file:
                    return PlainTextResponse(
                        "❌ No downloaded news found. Run news download first.",
                        status_code=400
                    )

                # Resolve the folder containing the downloaded JSON
                # Example:
                # /zzLotteryTicket/documents/.../CAMP_xxx/2025-12-16_17-06-03_full_news.json --> we want the parent directory
                downloaded_path = os.path.dirname(self.last_output_file)

                news_path=self._resolve_news_root_folder(downloaded_path,settings.news_folder_rel_path)

                # Generate unique identifier
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

                # Build full path to commands_mgr.ini
                commands_ini = str(Path(settings.commands_ini_path) / "commands_mgr.ini")

                # Documents root path (same as download)
                documents_path = settings.documents_path
                news_chunks_rel_path=settings.news_chunks_rel_path
                news_vendor = settings.news_vendor
                embedding_model = settings.news_embedding_model

                # Command template file from settings
                ingest_cmd_file = settings.docker_ingest_news_cmd

                # Load command template
                template_path = (
                        Path(__file__).parent.parent /
                        "static" / "containers_cmds" / ingest_cmd_file
                )
                template_raw = template_path.read_text()

                # Inject variables into template
                cmd_str = template_raw.format(
                    timestamp=timestamp,
                    commands_ini=commands_ini,
                    documents_path=documents_path,
                    news_path=news_path,
                    news_chunks_rel_path=news_chunks_rel_path,
                    news_vendor=news_vendor,
                    embedding_model=embedding_model,
                    symbol=symbol
                )

                # Convert command string into argument list (Windows-safe)
                cmd = shlex.split(cmd_str, posix=False)

                self.logger.info(f"[INGEST] Using downloaded path: {downloaded_path}")

            except Exception as ex:
                self.logger.exception("[INGEST] Error preparing ingest command")
                return PlainTextResponse(
                    f"❌ Error preparing ingest command: {ex}",
                    status_code=500
                )

            def extract_path(line: str):
                marker = "Artifacts saved →"
                if marker in line:
                    raw_path = line.split(marker, 1)[1].strip()
                    folder_path = str(Path(raw_path).parent)
                    session_id = request.session.get("sid")
                    ingest_state.context_by_session[session_id] = folder_path

                if "Ingestion completed" in line:
                    session_id = request.session.get("sid")
                    ingest_state.ready_by_session[session_id]=True

            # Stream ingest process output to UI in real time
            return StreamingResponse(
                ProcessStreamRunner.stream_process(
                    cmd=cmd,
                    logger=self.logger,
                    on_line=extract_path,
                    tag="INGEST"
                ),
                media_type="text/plain; charset=utf-8"
            )



