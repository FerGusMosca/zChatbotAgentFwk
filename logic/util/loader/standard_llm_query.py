# ===== standard_llm_query.py =====
# Simple query parser for standard LLM invocations.
# Validates that JSON contains both 'query' and 'prompt' fields.
# Optionally supports 'base64_content' field for compressed content.

import json
import base64
import gzip
from typing import Optional
from dataclasses import dataclass


@dataclass
class StandardLLMQueryDTO:
    """
    Data transfer object for standard LLM queries.
    """
    is_valid: bool
    query: str
    prompt: Optional[str] = None
    error_message: Optional[str] = None
    had_base64_content: bool = False  # Indicates if base64 content was decoded


class StandardLLMQuery:
    """
    Static helper to detect and parse standard LLM query payloads.
    Expected format: {"query": "...", "prompt": "..."}
    """

    @staticmethod
    def parse(raw_query: str) -> StandardLLMQueryDTO:
        """
        Tries to parse a standard LLM query JSON.
        Validates presence of both 'query' and 'prompt' fields.

        Args:
            raw_query: JSON string with query and prompt

        Returns:
            StandardLLMQueryDTO with validation results
        """

        # Validate input is not empty
        if not raw_query or not raw_query.strip():
            return StandardLLMQueryDTO(
                is_valid=False,
                query="",
                error_message="Empty query received"
            )

        raw_query = raw_query.strip()

        # Fast reject: not JSON-like
        if not raw_query.startswith("{"):
            return StandardLLMQueryDTO(
                is_valid=False,
                query=raw_query,
                error_message="Query is not in JSON format. Expected: {\"query\": \"...\", \"prompt\": \"...\"}"
            )

        # Parse JSON
        try:
            payload = json.loads(raw_query)
        except json.JSONDecodeError as e:
            return StandardLLMQueryDTO(
                is_valid=False,
                query=raw_query,
                error_message=f"Invalid JSON format: {str(e)}"
            )
        except Exception as e:
            return StandardLLMQueryDTO(
                is_valid=False,
                query=raw_query,
                error_message=f"Unexpected error parsing JSON: {str(e)}"
            )

        # Validate payload is a dictionary
        if not isinstance(payload, dict):
            return StandardLLMQueryDTO(
                is_valid=False,
                query=raw_query,
                error_message="JSON payload must be an object/dictionary"
            )

        # Extract fields
        query = payload.get("query")
        prompt = payload.get("prompt")

        # Validate mandatory fields
        if not query:
            return StandardLLMQueryDTO(
                is_valid=False,
                query="",
                error_message="Missing required field: 'query'"
            )

        if not prompt:
            return StandardLLMQueryDTO(
                is_valid=False,
                query=query,
                error_message="Missing required field: 'prompt'"
            )

        # Validate field types
        if not isinstance(query, str):
            return StandardLLMQueryDTO(
                is_valid=False,
                query=str(query) if query else "",
                error_message="Field 'query' must be a string"
            )

        if not isinstance(prompt, str):
            return StandardLLMQueryDTO(
                is_valid=False,
                query=query,
                error_message="Field 'prompt' must be a string"
            )

        # Validate non-empty strings
        if not query.strip():
            return StandardLLMQueryDTO(
                is_valid=False,
                query="",
                error_message="Field 'query' cannot be empty"
            )

        if not prompt.strip():
            return StandardLLMQueryDTO(
                is_valid=False,
                query=query,
                error_message="Field 'prompt' cannot be empty"
            )

        # Process optional base64_content field
        base64_content = payload.get("base64_content")
        had_base64 = False

        if base64_content:
            try:
                # Validate it's a string
                if not isinstance(base64_content, str):
                    return StandardLLMQueryDTO(
                        is_valid=False,
                        query=query,
                        error_message="Field 'base64_content' must be a string"
                    )

                # Decode base64
                compressed_data = base64.b64decode(base64_content.strip())

                # Decompress gzip
                decompressed_text = gzip.decompress(compressed_data).decode('utf-8')

                # Append to query
                query = f"{query.strip()}\n\n{decompressed_text}"
                had_base64 = True

            except base64.binascii.Error as e:
                return StandardLLMQueryDTO(
                    is_valid=False,
                    query=query,
                    error_message=f"Invalid base64 encoding in 'base64_content': {str(e)}"
                )
            except gzip.BadGzipFile as e:
                return StandardLLMQueryDTO(
                    is_valid=False,
                    query=query,
                    error_message=f"Invalid gzip compression in 'base64_content': {str(e)}"
                )
            except UnicodeDecodeError as e:
                return StandardLLMQueryDTO(
                    is_valid=False,
                    query=query,
                    error_message=f"Invalid UTF-8 encoding after decompression: {str(e)}"
                )
            except Exception as e:
                return StandardLLMQueryDTO(
                    is_valid=False,
                    query=query,
                    error_message=f"Error processing base64_content: {str(e)}"
                )

        # Success
        return StandardLLMQueryDTO(
            is_valid=True,
            query=query.strip(),
            prompt=prompt.strip(),
            had_base64_content=had_base64
        )