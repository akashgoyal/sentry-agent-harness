"""Central, env-driven configuration for the whole harness."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Sentry
    sentry_dsn: str = ""
    sentry_environment: str = "local"
    sentry_org: str = ""
    sentry_project: str = ""

    # LLM provider
    llm_provider: str = "anthropic"  # anthropic | openai | ollama | together
    llm_model: str = "claude-sonnet-5"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    together_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # MCP
    mcp_transport: str = "stdio"  # stdio | sse
    mcp_sse_url: str = "http://localhost:8765/sse"

    # Agent behavior
    max_iterations: int = 6
    truncation_limit_chars: int = 2000

    # Data
    db_path: str = "data/demo.db"


def get_settings() -> Settings:
    return Settings()
