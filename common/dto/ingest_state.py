from typing import Callable, Awaitable

class IngestState:
    def __init__(self):
        self.context_by_session: dict[str, str] = {}          # session_id -> ingest_path
        self.ready_by_session: dict[str, bool] = {}  # session_id -> completed
        self.query_by_session: dict[str, str] = {}   # session_id -> last query
        self.callbacks: dict[str, list[Callable[[str, str], Awaitable[None]]]] = {}

    def register_callback(self, session_id: str, cb: Callable[[str, str], Awaitable[None]]):
        self.callbacks.setdefault(session_id, []).append(cb)

    async def invoke_callback(self, session_id: str):
        if session_id in  self.ready_by_session :
            path = self.context_by_session.get(session_id)
            query = self.query_by_session.get(session_id)

            if not path or not query:
                return  "Missing path or query to proceed!"

            result = None
            for cb in self.callbacks.get(session_id, []):
                result = await cb(query, path)

            return result
        else:
            return "Session not ready to proceed!"

ingest_state = IngestState()
