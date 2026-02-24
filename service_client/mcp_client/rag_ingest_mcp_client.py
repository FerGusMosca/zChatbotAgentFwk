import asyncio
import json
import os
from typing import AsyncGenerator

import websockets

from common.util.std_in_out.root_locator import RootLocator


class RAGIngestMCPClient:
    def __init__(
        self,
        mode: str,
        source: str,
        dest_root: str,
        chunk_name: str,
        embedding_model: str,
        clustering_model: str,
        log_posfix: str,
        persist_qdrant: bool,
        qdrant_collection: str,
        uri: str = None
    ):
        self._mode = mode
        self._source = source
        self._dest_root = dest_root
        self._chunk_name = chunk_name
        self._embedding_model = embedding_model
        self._clustering_model = clustering_model
        self._log_posfix = log_posfix
        self._persist_qdrant = persist_qdrant
        self._qdrant_collection = qdrant_collection
        self._uri = uri

        self._report = "rag_ingest"
        self.last_output_folder = None
        self.ingest_error = False
        self.last_error = None

    async def execute_and_stream(self) -> AsyncGenerator[str, None]:
        """
        Execute the RAG ingest via MCP server and stream real-time progress messages.

        The method connects via WebSocket, sends the ingest payload, and listens for
        job/progress messages until the server signals completion or a real error occurs.

        Timeout handling is intentionally lenient: a single recv() timeout does NOT abort
        the process, because the MCP server may take several minutes between messages
        during heavy embedding/clustering steps. Only sustained silence (MAX_CONSECUTIVE_TIMEOUTS
        consecutive timeouts) is treated as a fatal condition.
        """

        # --- Load and populate the MCP payload template ---
        template_path = os.path.join(
            RootLocator.get_root(), "static", "mcp", "rag_ingest.json"
        )

        with open(template_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        args = payload["params"]["arguments"]

        args["report"]            = self._report
        args["mode"]              = self._mode
        args["source"]            = self._source
        args["dest_root"]         = self._dest_root
        args["chunk_name"]        = self._chunk_name
        args["embedding_model"]   = self._embedding_model
        args["clustering_model"]  = self._clustering_model
        args["log_posfix"]        = self._log_posfix
        args["persist_qdrant"]    = self._persist_qdrant
        args["qdrant_collection"] = self._qdrant_collection

        # --- Reset state flags before each execution ---
        self.ingest_error = False
        self.last_error = None
        self.last_output_folder = None

        # How many consecutive recv() timeouts are allowed before giving up.
        # Each timeout window is 120 seconds, so 5 x 120s = 10 minutes of total silence.
        MAX_CONSECUTIVE_TIMEOUTS = 5
        consecutive_timeouts = 0

        try:
            async with websockets.connect(self._uri, ping_interval=None) as ws:

                # --- Step 1: Request tools list (handshake / sanity check) ---
                await ws.send(
                    '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
                )
                list_resp = await ws.recv()
                yield f"Tools list: {list_resp}\n\n"

                # --- Step 2: Send the ingest payload ---
                await ws.send(json.dumps(payload))

                # --- Step 3: Listen for progress messages until done or fatal error ---
                while True:

                    # Try to receive the next message within the timeout window.
                    # TimeoutError is caught separately so it does NOT abort the loop —
                    # the MCP server may simply be busy and will send more messages later.
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=120.0)
                        # A message arrived — reset the consecutive timeout counter
                        consecutive_timeouts = 0

                    except asyncio.TimeoutError:
                        consecutive_timeouts += 1
                        yield (
                            f"[HEARTBEAT] No message received, server still processing... "
                            f"({consecutive_timeouts}/{MAX_CONSECUTIVE_TIMEOUTS})\n\n"
                        )

                        if consecutive_timeouts >= MAX_CONSECUTIVE_TIMEOUTS:
                            # Sustained silence: treat as a fatal timeout
                            self.ingest_error = True
                            self.last_error = (
                                f"Fatal timeout: no response from server after "
                                f"{MAX_CONSECUTIVE_TIMEOUTS * 120}s of silence"
                            )
                            yield f"[ERROR] {self.last_error}\n\n"
                            break

                        # Still within tolerance — keep waiting
                        continue

                    # --- Yield the raw message for UI visibility ---
                    yield f"MSG >>> {message}\n\n"

                    # --- Parse and inspect the message ---
                    try:
                        outer = json.loads(message)

                        if outer.get("method") == "job/progress":
                            inner_str = outer["params"].get("message", "")

                            # Check for successful completion signal
                            if inner_str and "INGESTION COMPLETED - out_folder=" in inner_str:
                                out_folder_part = inner_str.split("out_folder=", 1)[-1].strip()
                                self.last_output_folder = out_folder_part.replace("\\", "/")
                                yield f"[EXTRACTED FOLDER] {self.last_output_folder}\n\n"
                                # Clean exit: server confirmed completion
                                break

                            # Check for an explicit error reported by the server
                            if inner_str and "ERROR" in inner_str.upper():
                                self.ingest_error = True
                                self.last_error = inner_str
                                yield f"[SERVER ERROR] {inner_str}\n\n"
                                # Exit only when the server itself signals an error
                                break

                    except json.JSONDecodeError as e:
                        # Non-fatal: some progress messages may be plain-text logs, not JSON.
                        # Log and continue — do NOT set ingest_error or break the loop.
                        yield f"[SKIP] Non-JSON message ignored: {str(e)}\n\n"

                    except Exception as e:
                        # Non-fatal parse/inspection error.
                        # Log and continue — the server is still running.
                        yield f"[PARSE ERROR] {str(e)}\n\n"

        except Exception as e:
            # This outer except only catches WebSocket-level connection failures
            # (e.g. refused connection, network drop, handshake error).
            # These are always fatal — the server is unreachable.
            yield f"[CONNECTION ERROR] {str(e)}\n\n"
            self.ingest_error = True
            self.last_error = str(e)