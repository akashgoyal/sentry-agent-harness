"""The 'bug toggle deck' — deterministic, demoable failure modes.

A single FailureEngine instance is shared across a session (held on `app.state` for the
API, constructed fresh per CLI invocation) so flags can be flipped live between agent runs
and every layer (tools, MCP client, agent graph) consults the same state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any

from agent_harness.product.config import Settings
from agent_harness.product.telemetry.spans import breadcrumb


@dataclass
class ScenarioFlags:
    silent_truncation: bool = False
    infinite_tool_loop: bool = False
    mcp_schema_mismatch: bool = False
    context_inflation: bool = False


class FailureEngine:
    def __init__(self, settings: Settings, flags: ScenarioFlags | None = None) -> None:
        self._settings = settings
        self._flags = flags or ScenarioFlags()
        self._lock = Lock()

    @property
    def flags(self) -> ScenarioFlags:
        return self._flags

    def as_dict(self) -> dict[str, bool]:
        return asdict(self._flags)

    def update(self, **changes: bool) -> None:
        with self._lock:
            for key, value in changes.items():
                if not hasattr(self._flags, key):
                    raise ValueError(f"Unknown scenario flag: {key}")
                setattr(self._flags, key, value)
        breadcrumb("scenario", "toggle updated", **self.as_dict())

    # --- Silent Truncation Mode: cut oversized tool output, no exception raised ---
    def maybe_truncate(self, text: str) -> str:
        limit = self._settings.truncation_limit_chars
        if not self._flags.silent_truncation or len(text) <= limit:
            return text
        breadcrumb("scenario.silent_truncation", "tool output truncated", original_len=len(text), limit=limit)
        return text[:limit]

    # --- Infinite Tool Loop Mode: disable the "empty result -> stop" boundary ---
    def bypass_empty_result_stop(self, last_tool_result_was_empty: bool) -> bool:
        return self._flags.infinite_tool_loop and last_tool_result_was_empty

    # --- MCP Schema Payload Mismatch Mode: send a wrong JSON type to the tool ---
    def corrupt_payload(self, args: dict[str, Any]) -> dict[str, Any]:
        if not self._flags.mcp_schema_mismatch:
            return args
        corrupted = dict(args)
        for key, value in corrupted.items():
            if isinstance(value, (list, int)):
                corrupted[key] = "not-a-valid-type"
                breadcrumb("scenario.mcp_schema_mismatch", "corrupted outgoing arg", arg=key)
                break
        return corrupted

    # --- Context Inflation / Memory Leak Mode: skip normal history trimming ---
    def should_trim_context(self) -> bool:
        return not self._flags.context_inflation
