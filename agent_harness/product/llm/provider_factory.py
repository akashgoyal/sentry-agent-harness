"""LLMProviderFactory — the single place that turns Settings into a bound chat model.

Adding a new provider is one more branch here; nothing else in the harness changes.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from agent_harness.product.config import Settings


class LLMProviderFactory:
    # Deterministic, low-temperature sampling: this agent's job is reliable tool selection,
    # not creative variety, and tool-calling accuracy degrades noticeably at higher temperatures
    # (especially for smaller local models).
    _TEMPERATURE = 0.0

    @staticmethod
    def create(settings: Settings) -> BaseChatModel:
        provider = settings.llm_provider.lower()

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(
                model=settings.llm_model,
                api_key=settings.anthropic_api_key,
                temperature=LLMProviderFactory._TEMPERATURE,
            )

        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.openai_api_key,
                temperature=LLMProviderFactory._TEMPERATURE,
            )

        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(
                model=settings.llm_model,
                base_url=settings.ollama_base_url,
                temperature=LLMProviderFactory._TEMPERATURE,
            )

        if provider == "together":
            from langchain_together import ChatTogether

            return ChatTogether(
                model=settings.llm_model,
                api_key=settings.together_api_key,
                temperature=LLMProviderFactory._TEMPERATURE,
            )

        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
            "Expected one of: anthropic, openai, ollama, together."
        )
