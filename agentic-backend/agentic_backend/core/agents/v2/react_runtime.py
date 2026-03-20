"""
Executable runtime for v2 ReAct agents.

Use this file to understand how a ReAct definition is executed in Fred:
1. Convert typed input messages to LangChain messages.
2. Build the tool loop from declared `tool_requirements`.
3. Stream runtime events (assistant delta, tool call/result, final).

If you are debugging a ReAct agent in production, this is the first file to
open.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, cast

from fred_core.store import VectorSearchHit
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from langchain_core.messages.tool import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Checkpointer, Command
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

try:
    from langchain.agents import create_agent as _langchain_create_agent
except Exception:  # pragma: no cover - compatibility fallback
    from langgraph.prebuilt import create_react_agent as _langgraph_create_react_agent
else:
    _langgraph_create_react_agent = None

try:  # pragma: no cover - optional middleware import for compatibility
    from langchain.agents.middleware.types import (
        AgentMiddleware as _LangchainAgentMiddleware,
    )
except Exception:  # pragma: no cover - compatibility fallback
    _LangchainAgentMiddleware = None

from .builtin_tools import (
    BuiltinToolBackend,
    get_builtin_tool_spec,
)
from .context import (
    ArtifactPublishRequest,
    BoundRuntimeContext,
    ResourceFetchRequest,
    ResourceScope,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationRequest,
    ToolInvocationResult,
    UiPart,
)
from .model_routing import RoutedChatModelFactory
from .models import ReActAgentDefinition, ToolApprovalPolicy, ToolRefRequirement
from .react_hitl import build_hitl_compiled_react_agent
from .runtime import (
    AgentRuntime,
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    FinalRuntimeEvent,
    HumanInputRequest,
    RuntimeEvent,
    RuntimeServices,
    SpanPort,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
    TracerPort,
)
from .toolset_registry import get_registered_tool_spec


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)


class ReActMessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ReActToolCall(FrozenModel):
    call_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)


class ReActMessage(FrozenModel):
    role: ReActMessageRole
    content: str = Field(..., min_length=0)
    tool_name: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ReActToolCall, ...] = ()

    @model_validator(mode="after")
    def validate_message_shape(self) -> "ReActMessage":
        if self.tool_calls and self.role != ReActMessageRole.ASSISTANT:
            raise ValueError("Only assistant messages may declare tool_calls.")
        if self.tool_call_id is not None and self.role != ReActMessageRole.TOOL:
            raise ValueError("Only tool messages may declare tool_call_id.")
        return self


class ReActInput(FrozenModel):
    """
    Typed chat input accepted by `ReActRuntime`.

    Minimum contract:
    - at least one message
    - at least one user message
    """

    messages: tuple[ReActMessage, ...]

    @model_validator(mode="after")
    def validate_messages(self) -> "ReActInput":
        if not self.messages:
            raise ValueError("ReActInput.messages must contain at least one message.")
        if not any(message.role == ReActMessageRole.USER for message in self.messages):
            raise ValueError(
                "ReActInput.messages must contain at least one user message."
            )
        return self


class ReActOutput(FrozenModel):
    final_message: ReActMessage
    transcript: tuple[ReActMessage, ...]


class _ToolPayloadModel(BaseModel):
    """
    Generic args schema used when no specific schema is registered.

    In practice, tool-specific schemas are preferred when available because they
    produce more reliable model tool-calls.
    """

    payload: dict[str, object] = Field(
        default_factory=dict,
        description="JSON payload forwarded to the platform tool transport.",
    )


def _safe_prompt_token_map(
    binding: BoundRuntimeContext, *, agent_id: str
) -> dict[str, str]:
    response_language = _normalize_response_language(binding.runtime_context.language)
    return {
        "agent_id": agent_id,
        "today": datetime.now(tz=UTC).date().isoformat(),
        "response_language": response_language,
        "session_id": binding.runtime_context.session_id or "",
        "user_id": binding.runtime_context.user_id or "",
    }


class _LiteralFriendlyDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_prompt_template(
    template: str, *, binding: BoundRuntimeContext, agent_id: str
) -> str:
    return template.format_map(
        _LiteralFriendlyDict(_safe_prompt_token_map(binding, agent_id=agent_id))
    )


def _normalize_response_language(language: str | None) -> str:
    if not language:
        return "English"
    normalized = language.strip()
    if not normalized:
        return "English"
    key = normalized.lower().replace("_", "-")
    if key.startswith("fr"):
        return "français"
    if key.startswith("en"):
        return "English"
    return normalized


def _stringify_content(value: object) -> str:
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


def _to_langchain_message(message: ReActMessage) -> BaseMessage:
    if message.role == ReActMessageRole.SYSTEM:
        return SystemMessage(content=message.content)
    if message.role == ReActMessageRole.ASSISTANT:
        return AIMessage(
            content=message.content,
            tool_calls=[
                {
                    "id": tool_call.call_id,
                    "name": _sanitize_tool_name(tool_call.name),
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
                _sanitize_tool_name(message.tool_name)
                if isinstance(message.tool_name, str) and message.tool_name.strip()
                else None
            ),
        )
    return HumanMessage(content=message.content)


def _from_langchain_message(message: BaseMessage) -> ReActMessage:
    if isinstance(message, SystemMessage):
        return ReActMessage(
            role=ReActMessageRole.SYSTEM, content=_stringify_content(message.content)
        )
    if isinstance(message, HumanMessage):
        return ReActMessage(
            role=ReActMessageRole.USER, content=_stringify_content(message.content)
        )
    if isinstance(message, ToolMessage):
        return ReActMessage(
            role=ReActMessageRole.TOOL,
            content=_stringify_content(message.content),
            tool_name=getattr(message, "name", None),
            tool_call_id=getattr(message, "tool_call_id", None),
        )
    return ReActMessage(
        role=ReActMessageRole.ASSISTANT,
        content=_stringify_content(message.content),
        tool_calls=tuple(
            ReActToolCall(
                call_id=str(tool_call.get("id") or ""),
                name=_sanitize_tool_name(str(tool_call.get("name") or "")),
                arguments=cast(dict[str, object], tool_call.get("args") or {}),
            )
            for tool_call in getattr(message, "tool_calls", []) or []
            if str(tool_call.get("id") or "").strip()
            and str(tool_call.get("name") or "").strip()
        ),
    )


def _final_assistant_message(messages: Sequence[BaseMessage]) -> ReActMessage:
    for message in reversed(messages):
        if isinstance(message, AIMessage):
            return _from_langchain_message(message)
    raise RuntimeError("ReAct execution completed without an assistant message.")


def _build_guardrail_suffix(definition: ReActAgentDefinition) -> str:
    guardrails = definition.policy().guardrails
    if not guardrails:
        return ""
    lines = ["", "Operating guardrails:"]
    for guardrail in guardrails:
        lines.append(f"- {guardrail.title}: {guardrail.description}")
    return "\n".join(lines)


def _render_tool_result(result: ToolInvocationResult) -> str:
    rendered_blocks: list[str] = []
    for block in result.blocks:
        if block.kind == ToolContentKind.TEXT and block.text is not None:
            rendered_blocks.append(block.text)
            continue
        if block.kind == ToolContentKind.JSON and block.data is not None:
            rendered_blocks.append(json.dumps(block.data, ensure_ascii=False, indent=2))
            continue
        rendered_blocks.append(_render_fallback_tool_block(block))

    if not rendered_blocks:
        rendered_blocks.append("")

    if result.is_error:
        return "Tool error:\n" + "\n".join(rendered_blocks)
    return "\n".join(rendered_blocks)


def _render_fallback_tool_block(block: ToolContentBlock) -> str:
    if block.text is not None:
        return block.text
    if block.data is not None:
        return json.dumps(block.data, ensure_ascii=False, indent=2)
    return ""


def _extract_messages_from_update(update: object) -> list[BaseMessage]:
    messages: list[BaseMessage] = []
    if isinstance(update, dict):
        raw_messages = update.get("messages")
        if isinstance(raw_messages, list):
            messages.extend(
                message for message in raw_messages if isinstance(message, BaseMessage)
            )
        for value in update.values():
            messages.extend(_extract_messages_from_update(value))
    return messages


def _split_stream_event_mode(raw_event: object) -> tuple[str, object]:
    if (
        isinstance(raw_event, tuple)
        and len(raw_event) == 2
        and isinstance(raw_event[0], str)
    ):
        return raw_event[0], raw_event[1]
    return "updates", raw_event


def _extract_interrupt_request(update: object) -> HumanInputRequest | None:
    if not isinstance(update, dict):
        return None
    key = next(iter(update), None)
    if key not in {"interrupt", "__interrupt__"}:
        return None

    raw_interrupt = update[key]
    payload_obj: object
    checkpoint_id: str | None = None
    if isinstance(raw_interrupt, list):
        if not raw_interrupt:
            raise RuntimeError("Runtime emitted an empty interrupt list.")
        raw_interrupt = raw_interrupt[0]

    if isinstance(raw_interrupt, tuple):
        if len(raw_interrupt) == 2:
            payload_obj = raw_interrupt[0]
            checkpoint_id = getattr(raw_interrupt[1], "id", None) or getattr(
                raw_interrupt[1], "checkpoint_id", None
            )
        elif len(raw_interrupt) == 1:
            first = raw_interrupt[0]
            payload_obj = getattr(first, "value", first)
            checkpoint_id = getattr(first, "id", None) or getattr(
                first, "checkpoint_id", None
            )
        else:
            raise RuntimeError(
                f"Runtime emitted an unsupported interrupt tuple length: {len(raw_interrupt)}."
            )
    elif isinstance(raw_interrupt, dict):
        payload_obj = raw_interrupt.get("value", raw_interrupt)
        raw_checkpoint_id = (
            raw_interrupt.get("checkpoint_id")
            or raw_interrupt.get("id")
            or raw_interrupt.get("interrupt_id")
        )
        if isinstance(raw_checkpoint_id, str) and raw_checkpoint_id.strip():
            checkpoint_id = raw_checkpoint_id
    else:
        payload_obj = getattr(raw_interrupt, "value", raw_interrupt)
        raw_checkpoint_id = getattr(raw_interrupt, "id", None) or getattr(
            raw_interrupt, "checkpoint_id", None
        )
        if isinstance(raw_checkpoint_id, str) and raw_checkpoint_id.strip():
            checkpoint_id = raw_checkpoint_id

    try:
        request = HumanInputRequest.model_validate(payload_obj)
    except ValidationError as exc:
        raise RuntimeError(
            "Runtime emitted an invalid HITL payload. "
            "Expected HumanInputRequest-compatible data."
        ) from exc
    if checkpoint_id is not None:
        request = request.model_copy(update={"checkpoint_id": checkpoint_id})
    return request


def _assistant_delta_from_stream_event(raw_event: object) -> str | None:
    chunk = raw_event[0] if isinstance(raw_event, tuple) and raw_event else raw_event
    if not isinstance(chunk, AIMessageChunk):
        return None
    if chunk.tool_calls or chunk.tool_call_chunks:
        return None
    delta = _stringify_content(chunk.content)
    return delta if delta else None


def _runtime_metadata_from_stream_event(
    raw_event: object,
) -> tuple[str | None, dict[str, int] | None, str | None]:
    chunk = raw_event[0] if isinstance(raw_event, tuple) and raw_event else raw_event
    if not isinstance(chunk, AIMessageChunk):
        return (None, None, None)
    return _runtime_metadata_from_message(chunk)


def _runtime_metadata_from_message(
    message: BaseMessage,
) -> tuple[str | None, dict[str, int] | None, str | None]:
    response_metadata = getattr(message, "response_metadata", {}) or {}
    usage_metadata = getattr(message, "usage_metadata", {}) or {}
    additional_kwargs = getattr(message, "additional_kwargs", {}) or {}

    model_name = None
    if isinstance(response_metadata, dict):
        raw_model_name = response_metadata.get("model_name") or response_metadata.get(
            "model"
        )
        if isinstance(raw_model_name, str) and raw_model_name.strip():
            model_name = raw_model_name

    finish_reason = None
    if isinstance(response_metadata, dict):
        raw_finish_reason = response_metadata.get("finish_reason")
        if raw_finish_reason is not None:
            finish_reason = str(raw_finish_reason)

    token_usage = (
        _normalize_token_usage(usage_metadata)
        or _normalize_token_usage(
            response_metadata.get("usage_metadata")
            if isinstance(response_metadata, dict)
            else None
        )
        or _normalize_token_usage(
            response_metadata.get("token_usage")
            if isinstance(response_metadata, dict)
            else None
        )
        or _normalize_token_usage(
            response_metadata.get("usage")
            if isinstance(response_metadata, dict)
            else None
        )
        or _normalize_token_usage(
            additional_kwargs.get("token_usage")
            if isinstance(additional_kwargs, dict)
            else None
        )
        or _normalize_token_usage(
            additional_kwargs.get("usage")
            if isinstance(additional_kwargs, dict)
            else None
        )
    )

    return (model_name, token_usage, finish_reason)


def _normalize_token_usage(raw: object) -> dict[str, int] | None:
    if not isinstance(raw, dict) or not raw:
        return None

    usage = raw
    nested_usage = usage.get("usage")
    if isinstance(nested_usage, dict):
        usage = nested_usage

    def _to_int(value: object) -> int:
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if not isinstance(value, (float, str)):
            return 0
        try:
            return int(value)
        except Exception:
            return 0

    input_raw = usage.get("input_tokens")
    if input_raw is None:
        input_raw = usage.get("prompt_tokens")
    if input_raw is None:
        input_raw = usage.get("prompt_tokens_total")
    if input_raw is None:
        input_raw = usage.get("input_token_count")
    if input_raw is None:
        input_raw = usage.get("prompt_eval_count")

    output_raw = usage.get("output_tokens")
    if output_raw is None:
        output_raw = usage.get("completion_tokens")
    if output_raw is None:
        output_raw = usage.get("completion_tokens_total")
    if output_raw is None:
        output_raw = usage.get("output_token_count")
    if output_raw is None:
        output_raw = usage.get("eval_count")

    total_raw = usage.get("total_tokens")
    if total_raw is None:
        total_raw = usage.get("token_count")

    has_any = any(
        usage.get(key) is not None
        for key in (
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "prompt_tokens_total",
            "completion_tokens_total",
            "input_token_count",
            "output_token_count",
            "prompt_eval_count",
            "eval_count",
            "token_count",
        )
    )
    if not has_any:
        return None

    input_tokens = _to_int(input_raw)
    output_tokens = _to_int(output_raw)
    total_tokens = _to_int(total_raw)
    if total_raw is None:
        total_tokens = input_tokens + output_tokens

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _normalize_tool_artifact(artifact: object) -> ToolInvocationResult | None:
    if artifact is None:
        return None
    if isinstance(artifact, ToolInvocationResult):
        return artifact
    try:
        return ToolInvocationResult.model_validate(artifact)
    except ValidationError as exc:
        raise RuntimeError(
            "Tool runtime produced an invalid artifact. "
            "Expected ToolInvocationResult-compatible data."
        ) from exc


def _merge_sources(
    existing: tuple[VectorSearchHit, ...], new_sources: tuple[VectorSearchHit, ...]
) -> tuple[VectorSearchHit, ...]:
    if not new_sources:
        return existing

    merged = list(existing)
    seen = {
        (source.uid, source.rank, source.content, source.title) for source in existing
    }
    for source in new_sources:
        key = (source.uid, source.rank, source.content, source.title)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return tuple(merged)


def _merge_ui_parts(
    existing: tuple[UiPart, ...], new_parts: tuple[UiPart, ...]
) -> tuple[UiPart, ...]:
    if not new_parts:
        return existing

    merged = list(existing)
    seen = {
        json.dumps(part.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)
        for part in existing
    }
    for part in new_parts:
        key = json.dumps(
            part.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(part)
    return tuple(merged)


@dataclass(frozen=True, slots=True)
class _BoundTool:
    runtime_name: str
    description: str
    tool: BaseTool


class _CompiledReActAgent(Protocol):
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


class _TransportBackedReActExecutor(Executor[ReActInput, ReActOutput]):
    """
    Executes one ReAct run against the compiled LangChain/LangGraph agent.

    This class is responsible for runtime event emission. When streaming output
    looks wrong in UI, debug here first.
    """

    def __init__(
        self,
        *,
        compiled_agent: _CompiledReActAgent,
        binding: BoundRuntimeContext,
        services: RuntimeServices,
    ) -> None:
        self._compiled_agent = compiled_agent
        self._binding = binding
        self._services = services

    async def invoke(
        self, input_model: ReActInput, config: ExecutionConfig
    ) -> ReActOutput:
        span = None
        if self._services.tracer is not None:
            span = self._services.tracer.start_span(
                name="agent.invoke",
                context=self._binding.portable_context,
                attributes={"agent_id": self._binding.portable_context.agent_id or ""},
            )
        try:
            result = await self._compiled_agent.ainvoke(
                _graph_input(input_model, config),
                config=_to_runnable_config(config),
            )
            transcript = tuple(
                _from_langchain_message(message)
                for message in result["messages"]
                if isinstance(message, BaseMessage)
            )
            final_message = _final_assistant_message(result["messages"])
            return ReActOutput(final_message=final_message, transcript=transcript)
        finally:
            if span is not None:
                span.end()

    async def stream(
        self, input_model: ReActInput, config: ExecutionConfig
    ) -> AsyncIterator[RuntimeEvent]:
        span = None
        if self._services.tracer is not None:
            span = self._services.tracer.start_span(
                name="agent.stream",
                context=self._binding.portable_context,
                attributes={"agent_id": self._binding.portable_context.agent_id or ""},
            )

        sequence = 0
        last_assistant_message: ReActMessage | None = None
        collected_sources: tuple[VectorSearchHit, ...] = ()
        collected_ui_parts: tuple[UiPart, ...] = ()
        last_model_name: str | None = None
        last_token_usage: dict[str, int] | None = None
        last_finish_reason: str | None = None
        try:
            async for raw_event in self._compiled_agent.astream(
                _graph_input(input_model, config),
                config=_to_runnable_config(config),
                stream_mode=["messages", "updates"],
            ):
                mode, update = _split_stream_event_mode(raw_event)

                if mode == "messages":
                    model_name, token_usage, finish_reason = (
                        _runtime_metadata_from_stream_event(update)
                    )
                    if model_name is not None:
                        last_model_name = model_name
                    if token_usage is not None:
                        last_token_usage = token_usage
                    if finish_reason is not None:
                        last_finish_reason = finish_reason
                    delta = _assistant_delta_from_stream_event(update)
                    if delta is not None:
                        yield AssistantDeltaRuntimeEvent(
                            sequence=sequence,
                            delta=delta,
                        )
                        sequence += 1
                    continue

                if mode != "updates":
                    continue

                interrupt_request = _extract_interrupt_request(update)
                if interrupt_request is not None:
                    yield AwaitingHumanRuntimeEvent(
                        sequence=sequence,
                        request=interrupt_request,
                    )
                    sequence += 1
                    continue

                for message in _extract_messages_from_update(update):
                    if isinstance(message, ToolMessage):
                        artifact = _normalize_tool_artifact(message.artifact)
                        sources = artifact.sources if artifact is not None else ()
                        ui_parts = artifact.ui_parts if artifact is not None else ()
                        collected_sources = _merge_sources(collected_sources, sources)
                        collected_ui_parts = _merge_ui_parts(
                            collected_ui_parts, ui_parts
                        )
                        yield ToolResultRuntimeEvent(
                            sequence=sequence,
                            call_id=message.tool_call_id,
                            content=_stringify_content(message.content),
                            tool_name=message.name,
                            is_error=artifact.is_error
                            if artifact is not None
                            else False,
                            sources=sources,
                            ui_parts=ui_parts,
                        )
                        sequence += 1
                        continue

                    if isinstance(message, AIMessage) and message.tool_calls:
                        for tool_call in message.tool_calls:
                            yield ToolCallRuntimeEvent(
                                sequence=sequence,
                                tool_name=str(tool_call.get("name") or ""),
                                call_id=str(tool_call.get("id") or ""),
                                arguments=cast(
                                    dict[str, object], tool_call.get("args") or {}
                                ),
                            )
                            sequence += 1
                        continue

                    if isinstance(message, AIMessage):
                        model_name, token_usage, finish_reason = (
                            _runtime_metadata_from_message(message)
                        )
                        if model_name is not None:
                            last_model_name = model_name
                        if token_usage is not None:
                            last_token_usage = token_usage
                        if finish_reason is not None:
                            last_finish_reason = finish_reason
                        last_assistant_message = _from_langchain_message(message)

            if last_assistant_message is not None:
                yield FinalRuntimeEvent(
                    sequence=sequence,
                    content=last_assistant_message.content,
                    sources=collected_sources,
                    ui_parts=collected_ui_parts,
                    model_name=last_model_name,
                    token_usage=last_token_usage,
                    finish_reason=last_finish_reason,
                )
        finally:
            if span is not None:
                span.end()


def _to_runnable_config(config: ExecutionConfig) -> Mapping[str, object] | None:
    merged: dict[str, object] = dict(config.runnable_config)
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


def _graph_input(
    input_model: ReActInput, config: ExecutionConfig
) -> Mapping[str, object] | Command:
    if config.resume_payload is not None:
        return Command(resume=config.resume_payload)
    return {
        "messages": [_to_langchain_message(message) for message in input_model.messages]
    }


class ReActRuntime(AgentRuntime[ReActAgentDefinition, ReActInput, ReActOutput]):
    """
    Runtime implementation for `ReActAgentDefinition`.

    Where to look when customizing behavior:
    - tool wiring: `build_executor(...)` and `_create_compiled_react_agent(...)`
    - streaming/final event shape: `_TransportBackedReActExecutor`
    - bind/activation logic: `on_bind(...)` and `on_activate(...)`
    """

    def __init__(self, *, definition: ReActAgentDefinition, services: RuntimeServices):
        super().__init__(definition=definition, services=services)
        self._model: BaseChatModel | None = None

    def on_bind(self, binding: BoundRuntimeContext) -> None:
        if self.services.tool_provider is not None:
            self.services.tool_provider.bind(binding)
        if self.services.artifact_publisher is not None:
            self.services.artifact_publisher.bind(binding)
        if self.services.resource_reader is not None:
            self.services.resource_reader.bind(binding)

    async def on_activate(self, binding: BoundRuntimeContext) -> None:
        if self.services.chat_model_factory is None:
            raise RuntimeError(
                "ReActRuntime requires RuntimeServices.chat_model_factory."
            )
        self._model = self.services.chat_model_factory.build(self.definition, binding)
        if self.services.tool_provider is not None:
            await self.services.tool_provider.activate()

    async def build_executor(
        self, binding: BoundRuntimeContext
    ) -> Executor[ReActInput, ReActOutput]:
        if self._model is None:
            raise RuntimeError("ReActRuntime model is not initialized.")

        policy = self.definition.policy()
        if policy.tool_selection.max_tool_calls_per_turn is not None:
            raise NotImplementedError(
                "Per-turn tool-call limits are not enforced by the first v2 ReAct runtime yet."
            )

        bound_tools = self._build_tools(binding)
        system_prompt = _render_prompt_template(
            policy.system_prompt_template or "",
            binding=binding,
            agent_id=self.definition.agent_id,
        )
        system_prompt = (
            f"{system_prompt}"
            f"{_build_runtime_tool_prompt_suffix(bound_tools)}"
            f"{_build_guardrail_suffix(self.definition)}"
        )

        compiled_agent = _create_compiled_react_agent(
            model=self._model,
            tools=[bound_tool.tool for bound_tool in bound_tools],
            system_prompt=system_prompt,
            binding=binding,
            approval_policy=policy.tool_approval,
            checkpointer=self.services.checkpointer,
            tracer=self.services.tracer,
            chat_model_factory=self.services.chat_model_factory,
            definition=self.definition,
        )
        return _TransportBackedReActExecutor(
            compiled_agent=compiled_agent,
            binding=binding,
            services=self.services,
        )

    async def on_dispose(self) -> None:
        if self.services.tool_provider is not None:
            await self.services.tool_provider.aclose()
        self._model = None

    def _tool_ref_requirements(self) -> tuple[ToolRefRequirement, ...]:
        tool_requirements: list[ToolRefRequirement] = []
        for requirement in self.definition.tool_requirements:
            if isinstance(requirement, ToolRefRequirement):
                tool_requirements.append(requirement)
                continue
            raise NotImplementedError(
                "Capability-based tool requirements are not executable yet in the first v2 runtime. "
                "Use explicit tool_ref requirements for now."
            )
        return tuple(tool_requirements)

    def _toolset_key(self) -> str | None:
        raw = getattr(self.definition, "toolset_key", None)
        if not isinstance(raw, str):
            return None
        cleaned = raw.strip()
        return cleaned or None

    def _build_tools(self, binding: BoundRuntimeContext) -> list[_BoundTool]:
        tools: list[_BoundTool] = []
        used_names: set[str] = set()
        tools.extend(
            self._build_declared_tools(
                binding=binding,
                used_names=used_names,
            )
        )
        tools.extend(self._build_runtime_provider_tools(used_names=used_names))
        return tools

    def _build_declared_tools(
        self,
        *,
        binding: BoundRuntimeContext,
        used_names: set[str],
    ) -> list[_BoundTool]:
        requirements = self._tool_ref_requirements()
        if not requirements:
            return []

        tool_invoker = self.services.tool_invoker
        tools: list[_BoundTool] = []
        for requirement in requirements:
            base_name = _sanitize_tool_name(requirement.tool_ref)
            registered_spec = get_registered_tool_spec(
                toolset_key=self._toolset_key(),
                tool_ref=requirement.tool_ref,
            )
            if registered_spec is not None and registered_spec.runtime_name:
                base_name = _sanitize_tool_name(registered_spec.runtime_name)
            tool_name = base_name
            suffix = 2
            while tool_name in used_names:
                tool_name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(tool_name)

            builtin_spec = get_builtin_tool_spec(requirement.tool_ref)
            if builtin_spec is not None:
                description = (
                    requirement.description
                    or builtin_spec.default_description
                    or f"Platform-routed tool {requirement.tool_ref}."
                )

                if builtin_spec.backend == BuiltinToolBackend.TOOL_INVOKER:
                    if tool_invoker is None:
                        raise RuntimeError(
                            f"ReActRuntime requires RuntimeServices.tool_invoker for {requirement.tool_ref}."
                        )

                    async def _invoke_builtin_tool(
                        *,
                        tool_ref: str = requirement.tool_ref,
                        tool_name_for_span: str = tool_name,
                        **payload: object,
                    ) -> tuple[str, ToolInvocationResult]:
                        span = None
                        if self.services.tracer is not None:
                            span = self.services.tracer.start_span(
                                name="tool.invoke",
                                context=binding.portable_context,
                                attributes={
                                    "tool_name": tool_name_for_span,
                                    "tool_ref": tool_ref,
                                },
                            )
                        try:
                            result = await tool_invoker.invoke(
                                ToolInvocationRequest(
                                    tool_ref=tool_ref,
                                    payload=cast(
                                        dict[str, object],
                                        _normalize_payload(dict(payload)),
                                    ),
                                    context=binding.portable_context,
                                )
                            )
                            return (_render_tool_result(result), result)
                        finally:
                            if span is not None:
                                span.end()

                    tools.append(
                        _BoundTool(
                            runtime_name=tool_name,
                            description=description,
                            tool=StructuredTool.from_function(
                                func=None,
                                coroutine=_invoke_builtin_tool,
                                name=tool_name,
                                description=description,
                                args_schema=builtin_spec.args_schema,
                                response_format="content_and_artifact",
                            ),
                        )
                    )
                    continue

                if builtin_spec.backend == BuiltinToolBackend.ARTIFACT_PUBLISHER:
                    artifact_publisher = self.services.artifact_publisher
                    if artifact_publisher is None:
                        raise RuntimeError(
                            "ReActRuntime requires RuntimeServices.artifact_publisher for artifacts.publish_text."
                        )
                    publisher = artifact_publisher

                    async def _invoke_artifact_publish_text(
                        file_name: str,
                        content: str,
                        title: str | None = None,
                        content_type: str = "text/plain; charset=utf-8",
                        key: str | None = None,
                        *,
                        tool_ref: str = requirement.tool_ref,
                        tool_name_for_span: str = tool_name,
                    ) -> tuple[str, ToolInvocationResult]:
                        span = None
                        if self.services.tracer is not None:
                            span = self.services.tracer.start_span(
                                name="artifact.publish",
                                context=binding.portable_context,
                                attributes={
                                    "tool_name": tool_name_for_span,
                                    "artifact_file_name": file_name,
                                },
                            )
                        try:
                            artifact = await publisher.publish(
                                ArtifactPublishRequest(
                                    file_name=file_name,
                                    content_bytes=content.encode("utf-8"),
                                    key=key,
                                    content_type=content_type,
                                    title=title,
                                )
                            )
                            link_part = artifact.to_link_part()
                            result = ToolInvocationResult(
                                tool_ref=tool_ref,
                                blocks=(
                                    ToolContentBlock(
                                        kind=ToolContentKind.TEXT,
                                        text=f"Published {artifact.file_name} for the user.",
                                    ),
                                ),
                                ui_parts=(link_part,),
                            )
                            return (_render_tool_result(result), result)
                        finally:
                            if span is not None:
                                span.end()

                    tools.append(
                        _BoundTool(
                            runtime_name=tool_name,
                            description=description,
                            tool=StructuredTool.from_function(
                                func=None,
                                coroutine=_invoke_artifact_publish_text,
                                name=tool_name,
                                description=description,
                                args_schema=builtin_spec.args_schema,
                                response_format="content_and_artifact",
                            ),
                        )
                    )
                    continue

                if builtin_spec.backend == BuiltinToolBackend.RESOURCE_READER:
                    resource_reader = self.services.resource_reader
                    if resource_reader is None:
                        raise RuntimeError(
                            "ReActRuntime requires RuntimeServices.resource_reader for resources.fetch_text."
                        )
                    reader = resource_reader

                    async def _invoke_resource_fetch_text(
                        key: str,
                        scope: object,
                        target_user_id: str | None = None,
                        *,
                        tool_ref: str = requirement.tool_ref,
                        tool_name_for_span: str = tool_name,
                    ) -> tuple[str, ToolInvocationResult]:
                        if not isinstance(scope, ResourceScope):
                            raise RuntimeError(
                                "resources.fetch_text received an invalid scope."
                            )
                        span = None
                        if self.services.tracer is not None:
                            span = self.services.tracer.start_span(
                                name="resource.fetch",
                                context=binding.portable_context,
                                attributes={
                                    "tool_name": tool_name_for_span,
                                    "resource_key": key,
                                    "resource_scope": scope.value,
                                },
                            )
                        try:
                            resource = await reader.fetch(
                                ResourceFetchRequest(
                                    key=key,
                                    scope=scope,
                                    target_user_id=target_user_id,
                                )
                            )
                            result = ToolInvocationResult(
                                tool_ref=tool_ref,
                                blocks=(
                                    ToolContentBlock(
                                        kind=ToolContentKind.TEXT,
                                        text=resource.as_text(),
                                    ),
                                ),
                            )
                            return (_render_tool_result(result), result)
                        finally:
                            if span is not None:
                                span.end()

                    tools.append(
                        _BoundTool(
                            runtime_name=tool_name,
                            description=description,
                            tool=StructuredTool.from_function(
                                func=None,
                                coroutine=_invoke_resource_fetch_text,
                                name=tool_name,
                                description=description,
                                args_schema=builtin_spec.args_schema,
                                response_format="content_and_artifact",
                            ),
                        )
                    )
                    continue

            if registered_spec is not None:
                if tool_invoker is None:
                    raise RuntimeError(
                        "ReActRuntime requires RuntimeServices.tool_invoker for registered declared tools."
                    )

                async def _invoke_registered_tool(
                    *,
                    tool_ref: str = requirement.tool_ref,
                    tool_name_for_span: str = tool_name,
                    **payload: object,
                ) -> tuple[str, ToolInvocationResult]:
                    span = None
                    if self.services.tracer is not None:
                        span = self.services.tracer.start_span(
                            name="tool.invoke",
                            context=binding.portable_context,
                            attributes={
                                "tool_name": tool_name_for_span,
                                "tool_ref": tool_ref,
                            },
                        )
                    try:
                        result = await tool_invoker.invoke(
                            ToolInvocationRequest(
                                tool_ref=tool_ref,
                                payload=dict(payload),
                                context=binding.portable_context,
                            )
                        )
                        return (_render_tool_result(result), result)
                    finally:
                        if span is not None:
                            span.end()

                tools.append(
                    _BoundTool(
                        runtime_name=tool_name,
                        description=requirement.description
                        or registered_spec.description
                        or f"Platform-routed tool {requirement.tool_ref}.",
                        tool=StructuredTool.from_function(
                            func=None,
                            coroutine=_invoke_registered_tool,
                            name=tool_name,
                            description=requirement.description
                            or registered_spec.description
                            or f"Platform-routed tool {requirement.tool_ref}.",
                            args_schema=registered_spec.args_schema,
                            response_format="content_and_artifact",
                        ),
                    )
                )
                continue

            if tool_invoker is None:
                raise RuntimeError(
                    "ReActRuntime requires RuntimeServices.tool_invoker for transport-routed declared tools."
                )

            async def _invoke_tool(
                payload: dict[str, object],
                *,
                tool_ref: str = requirement.tool_ref,
                tool_name_for_span: str = tool_name,
            ) -> tuple[str, ToolInvocationResult]:
                span = None
                if self.services.tracer is not None:
                    span = self.services.tracer.start_span(
                        name="tool.invoke",
                        context=binding.portable_context,
                        attributes={
                            "tool_name": tool_name_for_span,
                            "tool_ref": tool_ref,
                        },
                    )
                try:
                    result = await tool_invoker.invoke(
                        ToolInvocationRequest(
                            tool_ref=tool_ref,
                            payload=payload,
                            context=binding.portable_context,
                        )
                    )
                    return (_render_tool_result(result), result)
                finally:
                    if span is not None:
                        span.end()

            tools.append(
                _BoundTool(
                    runtime_name=tool_name,
                    description=requirement.description
                    or f"Platform-routed tool {requirement.tool_ref}.",
                    tool=StructuredTool.from_function(
                        func=None,
                        coroutine=_invoke_tool,
                        name=tool_name,
                        description=requirement.description
                        or f"Platform-routed tool {requirement.tool_ref}.",
                        args_schema=_ToolPayloadModel,
                        response_format="content_and_artifact",
                    ),
                )
            )
        return tools

    def _build_runtime_provider_tools(
        self, *, used_names: set[str]
    ) -> list[_BoundTool]:
        tool_provider = self.services.tool_provider
        if tool_provider is None:
            return []

        tools: list[_BoundTool] = []
        for runtime_tool in tool_provider.get_tools():
            tool_name = runtime_tool.name.strip()
            if not tool_name:
                raise RuntimeError(
                    "Runtime-provided tool has an empty name. "
                    "Provider tools must expose a non-empty unique name."
                )
            if tool_name in used_names:
                raise RuntimeError(
                    f"Duplicate tool name {tool_name!r} detected across declared and runtime-provided tools. "
                    "Tool names must be unique in one ReAct runtime."
                )
            used_names.add(tool_name)
            description = runtime_tool.description.strip() or "No description provided."

            async def _invoke_runtime_provider_tool(
                *,
                _tool: BaseTool = runtime_tool,
                _tool_name: str = tool_name,
                **payload: object,
            ) -> str:
                span = None
                if self.services.tracer is not None:
                    span = self.services.tracer.start_span(
                        name="v2.graph.runtime_tool",
                        context=self.binding.portable_context,
                        attributes={
                            "tool_name": _tool_name,
                            "tool_ref": _tool_name,
                        },
                    )
                try:
                    raw_result = await _tool.ainvoke(
                        cast(dict[str, object], _normalize_payload(dict(payload)))
                    )
                    if isinstance(raw_result, ToolInvocationResult):
                        result = _render_tool_result(raw_result)
                    elif isinstance(raw_result, tuple) and len(raw_result) == 2:
                        rendered_content = _stringify_content(raw_result[0]).strip()
                        artifact = _normalize_tool_artifact(raw_result[1])
                        if rendered_content:
                            result = rendered_content
                        elif artifact is not None:
                            result = _render_tool_result(artifact)
                        else:
                            result = _stringify_content(raw_result[0])
                    elif isinstance(raw_result, dict):
                        result = json.dumps(raw_result, ensure_ascii=False, indent=2)
                    else:
                        result = _stringify_content(raw_result)
                    if span is not None:
                        span.set_attribute("status", "ok")
                    return result
                except Exception:
                    if span is not None:
                        span.set_attribute("status", "error")
                    raise
                finally:
                    if span is not None:
                        span.end()

            args_schema = getattr(runtime_tool, "args_schema", None)
            tools.append(
                _BoundTool(
                    runtime_name=tool_name,
                    description=description,
                    tool=StructuredTool.from_function(
                        func=None,
                        coroutine=_invoke_runtime_provider_tool,
                        name=tool_name,
                        description=description,
                        args_schema=args_schema,
                    ),
                )
            )
        return tools


def _normalize_payload(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {
            str(key): cast(object, _normalize_payload(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [cast(object, _normalize_payload(item)) for item in value]
    if isinstance(value, tuple):
        return [cast(object, _normalize_payload(item)) for item in value]
    return value


def _sanitize_tool_name(tool_ref: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in tool_ref.strip().lower())
    cleaned = cleaned.strip("_")
    if not cleaned:
        cleaned = "tool"
    if cleaned[0].isdigit():
        cleaned = f"tool_{cleaned}"
    return cleaned


def _build_runtime_tool_prompt_suffix(bound_tools: Sequence[_BoundTool]) -> str:
    if not bound_tools:
        return (
            "\n\nTool availability:\n"
            "- No external tool is available in this session.\n"
            "- Do not claim any search, database lookup, or API call unless it actually happened.\n"
            "- Answer directly without repeating capability disclaimers.\n"
        )

    lines = [
        "\n\nAvailable tools (exact names):",
    ]
    for bound_tool in bound_tools:
        lines.append(f"- {bound_tool.runtime_name}: {bound_tool.description}")
    lines.extend(
        [
            "Tool calling rules:",
            "- Use only the tools listed above.",
            "- Follow each tool's JSON argument schema exactly.",
            "- Never invent tool names or tool results.",
        ]
    )
    return "\n".join(lines)


_TRACE_MODEL_SPAN_NAME = "v2.react.model"
_REACT_MODEL_OPERATION_ROUTING = "routing"
_REACT_MODEL_OPERATION_PLANNING = "planning"


def _extract_model_name_from_message(message: BaseMessage | object) -> str | None:
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


def _extract_model_name_from_object(value: object) -> str | None:
    if isinstance(value, BaseChatModel):
        for attr in ("model_name", "model", "model_id"):
            raw = getattr(value, attr, None)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _extract_model_name_from_model_response(response: object) -> str | None:
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


def _infer_react_model_operation_from_messages(
    messages: Sequence[object],
) -> str:
    """
    Why this function exists:
    - infer ReAct phase for model routing from current message history

    Who calls it:
    - `_ReActDynamicModelRoutingMiddleware`
    - HITL `model_resolver` callback (`_model_for_state`)
    - tracing middleware (operation attribute)

    When it is called:
    - before each model call that uses dynamic routing/tracing metadata

    Expected inputs / invariants:
    - `messages` is a chronological conversation list (oldest -> newest)

    Return / side effects:
    - returns `"planning"` when the latest relevant message is a `ToolMessage`
    - returns `"routing"` when the latest relevant message is a `HumanMessage`
    - defaults to `"routing"` when nothing is inferable
    - no side effects

    Fallback / errors:
    - never raises (best-effort inference)

    Observability signals to look at:
    - value is propagated into model routing (`operation`) and tracing span
      attribute `operation` (`v2.react.model`)
    """
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            return _REACT_MODEL_OPERATION_PLANNING
        if isinstance(message, HumanMessage):
            return _REACT_MODEL_OPERATION_ROUTING
    return _REACT_MODEL_OPERATION_ROUTING


_ReActDynamicModelRoutingMiddleware: type[Any] | None = None
_ReActModelTracingMiddleware: type[Any] | None = None

if _LangchainAgentMiddleware is not None:  # pragma: no branch

    class _ReActDynamicModelRoutingMiddlewareImpl(_LangchainAgentMiddleware):  # type: ignore[misc]
        """
        Why this class exists:
        - apply model-routing policy at each ReAct model call without changing
          agent definition code

        Who instantiates it:
        - `_react_model_middlewares(...)` when:
          - LangChain middleware API is available
          - chat factory is `RoutedChatModelFactory`

        When it is executed:
        - on every model call passing through LangChain agent middleware
          (`wrap_model_call` / `awrap_model_call`)

        Expected inputs / invariants:
        - request object provides `messages` and `override(model=...)`
        - routed factory can resolve `purpose="chat"` with operation
          (`routing` or `planning`)

        Return / side effects:
        - returns underlying model handler response unchanged
        - side effect: swaps request model dynamically before handler call
        - caches resolved models per operation in `_models_by_operation`
          (avoids rebuilding model object repeatedly in same runtime)

        Fallback / errors:
        - if request messages are malformed, falls back to `routing` operation
        - routing/provider errors propagate

        Observability signals to look at:
        - routing decision logs from `RoutedChatModelFactory.build_for_chat`
          with prefix `[V2][MODEL_ROUTING]`
        """

        def __init__(
            self,
            *,
            routed_factory: RoutedChatModelFactory,
            definition: ReActAgentDefinition,
            binding: BoundRuntimeContext,
        ) -> None:
            super().__init__()
            self._routed_factory = routed_factory
            self._definition = definition
            self._binding = binding
            self._models_by_operation: dict[str, BaseChatModel] = {}

        def _operation_from_request(self, request: object) -> str:
            raw_messages = getattr(request, "messages", [])
            if not isinstance(raw_messages, list):
                return _REACT_MODEL_OPERATION_ROUTING
            return _infer_react_model_operation_from_messages(raw_messages)

        def _resolved_model(self, *, operation: str) -> BaseChatModel:
            cached = self._models_by_operation.get(operation)
            if cached is not None:
                return cached
            model, _ = self._routed_factory.build_for_chat(
                definition=self._definition,
                binding=self._binding,
                purpose="chat",
                operation=operation,
            )
            self._models_by_operation[operation] = model
            return model

        def wrap_model_call(self, request, handler):  # type: ignore[override]
            operation = self._operation_from_request(request)
            request = request.override(model=self._resolved_model(operation=operation))
            return handler(request)

        async def awrap_model_call(self, request, handler):  # type: ignore[override]
            operation = self._operation_from_request(request)
            request = request.override(model=self._resolved_model(operation=operation))
            return await handler(request)

    class _ReActModelTracingMiddlewareImpl(_LangchainAgentMiddleware):  # type: ignore[misc]
        """
        Runtime middleware that traces each ReAct model call as a child span.

        This keeps model latency visible even when the underlying LangChain
        execution graph does not emit granular node spans by default.
        """

        def __init__(
            self, *, tracer: TracerPort | None, binding: BoundRuntimeContext
        ) -> None:
            super().__init__()
            self._tracer = tracer
            self._binding = binding

        def _start_span(self, request: object):
            if self._tracer is None:
                return None
            request_messages = getattr(request, "messages", [])
            operation = (
                _infer_react_model_operation_from_messages(request_messages)
                if isinstance(request_messages, list)
                else _REACT_MODEL_OPERATION_ROUTING
            )
            attributes: dict[str, object] = {"operation": operation}
            request_model = getattr(request, "model", None)
            request_model_name = _extract_model_name_from_object(request_model)
            if request_model_name is not None:
                attributes["model_name"] = request_model_name
            return self._tracer.start_span(
                name=_TRACE_MODEL_SPAN_NAME,
                context=self._binding.portable_context,
                attributes=cast(dict[str, str | int | float | bool | None], attributes),
            )

        @staticmethod
        def _mark_ok(span: object, response: object) -> None:
            span_port = cast(SpanPort, span)
            span_port.set_attribute("status", "ok")
            model_name = _extract_model_name_from_model_response(response)
            if model_name is not None:
                span_port.set_attribute("model_name", model_name)

        def wrap_model_call(self, request, handler):  # type: ignore[override]
            span = self._start_span(request)
            try:
                response = handler(request)
                if span is not None:
                    self._mark_ok(span, response)
                return response
            except Exception:
                if span is not None:
                    cast(SpanPort, span).set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    cast(SpanPort, span).end()

        async def awrap_model_call(self, request, handler):  # type: ignore[override]
            span = self._start_span(request)
            try:
                response = await handler(request)
                if span is not None:
                    self._mark_ok(span, response)
                return response
            except Exception:
                if span is not None:
                    cast(SpanPort, span).set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    cast(SpanPort, span).end()

    _ReActDynamicModelRoutingMiddleware = _ReActDynamicModelRoutingMiddlewareImpl
    _ReActModelTracingMiddleware = _ReActModelTracingMiddlewareImpl


def _react_model_middlewares(
    *,
    tracer: TracerPort | None,
    binding: BoundRuntimeContext,
    chat_model_factory: object | None,
    definition: ReActAgentDefinition,
) -> Sequence[object]:
    """
    Build middleware stack for ReAct model calls.

    Why this exists:
    - keep middleware activation rules centralized and explicit

    Who calls it:
    - `_create_compiled_react_agent(...)` in LangChain `create_agent` path

    When it is called:
    - once when compiled agent is created

    Expected inputs / invariants:
    - `chat_model_factory` may or may not be routed
    - tracing is optional

    Return / side effects:
    - returns immutable tuple of middleware instances (possibly empty)
    - no side effects

    Fallback / errors:
    - no dynamic routing middleware when LangChain middleware API is unavailable
      or factory is not routed
    - tracing middleware omitted when tracer is absent

    Observability signals to look at:
    - when routing middleware is active, model selection logs appear with
      `[V2][MODEL_ROUTING]`
    - when tracing middleware is active, child span `v2.react.model` is emitted
    """
    middleware: list[object] = []
    if _ReActDynamicModelRoutingMiddleware is not None and isinstance(
        chat_model_factory, RoutedChatModelFactory
    ):
        middleware.append(
            _ReActDynamicModelRoutingMiddleware(
                routed_factory=chat_model_factory,
                definition=definition,
                binding=binding,
            )
        )
    if tracer is not None and _ReActModelTracingMiddleware is not None:
        middleware.append(_ReActModelTracingMiddleware(tracer=tracer, binding=binding))
    return tuple(middleware)


def _create_compiled_react_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    binding: BoundRuntimeContext,
    approval_policy: ToolApprovalPolicy,
    checkpointer: Checkpointer,
    tracer: TracerPort | None,
    chat_model_factory: object | None,
    definition: ReActAgentDefinition,
) -> _CompiledReActAgent:
    """
    Create the compiled ReAct agent implementation used at runtime.

    Why this exists:
    - isolate runtime construction differences between:
      - HITL tool-loop path
      - plain ReAct path (LangGraph/LangChain agent factory)

    Who calls it:
    - `ReActRuntime.build_executor(...)` during runtime build

    When it is called:
    - once per fresh runtime instance

    Expected inputs / invariants:
    - `model` is a base chat model already selected by runtime factory
    - `tools` are validated and ready to bind
    - `checkpointer` is available for resumability

    Return / side effects:
    - returns one compiled agent implementing `_CompiledReActAgent`
    - no immediate side effects beyond graph/agent object construction

    Fallback / errors:
    - HITL enabled -> force `build_tool_loop` path
    - HITL disabled and LangGraph helper available -> use it
    - else fallback to LangChain `create_agent`
    - construction errors propagate

    Observability signals to look at:
    - dynamic routing path: `[V2][MODEL_ROUTING]` logs
    - tracing middleware path: `v2.react.model` spans
    """
    if approval_policy.enabled:
        return cast(
            _CompiledReActAgent,
            build_hitl_compiled_react_agent(
                model=model,
                tools=tools,
                system_prompt=system_prompt,
                binding=binding,
                approval_policy=approval_policy,
                checkpointer=checkpointer,
                chat_model_factory=chat_model_factory,
                definition=definition,
                infer_operation_from_messages=_infer_react_model_operation_from_messages,
                default_operation=_REACT_MODEL_OPERATION_ROUTING,
            ),
        )

    if _langgraph_create_react_agent is not None:
        return cast(
            _CompiledReActAgent,
            _langgraph_create_react_agent(
                model=model,
                tools=tools,
                prompt=system_prompt,
                checkpointer=checkpointer,
            ),
        )
    return cast(
        _CompiledReActAgent,
        _langchain_create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            middleware=cast(
                Sequence[Any],
                _react_model_middlewares(
                    tracer=tracer,
                    binding=binding,
                    chat_model_factory=chat_model_factory,
                    definition=definition,
                ),
            ),
            checkpointer=checkpointer,
        ),
    )
