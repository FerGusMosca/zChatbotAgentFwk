# common/llm/openai_llm.py
"""
OpenAI-specific LLM wrapper.
Fully decoupled from the rest of the pipeline.
Ready for factory injection.
All comments in English.
"""
from langchain_openai import ChatOpenAI
from langchain_core.messages import BaseMessage
from typing import Any, Optional


class OpenAILLM:
    """
    Simple OpenAI LLM wrapper.
    Exposes only what the pipeline needs: .invoke(string) → str
    """
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
        )

    def invoke(self, prompt: str) -> str:
        """Takes a raw string prompt → returns clean text response."""
        response = self._client.invoke(prompt)
        return self._extract_content(response)

    def invoke_messages(self, messages: list[BaseMessage]) -> str:
        """For chat-history or multi-turn scenarios."""
        response = self._client.invoke(messages)
        return self._extract_content(response)

    @staticmethod
    def _extract_content(response: Any) -> str:
        """Safe extraction regardless of response type."""
        if hasattr(response, "content"):
            return response.content.strip()
        return str(response).strip()