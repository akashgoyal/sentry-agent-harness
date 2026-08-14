"""execute_bash — run a small allow-listed set of read-only shell commands."""

from __future__ import annotations

import shlex
import subprocess

from agent_harness.tools.base import BaseTool

_ALLOWED_COMMANDS = {"git", "ls", "pwd", "echo", "cat", "wc", "date"}


class ShellExecutorTool(BaseTool):
    name = "execute_bash"
    description = "Execute a read-only shell command (git, ls, pwd, echo, cat, wc, date) and return stdout/stderr."

    def _run(self, command: str) -> str:
        try:
            parts = shlex.split(command)
        except ValueError as exc:
            return f"Error: could not parse command: {exc}"
        if not parts or parts[0] not in _ALLOWED_COMMANDS:
            return f"Error: command '{command}' is not on the allow-list {sorted(_ALLOWED_COMMANDS)}."
        result = subprocess.run(parts, capture_output=True, text=True, timeout=10)
        return f"$ {command}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}\nexit_code: {result.returncode}"
