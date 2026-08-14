"""read_file_contents — ingest local repo files to answer developer queries."""

from __future__ import annotations

from pathlib import Path

from agent_harness.scenarios.failure_engine import FailureEngine
from agent_harness.tools.base import BaseTool


class FileInspectorTool(BaseTool):
    name = "read_file_contents"
    description = "Read the contents of a file within the project repository, given a relative path."

    def __init__(self, failure_engine: FailureEngine, root_dir: str = ".") -> None:
        super().__init__(failure_engine)
        self._root = Path(root_dir).resolve()

    def _run(self, path: str) -> str:
        target = (self._root / path).resolve()
        if self._root not in target.parents and target != self._root:
            return f"Error: path '{path}' escapes the project root."
        if not target.exists() or not target.is_file():
            return f"Error: file not found: {path}"
        return target.read_text(errors="replace")
