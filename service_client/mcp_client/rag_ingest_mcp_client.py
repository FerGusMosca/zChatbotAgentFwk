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
        """Execute the RAG ingest via MCP server and stream real-time messages."""

        template_path = os.path.join(
            RootLocator.get_root(), "static", "mcp", "rag_ingest.json"
        )

        with open(template_path, "r", encoding="utf-8") as f:
            payload = json.load(f)

        args = payload["params"]["arguments"]

        args["report"] = self._report
        args["mode"] = self._mode
        args["source"] = self._source
        args["dest_root"] = self._dest_root
        args["chunk_name"] = self._chunk_name
        args["embedding_model"] = self._embedding_model
        args["clustering_model"] = self._clustering_model
        args["log_posfix"] = self._log_posfix

        # NEW FIELDS
        args["persist_qdrant"] = self._persist_qdrant
        args["qdrant_collection"] = self._qdrant_collection

        self.ingest_error = False
        self.last_error = None

        try:
            async with websockets.connect(self._uri, ping_interval=None) as ws:

                await ws.send(
                    '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
                )
                list_resp = await ws.recv()
                yield f"Tools list: {list_resp}\n\n"

                await ws.send(json.dumps(payload))

                while True:
                    message = await asyncio.wait_for(ws.recv(), timeout=120.0)
                    yield f"MSG >>> {message}\n\n"

                    try:
                        outer = json.loads(message)
                        if outer.get("method") == "job/progress":
                            inner_str = outer["params"].get("message", "")
                            if inner_str and "INGESTION COMPLETED - out_folder=" in inner_str:
                                out_folder_part = inner_str.split(
                                    "out_folder=", 1
                                )[-1].strip()
                                self.last_output_folder = out_folder_part.replace("\\", "/")
                                yield f"[EXTRACTED FOLDER] {self.last_output_folder}\n\n"

                    except json.JSONDecodeError as e:
                        yield f"[SKIP] Invalid JSON: {str(e)}\n\n"
                        self.ingest_error = True
                        self.last_error = str(e)

                    except Exception as e:
                        yield f"[PARSE ERROR] {str(e)}\n\n"
                        self.ingest_error = True
                        self.last_error = str(e)

        except Exception as e:
            yield f"Error: {str(e)}\n\n"
            self.ingest_error = True
            self.last_error = str(e)