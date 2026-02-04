from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.constants import START
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

logger = logging.getLogger(__name__)


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
    requires_hitl: Optional[Callable[[str], bool]] = None,
    hitl_callback: Optional[Callable[[str, Dict[str, Any]], Any]] = None,
    post_response: Optional[Callable[[AIMessage, MessagesState], AIMessage]] = None,
) -> StateGraph:
    """
    Reusable graph:
      - reasoner node (LLM) bound to tools
      - conditional tool execution
      - optional HITL gating per tool
      - optional post-processing of AI response

    requires_hitl: tool_name -> bool
    hitl_callback: (tool_name, tool_args) -> raises/interrupts or returns modified args
    post_response: (ai_message, state) -> ai_message (e.g., attach tool outputs)
    """
    if requires_hitl is None:

        def _no_hitl(_: str) -> bool:
            return False

        requires_hitl = _no_hitl

    tool_node = ToolNode(tools)

    async def reasoner(state: MessagesState):
        sys_text = system_builder(state)
        msgs = [AIMessage(content=sys_text, role="system")] + state["messages"]
        response = await model.ainvoke(msgs)

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
