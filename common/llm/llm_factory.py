# common/llm/llm_factory.py
"""
LLM Factory – Single source of truth for LLM instantiation.
"""
from __future__ import annotations

import logging
from typing import Literal, Optional, Any

from llm_client.open_ai.openai_llm import OpenAILLM

logger = logging.getLogger(__name__)
Provider = Literal["openai"]


class LLMFactory:
    _DEFAULT_PROVIDER: Provider = "openai"

    @staticmethod
    def create(
        provider: Optional[Provider] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **extra_kwargs: Any,
    ) -> OpenAILLM:
        chosen = provider or LLMFactory._DEFAULT_PROVIDER

        if chosen == "openai":
            return OpenAILLM(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                **extra_kwargs,
            )

        logger.warning(
            "[LLMFactory] Provider '%s' not supported → using OpenAI fallback",
            provider,
        )
        return OpenAILLM(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )