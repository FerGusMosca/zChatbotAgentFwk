# llm_client/open_ai/openai_llm.py
"""
OpenAI-specific LLM wrapper.
Reads its API key from settings — no env vars, no exports.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from typing import Any, Optional

from common.config.settings import settings


class OpenAILLM:
    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens

        self._client = ChatOpenAI(
            model=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=settings.openai_api_key,
        )

    def invoke(self, prompt: str) -> str:
        response = self._client.invoke(prompt)
        return self._extract_content(response)

    def invoke_messages(self, messages: list[BaseMessage]) -> str:
        response = self._client.invoke(messages)
        return self._extract_content(response)

    @staticmethod
    def _extract_content(response: Any) -> str:
        if hasattr(response, "content"):
            return response.content.strip()
        return str(response).strip()

    def get_client(self):
        return self._client

    def handle(self, query):
        return self.invoke(query)