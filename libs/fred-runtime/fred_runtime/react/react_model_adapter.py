# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Model-call routing and tracing helpers for ReAct execution.

Why this module exists:
- LangChain can call the chat model directly, but Fred adds two platform concerns
  around those calls: model routing and tracing
- routing needs small operation labels such as `routing` and `planning`
- tracing needs stable helpers to read model names from models and responses
- keeping that logic here prevents those SDK-specific details from spreading into
  the Fred runtime contract or prompt code

How to use:
- use `infer_react_model_operation_from_messages(...)` before a model call when
  deciding whether the turn is initial routing or tool-driven planning
- the model-call span/KPI instrumentation itself lives in
  `react_middleware.TracingKpiMiddleware` (re-homed there by #1972)

Example:
- operation inference:
  `operation = infer_react_model_operation_from_messages(messages)`
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Protocol

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

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
