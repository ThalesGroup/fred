"""
Compatibility bridge between v2 runtimes and the existing chat pipeline.

Today, the chat stack still calls `astream_updates(...)` with a LangGraph-like
shape. This wrapper adapts v2 runtimes (ReAct/Graph) to that interface so we
can migrate incrementally without rewriting transport and persistence in one go.
"""

from __future__ import annotations

from typing import Any, cast

from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
)
from langchain_core.messages.tool import ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from pydantic import BaseModel

from ..contracts.context import BoundRuntimeContext
from ..contracts.models import GraphAgentDefinition, ReActAgentDefinition
from ..contracts.runtime import (
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    FinalRuntimeEvent,
    RuntimeEvent,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from ..graph.runtime import GraphRuntime
from ..react.react_langchain_adapter import (
    from_langchain_message,
    stringify_langchain_content,
)
from ..react.react_runtime import (
    ReActInput,
    ReActRuntime,
)
from ..react.react_tool_utils import sanitize_tool_name as _sanitize_tool_name

SessionCompatibleRuntime = ReActRuntime | GraphRuntime


class V2SessionAgent:
    """
    Adapter exposed to the chat layer for one bound runtime instance.

    Practical role:
    - convert incoming chat state to typed v2 input models
    - run the runtime executor
    - convert runtime events back to legacy stream events
    """

    def __init__(self, *, runtime: SessionCompatibleRuntime) -> None:
        self._runtime = runtime
        self.run_config: RunnableConfig = {}

    @property
    def streaming_memory(self):
        return self._runtime.services.checkpointer

    def get_id(self) -> str:
        return self._runtime.definition.agent_id

    @property
    def definition(self) -> GraphAgentDefinition | ReActAgentDefinition:
        return self._runtime.definition

    @property
    def binding(self) -> BoundRuntimeContext:
        return self._runtime.binding

    def rebind(self, binding: BoundRuntimeContext) -> None:
        tool_invoker = self._runtime.services.tool_invoker
        if tool_invoker is not None:
            rebind = getattr(tool_invoker, "rebind", None)
            if callable(rebind):
                rebind(binding)
        self._runtime.bind(binding)

    async def astream_updates(
        self,
        state: Any,
        *,
        config: RunnableConfig | None = None,
        stream_mode: Any = "updates",
        context: object | None = None,
    ):
        self.run_config = config if config is not None else {}
        execution_config = _execution_config_from_runnable_config(
            self.run_config,
            state=state,
        )
        requested_modes = _requested_stream_modes(stream_mode)

        if isinstance(self._runtime, ReActRuntime):
            input_model = (
                cast(BaseModel, _resume_input_placeholder(self._runtime))
                if isinstance(state, Command)
                else _v2_input_from_state(state, runtime=self._runtime)
            )
            executor = await self._runtime.get_executor()
            event_stream = executor.stream(
                cast(ReActInput, input_model), execution_config, context=context
            )
        else:
            input_model = (
                _resume_input_placeholder(self._runtime)
                if isinstance(state, Command)
                else _v2_input_from_state(state, runtime=self._runtime)
            )
            executor = await self._runtime.get_executor()
            event_stream = executor.stream(
                input_model, execution_config, context=context
            )

        async for event in event_stream:
            for legacy_event in _legacy_events_from_runtime_event(
                event, requested_modes=requested_modes
            ):
                yield legacy_event

    async def aclose(self) -> None:
        await self._runtime.dispose()


def _react_input_from_state(state: Any) -> ReActInput:
    if not isinstance(state, dict):
        raise TypeError(
            f"V2SessionAgent expects dict state input, got {type(state).__name__}."
        )

    raw_messages = state.get("messages")
    if not isinstance(raw_messages, list):
        raise TypeError("V2SessionAgent state must provide a list under 'messages'.")

    return ReActInput(
        messages=tuple(
            from_langchain_message(
                cast(BaseMessage, message),
                sanitize_tool_name=_sanitize_tool_name,
            )
            for message in raw_messages
        )
    )


def _v2_input_from_state(
    state: Any,
    *,
    runtime: SessionCompatibleRuntime,
) -> BaseModel:
    definition = runtime.definition
    if isinstance(definition, ReActAgentDefinition):
        return _react_input_from_state(state)
    if isinstance(definition, GraphAgentDefinition):
        return _graph_input_from_state(state, definition=definition)
    raise TypeError(
        f"Unsupported v2 definition type for session bridge: {type(definition).__name__}."
    )


def _execution_config_from_runnable_config(
    config: RunnableConfig, *, state: Any
) -> ExecutionConfig:
    configurable = config.get("configurable") or {}
    thread_id = configurable.get("thread_id")
    if thread_id is not None and not isinstance(thread_id, str):
        thread_id = str(thread_id)
    checkpoint_id = configurable.get("checkpoint_id")
    if checkpoint_id is not None and not isinstance(checkpoint_id, str):
        checkpoint_id = str(checkpoint_id)

    passthrough_config: dict[str, object] = {
        key: value for key, value in config.items() if key != "configurable"
    }
    if isinstance(configurable, dict):
        passthrough_config["configurable"] = dict(configurable)

    resume_payload = state.resume if isinstance(state, Command) else None
    return ExecutionConfig(
        thread_id=thread_id,
        checkpoint_id=checkpoint_id,
        adapter_config=passthrough_config,
        resume_payload=resume_payload,
    )


def _resume_input_placeholder(
    runtime: SessionCompatibleRuntime,
) -> BaseModel:
    definition = runtime.definition
    if isinstance(definition, ReActAgentDefinition):
        return ReActInput.model_construct(messages=())
    if isinstance(definition, GraphAgentDefinition):
        return definition.input_model().model_construct()
    raise TypeError(
        f"Unsupported v2 definition type for resume placeholder: {type(definition).__name__}."
    )


def _graph_input_from_state(
    state: Any, *, definition: GraphAgentDefinition
) -> BaseModel:
    if not isinstance(state, dict):
        raise TypeError(
            f"V2SessionAgent expects dict state input, got {type(state).__name__}."
        )

    input_model_cls = definition.input_model()
    payload: dict[str, object] = {
        key: value
        for key, value in state.items()
        if key in input_model_cls.model_fields and key != "messages"
    }

    raw_messages = state.get("messages")
    latest_user_text = _latest_human_text(raw_messages)
    if latest_user_text:
        for preferred_key in ("message", "text", "prompt", "input"):
            if (
                preferred_key in input_model_cls.model_fields
                and preferred_key not in payload
            ):
                payload[preferred_key] = latest_user_text
                break

    return input_model_cls.model_validate(payload)


def _latest_human_text(raw_messages: object) -> str | None:
    if not isinstance(raw_messages, list):
        return None

    for message in reversed(raw_messages):
        if isinstance(message, HumanMessage):
            return stringify_langchain_content(message.content)
    return None


def _requested_stream_modes(stream_mode: object) -> frozenset[str]:
    if isinstance(stream_mode, str):
        return frozenset({stream_mode})
    if isinstance(stream_mode, (list, tuple, set)):
        modes = {mode for mode in stream_mode if isinstance(mode, str)}
        if modes:
            return frozenset(modes)
    return frozenset({"updates"})


def _legacy_events_from_runtime_event(
    event: RuntimeEvent, *, requested_modes: frozenset[str]
) -> list[object]:
    if isinstance(event, AssistantDeltaRuntimeEvent):
        if "messages" not in requested_modes:
            return []
        return [
            (
                "messages",
                (
                    AIMessageChunk(content=event.delta),
                    {"langgraph_node": "agent"},
                ),
            )
        ]

    if isinstance(event, AwaitingHumanRuntimeEvent):
        if "updates" not in requested_modes:
            return []
        return [
            {
                "__interrupt__": {
                    "value": _interrupt_payload_from_request(event.request),
                }
            }
        ]

    if "updates" not in requested_modes:
        return []

    if isinstance(event, ToolCallRuntimeEvent):
        return [
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "id": event.call_id,
                                    "name": event.tool_name,
                                    "args": event.arguments,
                                }
                            ],
                        )
                    ]
                }
            }
        ]

    if isinstance(event, ToolResultRuntimeEvent):
        response_metadata = _tool_response_metadata(event)
        additional_kwargs = _tool_additional_kwargs(event)
        return [
            {
                "tools": {
                    "messages": [
                        ToolMessage(
                            content=event.content,
                            tool_call_id=event.call_id,
                            name=event.tool_name,
                            additional_kwargs=additional_kwargs,
                            response_metadata=response_metadata,
                        )
                    ]
                }
            }
        ]

    if isinstance(event, FinalRuntimeEvent):
        response_metadata = _final_response_metadata(event)
        additional_kwargs = _final_additional_kwargs(event)
        return [
            {
                "agent": {
                    "messages": [
                        AIMessage(
                            content=event.content,
                            additional_kwargs=additional_kwargs,
                            response_metadata=response_metadata,
                        )
                    ]
                }
            }
        ]

    return []


def _interrupt_payload_from_request(request: Any) -> dict[str, object]:
    payload = request.model_dump(mode="json", exclude_none=True)
    if payload.get("choices") == []:
        payload.pop("choices", None)
    if payload.get("metadata") == {}:
        payload.pop("metadata", None)
    return payload


def _tool_response_metadata(event: ToolResultRuntimeEvent) -> dict[str, object]:
    response_metadata: dict[str, object] = {}
    if event.sources:
        response_metadata["sources"] = [
            source.model_dump(mode="json") for source in event.sources
        ]
    if event.is_error:
        response_metadata["ok"] = False
    return response_metadata


def _tool_additional_kwargs(event: ToolResultRuntimeEvent) -> dict[str, object]:
    if not event.ui_parts:
        return {}
    return {"fred_parts": _serialize_ui_parts(event.ui_parts)}


def _final_response_metadata(event: FinalRuntimeEvent) -> dict[str, object]:
    response_metadata: dict[str, object] = {}
    if event.sources:
        response_metadata["sources"] = [
            source.model_dump(mode="json") for source in event.sources
        ]
    if event.model_name:
        response_metadata["model_name"] = event.model_name
    if event.token_usage is not None:
        response_metadata["token_usage"] = dict(event.token_usage)
    if event.finish_reason is not None:
        response_metadata["finish_reason"] = event.finish_reason
    return response_metadata


def _final_additional_kwargs(event: FinalRuntimeEvent) -> dict[str, object]:
    if not event.ui_parts:
        return {}
    return {"fred_parts": _serialize_ui_parts(event.ui_parts)}


def _serialize_ui_parts(parts: tuple[object, ...]) -> list[dict[str, object]]:
    serialized: list[dict[str, object]] = []
    for part in parts:
        model_dump = getattr(part, "model_dump", None)
        if callable(model_dump):
            payload = model_dump(mode="json")
            if isinstance(payload, dict):
                serialized.append(payload)
    return serialized
