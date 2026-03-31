from __future__ import annotations

from langchain_core.tools import StructuredTool

from agentic_backend.core.agents.v2.deep.runtime import (
    _allows_standard_filesystem_tools,
    _build_deepagent_runtime_middleware,
    _filesystem_prompt_suffix,
)
from agentic_backend.core.agents.v2.react.react_tool_binding import BoundTool


def _tool(name: str) -> StructuredTool:
    async def _handler() -> str:
        return "ok"

    return StructuredTool.from_function(
        func=None,
        coroutine=_handler,
        name=name,
        description=f"Tool {name}.",
    )


def test_deep_runtime_enables_filesystem_when_standard_tools_are_present() -> None:
    bound_tools = (
        BoundTool(
            runtime_name="ls",
            description="List files.",
            tool=_tool("ls"),
        ),
        BoundTool(
            runtime_name="knowledge_search",
            description="Search corpus.",
            tool=_tool("knowledge_search"),
        ),
    )

    assert _allows_standard_filesystem_tools(bound_tools) is True
    assert _filesystem_prompt_suffix(filesystem_tools_enabled=True) == ""
    assert _build_deepagent_runtime_middleware(filesystem_tools_enabled=True) == []


def test_deep_runtime_blocks_filesystem_when_standard_tools_are_absent() -> None:
    bound_tools = (
        BoundTool(
            runtime_name="knowledge_search",
            description="Search corpus.",
            tool=_tool("knowledge_search"),
        ),
    )

    assert _allows_standard_filesystem_tools(bound_tools) is False
    assert "Filesystem tools are disabled" in _filesystem_prompt_suffix(
        filesystem_tools_enabled=False
    )
    assert len(_build_deepagent_runtime_middleware(filesystem_tools_enabled=False)) == 7
