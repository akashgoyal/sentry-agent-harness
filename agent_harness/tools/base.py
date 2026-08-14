"""Common shape for the demo tools: name/description + traced, scenario-aware execution."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent_harness.scenarios.failure_engine import FailureEngine
from agent_harness.telemetry.spans import traced_step


class BaseTool(ABC):
    name: str
    description: str

    def __init__(self, failure_engine: FailureEngine) -> None:
        self._failures = failure_engine

    @abstractmethod
    def _run(self, **kwargs: Any) -> str:
        """Do the actual work and return a string result."""

    def execute(self, **kwargs: Any) -> str:
        with traced_step("tool.call", self.name, tool_input=kwargs) as span:
            result = self._failures.maybe_truncate(self._run(**kwargs))
            span.set_data("tool_output_len", len(result))
            return result
