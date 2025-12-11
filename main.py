# main.py
import argparse
import importlib
import logging
import os
from pathlib import Path
import time
from common.config.settings import get_settings
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from common.util.app_logger import AppLogger
from common.util.logger.logger import SimpleLogger
from common.util.settings.env_deploy_reader import EnvDeployReader
from controllers import chat_controller



# ---------- Boot / CLI ----------

EnvDeployReader.load(get_settings().deploy_file)
BASE_DIR = Path(__file__).resolve().parent
logger = SimpleLogger(loki_url=get_settings().loki_url,
                      grafana_on=get_settings().grafana_on)

# Parse CLI arg: --prompt generic|lawyer|<name>
parser = argparse.ArgumentParser(description="zChatbotAgentFwk")
parser.add_argument("--prompt", type=str, default="generic", help="Prompt file name (without .txt)")
args, _ = parser.parse_known_args()

prompt_file = BASE_DIR / "prompts" / f"{args.prompt}.txt"

try:
    prompt_text = prompt_file.read_text(encoding="utf-8")
    # Expose the selected prompt name via env var so the rest of the app can read it
    os.environ["ZBOT_PROMPT_NAME"] = args.prompt
    logger.info(
        "Prompt loaded",
        extra={"prompt_name": args.prompt, "prompt_path": str(prompt_file)}
    )
except FileNotFoundError:
    logger.error(
        "Prompt file not found",
        extra={"prompt_name": args.prompt, "prompt_path": str(prompt_file)}
    )
    raise


# ---------- FastAPI App ----------
def _load_webhooks(app):

    if get_settings().webhook is not None:
        webhook_logic = get_settings().webhook
        module = importlib.import_module(webhook_logic.split(",")[0])
        class_name = webhook_logic.split(",")[1]
        cls = getattr(module, class_name)
        cls(app)

app = FastAPI(title="zChatbotAgentFwk")
app.include_router(chat_controller.router)
_load_webhooks(app)

# Templates & static use absolute paths to avoid chdir side effects
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ---------- Middleware ----------




@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    """
    Simple request logging with latency.
    """
    start = time.time()
    path = request.url.path
    method = request.method
    try:
        response = await call_next(request)
        latency_ms = int((time.time() - start) * 1000)
        logger.info(
            "http_request",
            extra={"method": method, "path": path, "status": response.status_code, "latency_ms": latency_ms}
        )
        return response
    except Exception as ex:
        latency_ms = int((time.time() - start) * 1000)
        logger.error(
            "http_error",
            extra={"method": method, "path": path, "error": str(ex), "latency_ms": latency_ms}
        )
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)


# ---------- Routes ----------

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    # Debug banner on startup to confirm which prompt is active (safe for dev)
    logger.info("render_main", extra={"prompt_active": os.getenv("ZBOT_PROMPT_NAME")})
    return templates.TemplateResponse("main_page.html", {"request": request, "prompt": os.getenv("ZBOT_PROMPT_NAME")})

@app.get("/healthz")
async def healthz():
    return {"status": "ok", "prompt": os.getenv("ZBOT_PROMPT_NAME")}

# API router (chat endpoints)
from controllers.whatsapp_controller import router as whatsapp_router
app.include_router(chat_controller.router)
app.include_router(whatsapp_router, prefix="/whatsapp")


# ---------- Dev entrypoint ----------



if __name__ == "__main__":
    import uvicorn



    # Use 0.0.0.0 if you want to test from other devices in your LAN
    port= int( get_settings().port)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, timeout_keep_alive=120, workers=1)
    # Increased timeout to 120s to support slow SSI + CrossEncoder (up to 25s total)
    logger.info(f"App successfully loaded in port {port}")



print (__name__)
