# controllers/chat_controller.py
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import time
from pathlib import Path
from common.config.settings import get_settings
from common.dto.ingest_state import ingest_state
from common.util.app_logger import AppLogger
from fastapi import WebSocket, WebSocketDisconnect
router = APIRouter(prefix="/chatbot", tags=["Chatbot"])
logger = AppLogger.get_logger(__name__)

def _log_chat_metrics(question: str, latency_ms: int, bot) -> None:
    import json
    m = getattr(bot, "last_metrics", {}) or {}


@router.post("/ask")
async def ask_question(request: Request):
    session_id = request.session.get("sid")

    if session_id is not None and session_id in ingest_state.callbacks.keys():
        body = await request.json()
        ingest_state.query_by_session[session_id] = body["question"]


        path = ingest_state.context_by_session.get(session_id)
        completed = ingest_state.ready_by_session.get(session_id)
    
        if not completed:
            return {"answer": "⏳ Waiting other process to process any question..."}
    
        if not path:
            return {"answer": "⏳ No context information extracted for this session!"}

        ingest_state.ready_by_session[session_id]=True
        resp = await ingest_state.invoke_callback(session_id)
        return {"answer": resp}
    else:
        return {"answer": "🔴 Initialization Error!..."}


