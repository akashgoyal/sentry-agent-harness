"""MCPToolProvider — real FastMCP connection exposing tools as LangChain-compatible objects."""

from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool as LangchainTool
from langchain_core.tools import StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent_harness.product.config import Settings
from agent_harness.experiments.scenarios.failure_engine import FailureEngine
from agent_harness.product.telemetry.spans import traced_step

_SERVER_NAME = "agent-harness-tools"

_JSON_TYPE_TO_PY: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _validate_against_schema(schema: dict[str, Any], args: dict[str, Any]) -> None:
    """Raise if an arg's Python type doesn't match its declared JSON-schema type."""
    properties = schema.get("properties", {})
    for key, value in args.items():
        expected = _JSON_TYPE_TO_PY.get(properties.get(key, {}).get("type"))
        if expected and not isinstance(value, expected):
            declared = properties[key]["type"]
            raise TypeError(f"MCP schema mismatch: '{key}' expected {declared}, got {type(value).__name__}={value!r}")


class MCPToolProvider:
    """Owns the MCP client connection and bridges each remote tool into a Sentry-traced,
    scenario-aware LangChain tool the agent graph can bind to its LLM call."""

    def __init__(self, settings: Settings, failure_engine: FailureEngine) -> None:
        self._settings = settings
        self._failures = failure_engine
        self._client = MultiServerMCPClient({_SERVER_NAME: self._server_config()})

    def _server_config(self) -> dict[str, Any]:
        if self._settings.mcp_transport == "sse":
            return {"url": self._settings.mcp_sse_url, "transport": "sse"}
        flags = self._failures.flags
        return {
            "command": "python",
            "args": ["-m", "agent_harness.experiments.mcp.server"],
            "transport": "stdio",
            "env": {"SCENARIO_SILENT_TRUNCATION": "1" if flags.silent_truncation else "0"},
        }

    async def get_tools(self) -> list[LangchainTool]:
        with traced_step("mcp.connect", "load MCP tools", transport=self._settings.mcp_transport):
            raw_tools = await self._client.get_tools()
        return [self._wrap(tool) for tool in raw_tools]

    def _wrap(self, tool: LangchainTool) -> LangchainTool:
        """Route calls through the FailureEngine (MCP schema-mismatch injection) and a span.

        Calls `tool.ainvoke(...)` (not the raw coroutine) so LangChain's own response-format
        post-processing still runs and the wrapper always yields plain content back out.

        The schema-mismatch scenario validates the (corrupted) args against the tool's own
        JSON schema *before* sending, so the TypeError raises here — unhandled, the same way a
        real client bug would surface — rather than being caught and downgraded to a text error
        result inside FastMCP's own request handling.
        """

        async def traced_call(**kwargs: Any) -> Any:
            outgoing = self._failures.corrupt_payload(kwargs)
            if outgoing != kwargs and isinstance(tool.args_schema, dict):
                _validate_against_schema(tool.args_schema, outgoing)
            with traced_step("mcp.tool_call", tool.name, tool_input=outgoing):
                return await tool.ainvoke(outgoing)

        return StructuredTool.from_function(
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
            coroutine=traced_call,
        )
