# ===== common/util/logger/logger.py =====
# 2025 production – lightweight + async Loki (zero blocking)

import json
from datetime import datetime
from threading import Thread
from queue import Queue, Empty
from typing import Optional
import requests

from common.config.settings import get_settings


class SimpleLogger:
    def __init__(self, loki_url: Optional[str] = None, grafana_on: bool = False):
        self.loki_url = loki_url
        self.grafana_on = grafana_on

        # Cola asíncrona (máx 1000 mensajes)
        if self.grafana_on and self.loki_url:
            self.queue: Queue = Queue(maxsize=1000)
            self.worker = Thread(target=self._loki_worker, daemon=True)
            self.worker.start()

    def _loki_worker(self):
        """Worker asíncrono – nunca bloquea el bot"""
        session = requests.Session()
        while True:
            try:
                level, msg, extra = self.queue.get(timeout=1)
                app_name = extra.get("app") or f"App_{get_settings().bot_profile}"

                payload = {
                    "streams": [{
                        "stream": {"level": level, "app": app_name},
                        "values": [[str(int(datetime.utcnow().timestamp() * 1e9)), f"{msg} {json.dumps(extra or {})}"]]
                    }]
                }
                session.post(self.loki_url + "/loki/api/v1/push", json=payload, timeout=2)
            except Empty:
                continue
            except Exception:
                pass
    def _log(self, level: str, message: str, extra: dict | None = None):
        data = {
            "ts": datetime.utcnow().isoformat(),
            "level": level,
            "msg": message,
        }
        if extra:
            data.update(extra)

        print(json.dumps(data, ensure_ascii=False))

        # Push asíncrono a Loki
        if self.grafana_on and self.loki_url:
            try:
                self.queue.put_nowait((level, message, extra))
            except:
                pass  # cola llena → descartamos (mejor que bloquear)

    def info(self, message, extra=None):    self._log("INFO", message, extra)
    def error(self, message, extra=None):   self._log("ERROR", message, extra)
    def warning(self, message, extra=None): self._log("WARNING", message, extra)