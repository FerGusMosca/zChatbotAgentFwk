

# Lightweight Logger  -
# All comments in English.
# ================================

import json
from datetime import datetime


class SimpleLogger:
    """
    Ultra-light logger used across the bot.
    Supports .info(), .error(), .warning()
    """

    def info(self, message, extra=None):
        self._log("INFO", message, extra)

    def error(self, message, extra=None):
        self._log("ERROR", message, extra)

    def warning(self, message, extra=None):
        self._log("WARNING", message, extra)

    def _log(self, level, message, extra=None):
        ts = datetime.utcnow().isoformat()
        data = {
            "ts": ts,
            "level": level,
            "msg": message,
        }
        if isinstance(extra, dict):
            data.update(extra)
        print(json.dumps(data, ensure_ascii=False))