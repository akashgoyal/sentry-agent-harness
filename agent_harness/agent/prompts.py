"""SystemPromptRegistry — configurable operational boundaries fed into the agent context."""

from __future__ import annotations

_DEFAULT = """You are a careful software engineering assistant with access to these tools:
{tool_schema}

Rules:
- Only use the tools listed above; never fabricate a tool result.
- If a tool returns no data, say so plainly instead of guessing or repeating the same call.
- Be concise and note which tool produced any factual claim.
"""


class SystemPromptRegistry:
    """Named prompt templates, rendered with the live tool schema at run time."""

    def __init__(self) -> None:
        self._prompts: dict[str, str] = {"default": _DEFAULT}

    def register(self, name: str, template: str) -> None:
        self._prompts[name] = template

    def get(self, name: str, **kwargs: str) -> str:
        return self._prompts[name].format(**kwargs)
