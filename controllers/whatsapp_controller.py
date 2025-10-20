from anyio import Path
from fastapi import APIRouter, Request
from starlette.responses import JSONResponse

from common.config.settings import get_settings
from common.integrations.twilio_adapter import TwilioAdapter
from urllib.parse import parse_qs
from common.util.app_logger import AppLogger
from common.util.builder.bot_engine_loader import load_hybrid_bot

router = APIRouter()
logger = AppLogger.get_logger(__name__)

# Load a single instance of the HybridBot (reused for each request)
settings = get_settings()
bot_profile = settings.bot_profile
bot_root_path = settings.bot_profile_root_path
client_id = str(Path(bot_root_path) / bot_profile)
bot = load_hybrid_bot(client_id)

@router.post("/webhook")
async def whatsapp_webhook(request: Request):
    """
    Webhook used by Twilio Sandbox.
    Twilio sends an inbound WhatsApp message (x-www-form-urlencoded body).
    """
    raw = await request.body()
    logger.info(f"[DEBUG] RAW BODY = {raw}")

    # Twilio Sandbox sends x-www-form-urlencoded in the body.
    payload = parse_qs(raw.decode("utf-8"))

    # Values come as list[str], so we take the first element.
    user_id = payload.get("From", [""])[0]        # e.g. 'whatsapp:+54911XXXXXXX'
    text    = payload.get("Body", [""])[0]        # user's message
    msg_id  = payload.get("MessageSid", [""])[0]  # message ID

    logger.info(f"[WhatsApp] Incoming msg {msg_id} from {user_id} -> {text}")

    # Call our HybridBot as usual
    reply_text = bot.handle(text)

    # Send outbound message via Twilio

    TwilioAdapter.send_message(to=user_id, body=reply_text)

    logger.info(f"[WhatsApp] Reply sent to {user_id}")
    return JSONResponse(status_code=200, content={"status": "sent"})