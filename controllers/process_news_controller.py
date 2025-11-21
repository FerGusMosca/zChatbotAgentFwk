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

                # Load command template
                template_path = (
                        Path(__file__).parent.parent /
                        "static" / "containers_cmds" / "process_news.txt"
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
                        yield line
                except Exception as ex:
                    yield f"\n❌ Runtime error: {ex}\n"
                finally:
                    try:
                        process.stdout.close()
                        process.wait()
                    except:
                        pass

            return StreamingResponse(stream_output(), media_type="text/plain")





