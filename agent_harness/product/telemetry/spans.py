"""Thin helpers so every layer (agent, tools, MCP client) instruments Sentry the same way."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import sentry_sdk


@contextmanager
def traced_step(op: str, name: str, **data: Any) -> Iterator[Any]:
    """Open a child span under the current transaction, tagged with arbitrary key/value data."""
    with sentry_sdk.start_span(op=op, name=name) as span:
        for key, value in data.items():
            span.set_data(key, value)
        yield span


def breadcrumb(category: str, message: str, **data: Any) -> None:
    sentry_sdk.add_breadcrumb(category=category, message=message, data=data, level="info")


def current_trace_id() -> str | None:
    span = sentry_sdk.get_current_span()
    return span.trace_id if span else None
