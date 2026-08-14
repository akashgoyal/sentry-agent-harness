"""AgentHarness — a hand-rolled 2-node LangGraph loop (reason -> act -> observe -> repeat).

A hand-rolled graph (rather than the prebuilt ReAct agent) is used so the failure engine can
hook directly into the two places bugs need to live: the continue/stop decision (infinite tool
loop) and the pre-LLM-call context assembly (context inflation).
"""

from __future__ import annotations

import time
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool as LangchainTool
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages

from agent_harness.agent.prompts import SystemPromptRegistry
from agent_harness.config import Settings
from agent_harness.scenarios.failure_engine import FailureEngine
from agent_harness.telemetry.spans import breadcrumb, traced_step


def _stringify_tool_output(value: Any) -> str:
    """MCP tools return either a plain string or a list of {'type': 'text', 'text': ...}
    content blocks; normalize either shape into plain text for the ToolMessage/LLM."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(block, dict) and block.get("type") == "text" for block in value):
        return "\n".join(block.get("text", "") for block in value)
    return str(value)


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    iterations: int
    last_tool_empty: bool
    prompt_tokens: int
    completion_tokens: int


class AgentResult:
    def __init__(
        self,
        answer: str,
        iterations: int,
        tool_calls: list[dict[str, Any]],
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.answer = answer
        self.iterations = iterations
        self.tool_calls = tool_calls
        self.latency_ms = latency_ms
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens


class AgentHarness:
    """Multi-turn reasoning engine: evaluates the goal, selects tools, parses responses,
    and decides when execution is complete."""

    _CONTEXT_KEEP_LAST = 8
    _TOOL_MSG_TRIM_CHARS = 500

    def __init__(
        self,
        llm: BaseChatModel,
        tools: list[LangchainTool],
        settings: Settings,
        failure_engine: FailureEngine,
        prompts: SystemPromptRegistry | None = None,
    ) -> None:
        self._settings = settings
        self._failures = failure_engine
        self._tools_by_name = {tool.name: tool for tool in tools}
        self._llm = llm.bind_tools(tools)
        self._prompts = prompts or SystemPromptRegistry()
        self._graph = self._build_graph()

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("agent", self._call_model)
        graph.add_node("tools", self._execute_tools)
        graph.set_entry_point("agent")
        graph.add_conditional_edges("agent", self._should_continue, {"tools": "tools", "end": END})
        graph.add_edge("tools", "agent")
        return graph.compile()

    async def run(self, goal: str, session_id: str) -> AgentResult:
        tool_schema = "\n".join(f"- {t.name}: {t.description}" for t in self._tools_by_name.values())
        system_prompt = self._prompts.get("default", tool_schema=tool_schema)
        initial_state: AgentState = {
            "messages": [SystemMessage(content=system_prompt), HumanMessage(content=goal)],
            "iterations": 0,
            "last_tool_empty": False,
            "prompt_tokens": 0,
            "completion_tokens": 0,
        }

        breadcrumb("agent.session", "starting run", session_id=session_id, goal=goal)
        start = time.perf_counter()
        with traced_step("agent.run", "agent harness run", session_id=session_id, goal=goal):
            recursion_limit = max(50, self._settings.max_iterations * 4)
            final_state = await self._graph.ainvoke(initial_state, config={"recursion_limit": recursion_limit})
        latency_ms = (time.perf_counter() - start) * 1000

        final_message = final_state["messages"][-1]
        answer = final_message.content if isinstance(final_message.content, str) else str(final_message.content)
        tool_calls = [
            {"tool": m.name, "output": m.content}
            for m in final_state["messages"]
            if isinstance(m, ToolMessage)
        ]
        breadcrumb("agent.session", "run finished", session_id=session_id, iterations=final_state["iterations"])

        return AgentResult(
            answer=answer,
            iterations=final_state["iterations"],
            tool_calls=tool_calls,
            latency_ms=latency_ms,
            prompt_tokens=final_state["prompt_tokens"],
            completion_tokens=final_state["completion_tokens"],
        )

    async def _call_model(self, state: AgentState) -> dict[str, Any]:
        context = self._trim(state["messages"]) if self._failures.should_trim_context() else state["messages"]
        iterations = state["iterations"] + 1
        breadcrumb("agent.iteration", "reasoning step", iteration=iterations, context_messages=len(context))

        with traced_step("agent.reason", f"iteration {iterations}", iteration=iterations) as span:
            response: AIMessage = await self._llm.ainvoke(context)
            usage = getattr(response, "usage_metadata", None) or {}
            prompt_tokens = usage.get("input_tokens", 0) or 0
            completion_tokens = usage.get("output_tokens", 0) or 0
            span.set_data("prompt_tokens", prompt_tokens)
            span.set_data("completion_tokens", completion_tokens)
            span.set_data("requested_tool_calls", len(response.tool_calls or []))

        return {
            "messages": [response],
            "iterations": iterations,
            "prompt_tokens": state["prompt_tokens"] + prompt_tokens,
            "completion_tokens": state["completion_tokens"] + completion_tokens,
        }

    async def _execute_tools(self, state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        results: list[BaseMessage] = []
        outputs: list[str] = []

        for call in last.tool_calls:
            tool = self._tools_by_name.get(call["name"])
            if tool is None:
                output = f"Unknown tool: {call['name']}"
            else:
                with traced_step("agent.tool_dispatch", call["name"], tool_call_id=call["id"]):
                    output = _stringify_tool_output(await tool.ainvoke(call["args"]))
            outputs.append(output)
            results.append(ToolMessage(content=output, tool_call_id=call["id"], name=call["name"]))

        empty = bool(outputs) and all(o.strip() in ("", "[]") for o in outputs)
        breadcrumb("agent.tools", "tool batch executed", count=len(outputs), all_empty=empty)
        return {"messages": results, "last_tool_empty": empty}

    def _should_continue(self, state: AgentState) -> str:
        iterations = state["iterations"]
        if iterations >= self._settings.max_iterations:
            breadcrumb("agent.loop", "stopping: hit max_iterations safety cap", iterations=iterations)
            return "end"

        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return "end"

        # Infinite Tool Loop Mode: normally an empty tool result ends the loop; the scenario
        # disables that boundary so the agent keeps reformulating until the safety cap above.
        if state["last_tool_empty"] and not self._failures.bypass_empty_result_stop(True):
            breadcrumb("agent.loop", "stopping: last tool call returned no data", iterations=iterations)
            return "end"

        return "tools"

    def _trim(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        """Bound context growth: keep the system message + last N turns, cap tool output size."""
        system = messages[:1] if messages and isinstance(messages[0], SystemMessage) else []
        rest = messages[len(system):]
        window = rest[-self._CONTEXT_KEEP_LAST :]
        if len(window) < len(rest):
            breadcrumb("agent.context", "trimmed older turns", dropped=len(rest) - len(window))

        bounded: list[BaseMessage] = []
        for msg in window:
            if isinstance(msg, ToolMessage) and isinstance(msg.content, str) and len(msg.content) > self._TOOL_MSG_TRIM_CHARS:
                msg = ToolMessage(
                    content=msg.content[: self._TOOL_MSG_TRIM_CHARS] + " …(context-trimmed)",
                    tool_call_id=msg.tool_call_id,
                    name=msg.name,
                )
            bounded.append(msg)
        return system + bounded
