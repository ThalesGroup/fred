"""
Transcript conversion between Fred ReAct messages and LangChain message objects.

Why this module exists:
- Fred agent authors work with typed Fred transcript models such as `ReActMessage`
  and `ReActInput`
- LangChain and LangGraph expect SDK message classes such as `HumanMessage`,
  `AIMessage`, and `ToolMessage`
- this module is the narrow bridge between those two transcript shapes

How to use:
- use `graph_input_from_react_input(...)` right before calling the compiled ReAct
  agent
- use `from_langchain_message(...)` or `final_assistant_message(...)` when turning
  LangChain output back into the Fred transcript

Example:
- fresh execution:
  `graph_input = graph_input_from_react_input(input_model, config, sanitize_tool_name=name_fn)`
- final assistant turn:
  `assistant_message = final_assistant_message(messages, sanitize_tool_name=name_fn)`
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.messages.tool import ToolMessage
from langgraph.types import Command

from ..contracts.react_contract import (
    ReActInput,
    ReActMessage,
    ReActMessageRole,
    ReActToolCall,
)
from ..contracts.runtime import ExecutionConfig


def stringify_langchain_content(value: object) -> str:
    """
    Render LangChain message content blocks as one plain string.

    Why this exists:
    - LangChain content can be plain text or structured blocks
    - the Fred transcript should expose one simple text form

    How to use:
    - pass any `message.content` value before storing it in the Fred-side transcript

    Example:
    - `stringify_langchain_content(message.content)`
    """

    if isinstance(value, str):
        return value
    if isinstance(value, list):
        rendered_parts: list[str] = []
        for item in value:
            if isinstance(item, dict) and "text" in item:
                rendered_parts.append(str(item["text"]))
            else:
                rendered_parts.append(str(item))
        return "\n".join(part for part in rendered_parts if part)
    return str(value)


def to_langchain_message(
    message: ReActMessage,
    *,
    sanitize_tool_name: Callable[[str], str],
) -> BaseMessage:
    """
    Convert one Fred-side ReAct message to the LangChain message equivalent.

    Why this exists:
    - the Fred contract deliberately avoids LangChain classes
    - the runtime still needs a precise bridge into LangChain/LangGraph execution

    How to use:
    - pass one `ReActMessage` before sending transcript state to the compiled agent

    Example:
    - `to_langchain_message(message, sanitize_tool_name=_sanitize_tool_name)`
    """

    if message.role == ReActMessageRole.SYSTEM:
        return SystemMessage(content=message.content)
    if message.role == ReActMessageRole.ASSISTANT:
        return AIMessage(
            content=message.content,
            tool_calls=[
                {
                    "id": tool_call.call_id,
                    "name": sanitize_tool_name(tool_call.name),
                    "args": tool_call.arguments,
                }
                for tool_call in message.tool_calls
            ],
        )
    if message.role == ReActMessageRole.TOOL:
        if message.tool_call_id is None:
            raise RuntimeError("ReAct tool messages require tool_call_id.")
        return ToolMessage(
            content=message.content,
            tool_call_id=message.tool_call_id,
            name=(
                sanitize_tool_name(message.tool_name)
                if isinstance(message.tool_name, str) and message.tool_name.strip()
                else None
            ),
        )
    return HumanMessage(content=message.content)


def from_langchain_message(
    message: BaseMessage,
    *,
    sanitize_tool_name: Callable[[str], str],
) -> ReActMessage:
    """
    Convert one LangChain message to the Fred-side ReAct transcript shape.

    Why this exists:
    - LangChain message classes should not leak into Fred runtime outputs
    - a single conversion path keeps transcript normalization deterministic

    How to use:
    - pass one LangChain message emitted by the compiled agent

    Example:
    - `from_langchain_message(message, sanitize_tool_name=_sanitize_tool_name)`
    """

    if isinstance(message, SystemMessage):
        return ReActMessage(
            role=ReActMessageRole.SYSTEM,
            content=stringify_langchain_content(message.content),
        )
    if isinstance(message, HumanMessage):
        return ReActMessage(
            role=ReActMessageRole.USER,
            content=stringify_langchain_content(message.content),
        )
    if isinstance(message, ToolMessage):
        return ReActMessage(
            role=ReActMessageRole.TOOL,
            content=stringify_langchain_content(message.content),
            tool_name=getattr(message, "name", None),
            tool_call_id=getattr(message, "tool_call_id", None),
        )
    return ReActMessage(
        role=ReActMessageRole.ASSISTANT,
        content=stringify_langchain_content(message.content),
        tool_calls=tuple(
            ReActToolCall(
                call_id=str(tool_call.get("id") or ""),
                name=sanitize_tool_name(str(tool_call.get("name") or "")),
                arguments=tool_call.get("args") or {},
            )
            for tool_call in getattr(message, "tool_calls", []) or []
            if str(tool_call.get("id") or "").strip()
            and str(tool_call.get("name") or "").strip()
        ),
    )


def final_assistant_message(
    messages: Sequence[BaseMessage],
    *,
    sanitize_tool_name: Callable[[str], str],
) -> ReActMessage:
    """
    Return the last assistant message from one compiled-agent transcript.

    Why this exists:
    - the Fred runtime final result should always point to the last assistant turn
    - centralizing that lookup avoids repeating LangChain message checks

    How to use:
    - call after `compiled_agent.ainvoke(...)`

    Example:
    - `final_message = final_assistant_message(messages, sanitize_tool_name=_sanitize_tool_name)`
    """

    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return from_langchain_message(
                message,
                sanitize_tool_name=sanitize_tool_name,
            )
    raise RuntimeError("ReAct execution completed without an assistant message.")


def to_runnable_config(config: ExecutionConfig) -> Mapping[str, object] | None:
    """
    Convert Fred execution config to LangChain runnable config.

    Why this exists:
    - Fred execution options and LangChain runnable config are not the same shape
    - the adapter should map only the supported cross-over fields

    How to use:
    - call before `ainvoke(...)` or `astream(...)` on the compiled agent

    Example:
    - `compiled_agent.ainvoke(graph_input, config=to_runnable_config(config))`
    """

    merged: dict[str, object] = dict(config.adapter_config)
    configurable_raw = merged.get("configurable")
    configurable: dict[str, object] = (
        dict(configurable_raw) if isinstance(configurable_raw, Mapping) else {}
    )

    if config.thread_id is not None:
        configurable["thread_id"] = config.thread_id

    if configurable:
        merged["configurable"] = configurable
    else:
        merged.pop("configurable", None)

    return merged or None


def graph_input_from_react_input(
    input_model: ReActInput,
    config: ExecutionConfig,
    *,
    sanitize_tool_name: Callable[[str], str],
) -> Mapping[str, object] | Command:
    """
    Convert Fred ReAct input to the compiled-agent graph input.

    Why this exists:
    - resume calls use LangGraph `Command`, while fresh calls use a message payload
    - the runtime should prepare that shape once in one adapter helper

    How to use:
    - pass the Fred input model plus execution config before invoking the graph

    Example:
    - `graph_input_from_react_input(input_model, config, sanitize_tool_name=_sanitize_tool_name)`
    """

    if config.resume_payload is not None:
        return Command(resume=config.resume_payload)
    return {
        "messages": [
            to_langchain_message(message, sanitize_tool_name=sanitize_tool_name)
            for message in input_model.messages
        ]
    }
