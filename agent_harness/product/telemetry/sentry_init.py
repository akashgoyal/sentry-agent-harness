"""One-shot Sentry SDK bootstrap. Call once at process startup (API server or CLI)."""

from __future__ import annotations

import sentry_sdk

from agent_harness.product.config import Settings


def init_sentry(settings: Settings) -> None:
    if not settings.sentry_dsn:
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=1.0,
        send_default_pii=False,
    )
    sentry_sdk.set_tag("llm.provider", settings.llm_provider)
    sentry_sdk.set_tag("llm.model", settings.llm_model)
