"""
Model-call routing and tracing helpers for ReAct execution.

Why this module exists:
- LangChain can call the chat model directly, but Fred adds two platform concerns
  around those calls: model routing and tracing
- routing needs small operation labels such as `routing` and `planning`
- tracing needs a wrapper that records which model was used for one ReAct turn
- keeping that logic here prevents those SDK-specific details from spreading into
  the Fred runtime contract or prompt code

How to use:
- use `infer_react_model_operation_from_messages(...)` before a model call when
  deciding whether the turn is initial routing or tool-driven planning
- use `build_tool_loop_model_call_wrapper(...)` when compiling the shared ReAct
  tool loop so plain ReAct and HITL produce the same tracing behavior

Example:
- operation inference:
  `operation = infer_react_model_operation_from_messages(messages)`
- tracing wrapper:
  `wrapper = build_tool_loop_model_call_wrapper(tracer=tracer, binding=binding, ...)`
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from typing import Any, Protocol, cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ..contracts.context import BoundRuntimeContext
from ..contracts.runtime import TracerPort

TRACE_MODEL_SPAN_NAME = "v2.react.model"

# Model-operation labels are Fred tracing metadata, not agent-facing concepts.
# Why they exist:
# - routed model factories may choose different model configs for different kinds
#   of ReAct work inside one turn
# - tracing should make that split visible without leaking SDK event shapes
# How to use:
# - `routing` is the safe default for generic assistant turns
# - `planning` marks turns where the assistant is already in a tool-driven loop
# Example:
# - the first assistant response in a turn usually traces as `routing`
# - a follow-up model call after tool execution traces as `planning`
REACT_MODEL_OPERATION_ROUTING = "routing"
REACT_MODEL_OPERATION_PLANNING = "planning"


class CompiledReActAgent(Protocol):
    """
    Small protocol for the compiled LangChain/LangGraph ReAct executor.

    Why this exists:
    - Fred should depend on the tiny compiled-agent behavior it needs, not on one
      concrete SDK class
    - tests can fake this protocol without reproducing LangGraph internals

    How to use:
    - return any object implementing this protocol from the runtime compiler

    Example:
    - `compiled_agent.ainvoke(input, config=config)`
    """

    async def ainvoke(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
    ) -> dict[str, list[BaseMessage]]: ...

    def astream(
        self,
        input: object,
        *,
        config: Mapping[str, object] | None = None,
        stream_mode: str | list[str],
    ) -> AsyncIterator[object]: ...


def extract_model_name_from_object(value: object) -> str | None:
    """
    Read the configured model name from one LangChain chat model object.

    Why this exists:
    - Fred tracing should tag model-call spans with the selected model when possible
    - providers expose that value under different attributes

    How to use:
    - pass the active `BaseChatModel` or another candidate object

    Example:
    - `extract_model_name_from_object(model)`
    """

    if isinstance(value, BaseChatModel):
        for attr in ("model_name", "model", "model_id"):
            raw = getattr(value, attr, None)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def extract_model_name_from_model_response(response: object) -> str | None:
    """
    Read the effective model name from one LangChain model response.

    Why this exists:
    - the configured model and the effective provider model can differ
    - Fred final events and traces should prefer the response-reported model name

    How to use:
    - pass one assistant `AIMessage` or LangChain model response wrapper

    Example:
    - `extract_model_name_from_model_response(response)`
    """

    if isinstance(response, AIMessage):
        return _extract_model_name_from_message(response)

    model_response = getattr(response, "model_response", None)
    if model_response is not None:
        response = model_response

    result = getattr(response, "result", None)
    if not isinstance(result, list):
        return None

    for item in reversed(result):
        model_name = _extract_model_name_from_message(item)
        if model_name is not None:
            return model_name
    return None


def infer_react_model_operation_from_messages(
    messages: Sequence[object],
) -> str:
    """
    Infer the current ReAct phase from message history.

    Why this exists:
    - Fred model routing and tracing distinguish routing from planning turns
    - one best-effort inference function keeps those decisions consistent

    How to use:
    - pass the chronological conversation history before a model call

    Example:
    - `infer_react_model_operation_from_messages(messages)`
    """

    for message in reversed(messages):
        if message.__class__.__name__ == "ToolMessage":
            return REACT_MODEL_OPERATION_PLANNING
        if isinstance(message, HumanMessage):
            return REACT_MODEL_OPERATION_ROUTING
    return REACT_MODEL_OPERATION_ROUTING


def build_tool_loop_model_call_wrapper(
    *,
    tracer: TracerPort | None,
    binding: BoundRuntimeContext,
    infer_operation_from_messages: Callable[[Sequence[object]], str],
    default_operation: str,
) -> Callable[[object, object, Callable[[], Any]], Any] | None:
    """
    Build the model-call wrapper used by the shared ReAct tool loop.

    Why this exists:
    - plain ReAct and HITL should emit the same model-call spans and operation metadata
    - tracing and operation inference belong in the SDK adapter layer, not in prompts

    How to use:
    - pass the returned wrapper into the shared tool loop compiler

    Example:
    - `build_tool_loop_model_call_wrapper(tracer=tracer, binding=binding, ...)`
    """

    if tracer is None:
        return None

    async def _wrap(
        state: object,
        model_for_call: object,
        invoke_model: Callable[[], object],
    ) -> object:
        state_messages = state.get("messages", []) if isinstance(state, dict) else []
        messages = state_messages if isinstance(state_messages, list) else []
        operation = (
            infer_operation_from_messages(messages) if messages else default_operation
        )
        attributes: dict[str, object] = {"operation": operation}
        model_name = extract_model_name_from_object(model_for_call)
        if model_name is not None:
            attributes["model_name"] = model_name
        span = tracer.start_span(
            name=TRACE_MODEL_SPAN_NAME,
            context=binding.portable_context,
            attributes=cast(dict[str, str | int | float | bool | None], attributes),
        )
        try:
            response = await cast(Any, invoke_model)()
            span.set_attribute("status", "ok")
            response_model_name = extract_model_name_from_model_response(response)
            if response_model_name is not None:
                span.set_attribute("model_name", response_model_name)
            return response
        except Exception:
            span.set_attribute("status", "error")
            raise
        finally:
            span.end()

    return _wrap


def _extract_model_name_from_message(message: BaseMessage | object) -> str | None:
    """
    Read one model name directly from a LangChain message metadata payload.

    Why this exists:
    - response messages are the smallest place where provider model names appear
    - the public model-name helpers share this low-level extraction logic

    How to use:
    - pass one assistant message or chunk

    Example:
    - `_extract_model_name_from_message(message)`
    """

    if not isinstance(message, BaseMessage):
        return None
    response_metadata = getattr(message, "response_metadata", {}) or {}
    if not isinstance(response_metadata, dict):
        return None
    raw_model_name = response_metadata.get("model_name") or response_metadata.get(
        "model"
    )
    if isinstance(raw_model_name, str) and raw_model_name.strip():
        return raw_model_name.strip()
    return None
