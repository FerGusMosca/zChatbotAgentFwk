# common/llm/llm_factory.py
"""
LLM Factory – Single source of truth for LLM instantiation.
All comments in English.
"""
from __future__ import annotations
from typing import Literal, Optional, Dict, Any

from llm_client.open_ai.openai_llm import OpenAILLM

# Supported providers (easy to extend)
Provider = Literal["openai"]

class LLMFactory:
    """
    Factory that returns a ready-to-use LLM instance.
    If an unsupported provider is requested → falls back to OpenAI (safe default).
    """
    _DEFAULT_PROVIDER: Provider = "openai"

    @staticmethod
    def create(
        provider: Optional[Provider] = None,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        **extra_kwargs: Any,
    ) -> OpenAILLM:
        """
        Returns an LLM instance according to the requested provider.
        Parameters
        ----------
        provider : str or None
            "openai" → OpenAI (currently the only supported).
            Any other value or None → falls back to OpenAI (safe default).
        **extra_kwargs : any
            Forwarded directly to the concrete implementation.
        """
        chosen = provider or LLMFactory._DEFAULT_PROVIDER

        if chosen == "openai":
            return OpenAILLM(
                model_name=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                **extra_kwargs,
            )

        # ─────── Fallback with clear error (you will know immediately) ───────
        from common.util.logger.logger import SimpleLogger
        logger = SimpleLogger()
        logger.info(
            "[LLMFactory] Unsupported provider requested",
            {"requested": provider, "fallback": "openai"},
        )
        print(f"[LLMFactory] WARNING: Provider '{provider}' not supported → using OpenAI fallback")

        return OpenAILLM(
            model_name=model_name,
            temperature=temperature,
            max_tokens=max_tokens,
            **extra_kwargs,
        )