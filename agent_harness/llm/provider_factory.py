"""LLMProviderFactory — the single place that turns Settings into a bound chat model.

Adding a new provider is one more branch here; nothing else in the harness changes.
"""

from __future__ import annotations

from langchain_core.language_models.chat_models import BaseChatModel

from agent_harness.config import Settings


class LLMProviderFactory:
    @staticmethod
    def create(settings: Settings) -> BaseChatModel:
        provider = settings.llm_provider.lower()

        if provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=settings.llm_model, api_key=settings.anthropic_api_key)

        if provider == "openai":
            from langchain_openai import ChatOpenAI

            return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key)

        if provider == "ollama":
            from langchain_ollama import ChatOllama

            return ChatOllama(model=settings.llm_model, base_url=settings.ollama_base_url)

        if provider == "together":
            from langchain_together import ChatTogether

            return ChatTogether(model=settings.llm_model, api_key=settings.together_api_key)

        raise ValueError(
            f"Unknown LLM_PROVIDER '{settings.llm_provider}'. "
            "Expected one of: anthropic, openai, ollama, together."
        )
