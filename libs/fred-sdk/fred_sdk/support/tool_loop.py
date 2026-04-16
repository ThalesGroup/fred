"""
Reusable ReAct-style LangGraph tool-loop builder.

Why this module exists:
- ReAct and Deep runtimes both need a model-calls-tools-loops-until-done graph
- keeping this builder in the SDK means the pattern is available to any runtime
  without depending on platform infrastructure

How to use it:
- call build_tool_loop(model, tools, system_builder) to get a compiled StateGraph
- optionally pass model_resolver, hitl_callback, and post_response hooks
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.constants import START
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)


def _sanitize_dangling_tool_calls(messages: List[Any]) -> List[Any]:
    """
    Remove any AIMessage(tool_calls=...) whose call_ids are not all answered
    by immediately-following ToolMessages.

    Why this exists:
    - When a turn crashes mid-flight (e.g. OpenAI 400 on a previous call), the
      LangGraph checkpoint stores the user message and the assistant tool_call
      request, but never the tool result. Every subsequent turn then loads that
      poisoned checkpoint state and OpenAI rejects the payload with:
        "tool_call_ids did not have response messages: <id>"
    - Sanitizing here is the only safe place: it covers both the in-memory
      and persisted checkpoint paths, regardless of whether history restore
      ran or was skipped.

    What it does:
    - Walk through messages in order.
    - For each AIMessage with tool_calls, check that every call_id has a
      matching ToolMessage immediately following it.
    - If ANY call_id is unmatched, drop the AIMessage AND any partial
      ToolMessages that followed it, then continue with the rest of the
      message list (preserving subsequent user messages so the current
      query is not lost).
    """
    result: List[Any] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        tool_calls = (
            getattr(msg, "tool_calls", None) if isinstance(msg, AIMessage) else None
        )
        if tool_calls:
            expected_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
            # Scan immediately-following ToolMessages
            j = i + 1
            seen_ids: set[str] = set()
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                call_id = getattr(messages[j], "tool_call_id", None)
                if call_id:
                    seen_ids.add(call_id)
                j += 1
            if expected_ids and expected_ids == seen_ids:
                # Fully matched — keep AIMessage + all ToolMessages
                result.extend(messages[i:j])
                i = j
            else:
                # Dangling or partial — drop AIMessage and partial ToolMessages,
                # keep everything after (user messages for the current turn).
                logger.warning(
                    "[TOOL_LOOP] Dropped dangling AIMessage(tool_calls) at index %d "
                    "expected_ids=%s seen_ids=%s. "
                    "This usually means a prior turn crashed before the tool result was stored.",
                    i,
                    expected_ids,
                    seen_ids,
                )
                i = j  # skip over partial ToolMessages too
        else:
            result.append(msg)
            i += 1
    return result


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
        msgs = [SystemMessage(content=sys_text)] + _sanitize_dangling_tool_calls(
            state["messages"]
        )
        current_model = model_resolver(state) if model_resolver is not None else model

        async def _invoke_model() -> Any:
            return await current_model.ainvoke(msgs)

        response = (
            await model_call_wrapper(state, current_model, _invoke_model)
            if model_call_wrapper is not None
            else await _invoke_model()
        )

        if post_response is None:
            tool_payloads = collect_tool_outputs(state["messages"])
            md = getattr(response, "response_metadata", {}) or {}
            tools_md = md.get("tools", {}) or {}
            tools_md.update(tool_payloads)
            md["tools"] = tools_md
            response.response_metadata = md
        return {"messages": [response]}

    async def gate_tools(state: MessagesState):
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
                    result = await hitl_callback(name, args)
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
