"""FastMCP server exposing the three demo tools over stdio or SSE.

Run standalone for SSE: `python -m agent_harness.experiments.mcp.server`
For stdio it is spawned as a subprocess by MCPToolProvider, one per client connection.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP

from agent_harness.product.config import get_settings
from agent_harness.experiments.scenarios.failure_engine import FailureEngine, ScenarioFlags
from agent_harness.experiments.tools.database import DatabaseTool
from agent_harness.experiments.tools.file_inspector import FileInspectorTool
from agent_harness.experiments.tools.shell_executor import ShellExecutorTool

settings = get_settings()

# The only scenario that lives at the tool/server layer is silent truncation; the
# client that spawns us forwards the current toggle state via env vars (see
# MCPToolProvider._server_config), since this may run as a separate OS process.
_flags = ScenarioFlags(silent_truncation=os.environ.get("SCENARIO_SILENT_TRUNCATION") == "1")
_failures = FailureEngine(settings, _flags)

_file_tool = FileInspectorTool(_failures)
_db_tool = DatabaseTool(_failures, settings.db_path)
_shell_tool = ShellExecutorTool(_failures)

mcp = FastMCP("agent-harness-tools")


@mcp.tool()
def read_file_contents(path: str) -> str:
    """Read the contents of a file within the project repository, given a relative path."""
    return _file_tool.execute(path=path)


@mcp.tool()
def query_database(query: str, limit: int = 100) -> str:
    """Run a read-only SQL SELECT against the demo SQLite database, capped to 'limit' rows.

    Schema:
      users(id INTEGER, name TEXT, email TEXT, plan TEXT)
      orders(id INTEGER, user_id INTEGER REFERENCES users(id), item TEXT, amount_usd REAL, status TEXT)
      invoices(id TEXT, user_id INTEGER REFERENCES users(id), period TEXT, subtotal_usd REAL,
               discount_usd REAL, tax_usd REAL, charged_usd REAL)
    """
    return _db_tool.execute(query=query, limit=limit)


@mcp.tool()
def execute_bash(command: str) -> str:
    """Execute a read-only shell command (git, ls, pwd, echo, cat, wc, date)."""
    return _shell_tool.execute(command=command)


if __name__ == "__main__":
    if settings.mcp_transport == "sse":
        mcp.run(transport="sse", host="0.0.0.0", port=8765)
    else:
        mcp.run()
