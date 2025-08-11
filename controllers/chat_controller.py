# controllers/chat_controller.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import time

from common.config.settings import get_settings
from common.util.app_logger import AppLogger
from common.util.builder.bot_engine_loader import load_hybrid_bot

router = APIRouter(prefix="/chatbot", tags=["Chatbot"])
logger = AppLogger.get_logger(__name__)

def _log_chat_metrics(question: str, latency_ms: int, bot) -> None:
    import json
    m = getattr(bot, "last_metrics", {}) or {}
    payload = {
        "mode": m.get("mode"),
        "docs_found": m.get("docs_found"),
        "best_score": m.get("best_score"),
        "threshold": m.get("threshold"),
        "prompt_name": m.get("prompt_name"),
        "latency_ms": latency_ms,
        "len_q": len(question or ""),
    }
    logger.info("chat_metrics %s", json.dumps(payload, ensure_ascii=False))

@router.post("/ask")
async def ask_question(request: Request):
    try:
        import time
        start = time.time()

        payload = await request.json()
        question = (payload.get("question") or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="Missing 'question' in request body")

        hybrid_bot = load_hybrid_bot("demo_client")
        answer = hybrid_bot.handle(question)

        latency_ms = int((time.time() - start) * 1000)

        try:
            _log_chat_metrics(question, latency_ms, hybrid_bot)
        except Exception as log_ex:
            logger.warning("metrics_error", extra={"error": str(log_ex)})

        return JSONResponse(content={"answer": answer})

    except HTTPException:
        raise
    except Exception as e:
        logger.error("chat_error", extra={"error": str(e)})
        return JSONResponse(status_code=500, content={"error": "Internal error"})
