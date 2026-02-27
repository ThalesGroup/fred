from __future__ import annotations

import pytest

pytest.importorskip("langgraph")

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agentic_backend.core.tools.tool_loop import build_tool_loop


class _CaptureModel:
    def __init__(self) -> None:
        self.calls: list[list[object]] = []

    async def ainvoke(self, messages):
        self.calls.append(list(messages))
        return AIMessage(content="ok")


@pytest.mark.asyncio
async def test_build_tool_loop_prepends_real_system_message():
    model = _CaptureModel()

    graph = build_tool_loop(
        model=model,
        tools=[],
        system_builder=lambda _state: "System guardrails",
    ).compile()

    result = await graph.ainvoke({"messages": [HumanMessage(content="hello")]})

    assert "messages" in result
    assert model.calls, "Model should have been invoked at least once"
    first_call = model.calls[0]
    assert isinstance(first_call[0], SystemMessage)
    assert not isinstance(first_call[0], AIMessage)
    assert first_call[0].content == "System guardrails"
    assert isinstance(first_call[1], HumanMessage)
