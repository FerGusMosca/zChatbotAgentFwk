import json

from common.dto.dynamic_query import DynamicQueryDTO

class DynamicQuery:
    """
    Static helper to detect and parse dynamic query payloads.
    """

    @staticmethod
    def parse(raw_query: str) -> DynamicQueryDTO:
        """
        Tries to parse a dynamic query JSON.
        If structure is invalid, falls back to plain query.
        """

        if not raw_query:
            return DynamicQueryDTO(
                is_dynamic=False,
                query=""
            )

        raw_query = raw_query.strip()

        # Fast reject: not JSON-like
        if not raw_query.startswith("{"):
            return DynamicQueryDTO(
                is_dynamic=False,
                query=raw_query
            )

        try:
            payload = json.loads(raw_query)
        except Exception:
            # Invalid JSON → treat as plain query
            return DynamicQueryDTO(
                is_dynamic=False,
                query=raw_query
            )

        # Mandatory fields
        if not isinstance(payload, dict):
            return DynamicQueryDTO(
                is_dynamic=False,
                query=raw_query
            )

        query = payload.get("query")
        chunks_folder = payload.get("chunks_folder")

        if not query or not chunks_folder:
            return DynamicQueryDTO(
                is_dynamic=False,
                query=raw_query
            )

        return DynamicQueryDTO(
            is_dynamic=True,
            query=query,
            chunks_folder=chunks_folder
        )
