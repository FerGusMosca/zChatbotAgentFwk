import datetime
import os
import shlex

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse
from pathlib import Path
import subprocess
from starlette.responses import StreamingResponse
from starlette.templating import Jinja2Templates

from common.config.settings import settings
from common.util.app_logger import AppLogger
from data_access_layer.portfolio_securities_manager import PortfolioSecuritiesManager


class ProcessNewsController:

    def __init__(self):
        self.router = APIRouter(prefix="/process_news")

        # Store last generated report in memory
        self.last_output_file = None

        base = Path(__file__).parent.parent
        self.templates = Jinja2Templates(directory=base / "templates")

        self.logger = AppLogger.get_logger("ProcessNewsController")

        self.sec_mgr = PortfolioSecuritiesManager(settings.research_connection_string)

        @self.router.get("/", response_class=HTMLResponse)
        async def main(request: Request):
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


                prcess_news_cmd_file =settings.docker_process_news_cmd

                # Load command template
                template_path = (
                        Path(__file__).parent.parent /
                        "static" / "containers_cmds" / prcess_news_cmd_file
                )
                template_raw = template_path.read_text()

                # Inject variables into template (single-line CMD)
                cmd_str = template_raw.format(
                    timestamp=timestamp,
                    commands_ini=commands_ini,
                    documents_path=documents_path,
                    symbol=symbol
                )

                # Convert into argument list
                cmd = shlex.split(cmd_str, posix=False)

            except KeyError as ex:
                return PlainTextResponse(f"❌ Missing template variable: {ex}", status_code=500)
            except Exception as ex:
                return PlainTextResponse(f"❌ Error preparing command: {ex}", status_code=500)

            async def stream_output():

                try:
                    self.logger.error(f"CMD: {cmd}")
                    process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1
                    )
                    for line in process.stdout:
                        print(">>>", line)
                        yield line

                        # ===== Capture last JSON path =====
                        # comment: detect "saved" event with JSON path
                        if '"path":' in line:
                            try:
                                # comment: extract JSON string safely
                                part = line.split('"path":', 1)[1]
                                extracted = part.split('"')[1]  # first quoted string
                                self.last_output_file = extracted
                                self.logger.info(f"[OK] Extracted output file: {self.last_output_file}")
                            except Exception as ex:
                                self.logger.error(
                                    f"[FAIL] Could not extract path from line: {line.strip()} | Error: {ex}"
                                )

                except Exception as ex:
                    yield f"\n❌ Runtime error: {ex}\n"
                finally:
                    try:
                        process.stdout.close()
                        process.wait()
                    except:
                        pass

            return StreamingResponse(stream_output(), media_type="text/plain; charset=utf-8")  # comment: enable chunked streaming




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
