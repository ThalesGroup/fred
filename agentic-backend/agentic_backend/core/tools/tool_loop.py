from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.constants import START
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)


def _trim_to_human_boundary(messages: list, max_messages: int) -> list:
    """
    Keep the last `max_messages` entries, then scan forward to the first
    HumanMessage so the context never starts mid tool-call/result pair.
    """
    if len(messages) <= max_messages:
        return messages
    trimmed = messages[-max_messages:]
    for i, msg in enumerate(trimmed):
        if isinstance(msg, HumanMessage):
            return trimmed[i:]
    return trimmed


def collect_tool_outputs(messages: List[Any]) -> Dict[str, Any]:
    """
    Collect latest ToolMessage content per tool name.
    Normalizes string content by attempting JSON decode.
    """
    tool_payloads: Dict[str, Any] = {}
    for msg in messages:
        name = getattr(msg, "name", None)
        if isinstance(msg, ToolMessage) and isinstance(name, str):
            raw = msg.content
            normalized: Any = raw
            if isinstance(raw, str):
                try:
                    normalized = json.loads(raw)
                except Exception:
                    normalized = raw
            tool_payloads[name] = normalized
    return tool_payloads


def build_tool_loop(
    model,
    tools: List[BaseTool],
    system_builder: Callable[[MessagesState], str],
    model_resolver: Optional[Callable[[MessagesState], Any]] = None,
    model_call_wrapper: Optional[
        Callable[[MessagesState, Any, Callable[[], Awaitable[Any]]], Awaitable[Any]]
    ] = None,
    requires_hitl: Optional[Callable[[str], bool]] = None,
    hitl_callback: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    rewrite_tool_call: Optional[
        Callable[[str, Dict[str, Any], MessagesState], Dict[str, Any]]
    ] = None,
    post_response: Optional[Callable[[AIMessage, MessagesState], AIMessage]] = None,
    max_history_messages: Optional[int] = None,
) -> StateGraph:
    """
    Reusable graph for ReAct-style model and tool execution.

    Why this exists:
    - Fred needs one small execution loop that can power plain tool use and optional
      human approval without duplicating graph wiring
    - path rewrites or tracing hooks should plug in once here instead of forking
      separate executors

    How to use:
    - pass the bound model, tool list, and a system-message builder
    - optionally provide tool-call rewriting, human-approval gating, model-call
      wrapping, or AI post-processing hooks

    Example:
    - `build_tool_loop(model=bound_model, tools=tools, system_builder=builder)`
    """
    if requires_hitl is None:

        def _no_hitl(_: str) -> bool:
            return False

        requires_hitl = _no_hitl

    tool_node = ToolNode(tools)

    async def reasoner(state: MessagesState):
        sys_text = system_builder(state)
        all_messages = state["messages"]
        if max_history_messages is not None:
            trimmed = _trim_to_human_boundary(all_messages, max_history_messages)
            logger.info(
                "[TOOL LOOP] history trimmed: %d → %d messages (max_history_messages=%d)",
                len(all_messages),
                len(trimmed),
                max_history_messages,
            )
        else:
            trimmed = all_messages
        msgs = [SystemMessage(content=sys_text)] + trimmed
        current_model = model_resolver(state) if model_resolver is not None else model

        async def _invoke_model() -> Any:
            return await current_model.ainvoke(msgs)

        response = (
            await model_call_wrapper(state, current_model, _invoke_model)
            if model_call_wrapper is not None
            else await _invoke_model()
        )

        # Attach latest tool outputs if post_response not provided
        if post_response is None:
            tool_payloads = collect_tool_outputs(state["messages"])
            md = getattr(response, "response_metadata", {}) or {}
            tools_md = md.get("tools", {}) or {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md
        return {"messages": [response]}

    async def gate_tools(state: MessagesState):
        """
        Inspect pending tool calls; if any require HITL, delegate to hitl_callback
        which is expected to interrupt (raise) or mutate args.
        """
        if not requires_hitl:
            return {}

        if state.get("hitl_completed"):
            return {}

        last = state["messages"][-1] if state["messages"] else None
        tool_calls = getattr(last, "tool_calls", None) or []
        updated = False
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else None
            raw_args = tc.get("args") if isinstance(tc, dict) else {}
            args: Dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            if name and rewrite_tool_call is not None:
                rewritten_args = rewrite_tool_call(name, dict(args), state)
                if rewritten_args != args:
                    args = rewritten_args
                    tc["args"] = args
                    updated = True
            if name and requires_hitl(name):
                if hitl_callback:
                    result = await hitl_callback(name, args)  # may raise interrupt
                    if isinstance(result, dict):
                        if result.get("cancel"):
                            return {"hitl_completed": True, "skip_tools": True}
                        notes = result.get("notes")
                        if notes:
                            args["notes"] = notes
                            tc["args"] = args
                        updated = True
        if updated:
            return {"hitl_completed": True}
        return {}

    def _route_after_gate(state: MessagesState) -> str:
        return "skip" if state.get("skip_tools") else "execute"

    async def tool_exec(state: MessagesState):
        # Last message is a ToolCall; ToolNode already ran. Nothing to do.
        return {}

    g = StateGraph(MessagesState)
    g.add_node("reasoner", reasoner)
    g.add_node("tools", tool_node)
    g.add_node("gate_tools", gate_tools)
    g.add_node("tool_exec", tool_exec)

    g.add_edge(START, "reasoner")
    g.add_conditional_edges(
        "reasoner",
        tools_condition,
        {
            "tools": "gate_tools",
            "__end__": END,
        },
    )
    g.add_conditional_edges(
        "gate_tools",
        _route_after_gate,
        {
            "execute": "tools",
            "skip": "reasoner",
        },
    )
    g.add_edge("tools", "tool_exec")
    g.add_edge("tool_exec", "reasoner")

    return g
