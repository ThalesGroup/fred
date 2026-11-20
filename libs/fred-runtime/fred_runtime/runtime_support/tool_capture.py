# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

"""Tool boundary context shared by the runtime recorder and execution clients."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from contextvars import ContextVar
from typing import TYPE_CHECKING

from fred_core.conversation_trace import TraceToolSource

if TYPE_CHECKING:
    from fred_sdk.contracts.runtime import SpanPort

    from fred_runtime.app.conversation_trace_artifacts import HttpTurnBuffer
    from fred_runtime.app.conversation_trace_tools import RecordedToolCall

active_tool_buffer: ContextVar[HttpTurnBuffer | None] = ContextVar(
    "active_conversation_tool_buffer", default=None
)
active_tool_capture: ContextVar[RecordedToolCall | None] = ContextVar(
    "active_conversation_tool_capture", default=None
)


@asynccontextmanager
async def capture_tool(
    tool_name: str, call_id: str | None, source: TraceToolSource, arguments: object
) -> AsyncIterator[RecordedToolCall | None]:
    buffer = active_tool_buffer.get()
    tool = buffer.start_tool(tool_name, call_id, source) if buffer is not None else None
    if tool is not None:
        await tool.retain("input", arguments)
    elif active_tool_capture.get() is None:
        yield None
        return
    token = active_tool_capture.set(tool)
    try:
        yield tool
    finally:
        active_tool_capture.reset(token)


def link_tool_span(span: SpanPort | None, tool: RecordedToolCall) -> None:
    """Identify the captured invocation on the span that owns its placement."""
    if span is not None:
        with suppress(Exception):
            span.set_attribute("fred.evidence.ref", tool.ref)


def capture_mcp_tool() -> RecordedToolCall | None:
    tool = active_tool_capture.get()
    if tool is not None:
        tool.source = TraceToolSource.MCP
    return tool
