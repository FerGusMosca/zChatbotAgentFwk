# ================================
# Lightweight Logger (BOT6 style)
# All comments in English.
# ================================

import json
from datetime import datetime


class SimpleLogger:
    """
    Ultra-light logger.
    Compatible with bot._log(event, payload).
    Prints timestamp + event + payload as JSON.
    """

    def info(self, message, extra=None):
        ts = datetime.utcnow().isoformat()
        data = {
            "ts": ts,
            "msg": message,
        }

        if isinstance(extra, dict):
            data.update(extra)

        print(json.dumps(data, ensure_ascii=False))
