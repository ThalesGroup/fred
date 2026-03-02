"""
Concrete v2 runtime for ReAct-style agents.

Why this file exists:
- It gives the v2 contract one real, runnable execution category instead of
  leaving the new API as a pure specification exercise.
- It keeps agent definitions declarative: prompts and tool requirements stay on
  the definition side, while model resolution and tool transport stay platform-
  owned runtime capabilities.
- It uses the same capability seams that a broader GenAI SDK would expect:
  model provisioning, tracing, and transport-agnostic tool invocation.

What this file intentionally does not do:
- It does not assume MCP directly.
- It does not introduce a second lifecycle surface for agent authors.
- It does not try to solve every future ReAct feature (approvals, registry
  resolution, advanced memory policies) before the first runnable slice exists.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Literal, Protocol, cast

from fred_core import VectorSearchHit
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
from langgraph.types import Checkpointer, Command, interrupt
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

try:
    from langchain.agents import create_agent as _langchain_create_agent
except Exception:  # pragma: no cover - compatibility fallback
    from langgraph.prebuilt import create_react_agent as _langgraph_create_react_agent
else:
    _langgraph_create_react_agent = None

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
from agentic_backend.core.tools.tool_loop import build_tool_loop
from .models import ReActAgentDefinition, ToolApprovalPolicy, ToolRefRequirement
from .runtime import (
    AgentRuntime,
    AssistantDeltaRuntimeEvent,
    AwaitingHumanRuntimeEvent,
    ExecutionConfig,
    Executor,
    FinalRuntimeEvent,
    HumanChoiceOption,
    HumanInputRequest,
    RuntimeEvent,
    RuntimeServices,
    ToolCallRuntimeEvent,
    ToolResultRuntimeEvent,
)
from .tool_approval import requires_tool_approval


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
    Minimal typed input for the first v2 ReAct runtime.

    This is intentionally chat-shaped because both the generic assistant and the
    first RAG-oriented agent are conversational agents. If Fred later needs a
    richer request envelope, that can wrap this model instead of replacing it.
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
    Generic payload schema for transport-routed tools.

    We keep this intentionally small for the first slice: the portable runtime
    knows that a tool exists and how to call it, but not yet each tool's full
    domain schema. That richer schema can later come from registry metadata.
    """

    payload: dict[str, object] = Field(
        default_factory=dict,
        description="JSON payload forwarded to the platform tool transport.",
    )


class _KnowledgeSearchToolArgs(BaseModel):
    """
    Explicit tool schema for the first built-in Fred retrieval tool.

    We special-case this because it is the first real production tool wired into
    the v2 runtime. A concrete schema makes model tool-calling far more reliable
    than the generic `payload` wrapper.
    """

    query: str = Field(
        ...,
        min_length=1,
        description="Natural-language search query to run against the selected corpus.",
    )
    top_k: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Maximum number of retrieved snippets to return.",
    )


class _LogsQueryToolArgs(BaseModel):
    window_minutes: int = Field(
        default=5,
        ge=1,
        le=60,
        description="How far back to scan logs.",
    )
    limit: int = Field(
        default=500,
        ge=1,
        le=5000,
        description="Maximum number of events to fetch per backend.",
    )
    min_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="WARNING",
        description="Minimum log level to include in the query.",
    )
    include_agentic: bool = Field(
        default=True,
        description="Whether to include Agentic backend logs.",
    )
    include_knowledge_flow: bool = Field(
        default=True,
        description="Whether to include Knowledge Flow logs.",
    )
    max_events: int = Field(
        default=200,
        ge=50,
        le=1000,
        description="Cap the events kept in the returned triage digest.",
    )


class _GeoPointArgs(BaseModel):
    name: str | None = Field(
        default=None,
        description="Human-readable point label shown in map popups when available.",
    )
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    properties: dict[str, object] = Field(
        default_factory=dict,
        description="Additional GeoJSON properties attached to the point.",
    )


class _GeoRenderPointsArgs(BaseModel):
    title: str = Field(
        default="Map results",
        description="Short textual summary accompanying the rendered map.",
    )
    points: list[_GeoPointArgs] = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Latitude/longitude points to render as a GeoJSON feature collection.",
    )
    popup_property: str | None = Field(
        default="name",
        description="Feature property to show in popups when present.",
    )
    fit_bounds: bool = Field(
        default=True,
        description="Whether the UI should fit the map viewport to the returned features.",
    )


class _ArtifactPublishTextArgs(BaseModel):
    file_name: str = Field(
        ...,
        min_length=1,
        description="File name to give the generated artifact, for example report.md or summary.txt.",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="Full textual content to publish for the user.",
    )
    title: str | None = Field(
        default=None,
        description="Optional user-facing title shown for the returned download link.",
    )
    content_type: str = Field(
        default="text/plain; charset=utf-8",
        description="MIME type of the generated text artifact.",
    )
    key: str | None = Field(
        default=None,
        description="Optional logical storage key. Leave empty to let Fred generate one.",
    )


class _ResourceFetchTextArgs(BaseModel):
    key: str = Field(
        ...,
        min_length=1,
        description="Logical storage key of the template or supporting text resource to read.",
    )
    scope: ResourceScope = Field(
        default=ResourceScope.AGENT_CONFIG,
        description="Where the resource lives. Agent configuration is the usual location for templates.",
    )
    target_user_id: str | None = Field(
        default=None,
        description="Required only for per-user agent resources.",
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
                    "name": tool_call.name,
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
            name=message.tool_name,
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
                name=str(tool_call.get("name") or ""),
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


def _truncate_for_human_review(value: object, *, max_chars: int = 1200) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except Exception:
        rendered = str(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."


def _is_french_language(language: str | None) -> bool:
    if language is None:
        return False
    return language.strip().lower().replace("_", "-").startswith("fr")


def _build_tool_approval_request(
    *,
    binding: BoundRuntimeContext,
    tool_name: str,
    tool_args: dict[str, object],
) -> HumanInputRequest:
    if _is_french_language(binding.runtime_context.language):
        return HumanInputRequest(
            stage="tool_approval",
            title="Confirmer l'execution de l'outil",
            question=(
                f"L'agent souhaite executer `{tool_name}`. "
                "Cette action peut modifier un etat ou declencher une action externe. "
                "Veux-tu continuer ?"
            ),
            choices=(
                HumanChoiceOption(
                    id="proceed",
                    label="Continuer",
                    description="Executer cet outil maintenant.",
                    default=True,
                ),
                HumanChoiceOption(
                    id="cancel",
                    label="Annuler",
                    description="Ne pas executer cet outil et laisser l'agent se replanifier.",
                ),
            ),
            free_text=True,
            metadata={
                "tool_name": tool_name,
                "tool_args_preview": _truncate_for_human_review(tool_args),
            },
        )

    return HumanInputRequest(
        stage="tool_approval",
        title="Confirm tool execution",
        question=(
            f"The agent wants to execute `{tool_name}`. "
            "This may modify state or trigger an external action. "
            "Do you want to continue?"
        ),
        choices=(
            HumanChoiceOption(
                id="proceed",
                label="Proceed",
                description="Run this tool now.",
                default=True,
            ),
            HumanChoiceOption(
                id="cancel",
                label="Cancel",
                description="Do not run this tool; let the agent replan.",
            ),
        ),
        free_text=True,
        metadata={
            "tool_name": tool_name,
            "tool_args_preview": _truncate_for_human_review(tool_args),
        },
    )


def _is_cancelled_human_decision(decision: object) -> bool:
    if isinstance(decision, dict):
        raw_choice = decision.get("choice_id") or decision.get("answer")
        if isinstance(raw_choice, str):
            return raw_choice.strip().lower() == "cancel"
        return False
    if isinstance(decision, str):
        return decision.strip().lower() == "cancel"
    return False


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
    if config.thread_id is None:
        return None
    return {"configurable": {"thread_id": config.thread_id}}


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
    Platform-owned runtime for pure v2 ReAct agent definitions.

    This is the first concrete runtime because it offers the best leverage:
    a small authoring surface, a generic execution engine, and a clean path to
    portable tool invocation through injected platform services.
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
            policy.system_prompt_template,
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
            tool_name = base_name
            suffix = 2
            while tool_name in used_names:
                tool_name = f"{base_name}_{suffix}"
                suffix += 1
            used_names.add(tool_name)

            if requirement.tool_ref == "knowledge.search":
                if tool_invoker is None:
                    raise RuntimeError(
                        "ReActRuntime requires RuntimeServices.tool_invoker for knowledge.search."
                    )

                async def _invoke_knowledge_search(
                    query: str,
                    top_k: int = 8,
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
                                payload={"query": query, "top_k": top_k},
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
                            coroutine=_invoke_knowledge_search,
                            name=tool_name,
                            description=requirement.description
                            or f"Platform-routed tool {requirement.tool_ref}.",
                            args_schema=_KnowledgeSearchToolArgs,
                            response_format="content_and_artifact",
                        ),
                    )
                )
                continue

            if requirement.tool_ref == "logs.query":
                if tool_invoker is None:
                    raise RuntimeError(
                        "ReActRuntime requires RuntimeServices.tool_invoker for logs.query."
                    )

                async def _invoke_logs_query(
                    window_minutes: int = 5,
                    limit: int = 500,
                    min_level: Literal[
                        "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
                    ] = "WARNING",
                    include_agentic: bool = True,
                    include_knowledge_flow: bool = True,
                    max_events: int = 200,
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
                                payload={
                                    "window_minutes": window_minutes,
                                    "limit": limit,
                                    "min_level": min_level,
                                    "include_agentic": include_agentic,
                                    "include_knowledge_flow": include_knowledge_flow,
                                    "max_events": max_events,
                                },
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
                            coroutine=_invoke_logs_query,
                            name=tool_name,
                            description=requirement.description
                            or f"Platform-routed tool {requirement.tool_ref}.",
                            args_schema=_LogsQueryToolArgs,
                            response_format="content_and_artifact",
                        ),
                    )
                )
                continue

            if requirement.tool_ref == "geo.render_points":
                if tool_invoker is None:
                    raise RuntimeError(
                        "ReActRuntime requires RuntimeServices.tool_invoker for geo.render_points."
                    )

                async def _invoke_geo_render_points(
                    title: str = "Map results",
                    points: list[dict[str, object]] | None = None,
                    popup_property: str | None = "name",
                    fit_bounds: bool = True,
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
                                payload={
                                    "title": title,
                                    "points": points or [],
                                    "popup_property": popup_property,
                                    "fit_bounds": fit_bounds,
                                },
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
                            coroutine=_invoke_geo_render_points,
                            name=tool_name,
                            description=requirement.description
                            or f"Platform-routed tool {requirement.tool_ref}.",
                            args_schema=_GeoRenderPointsArgs,
                            response_format="content_and_artifact",
                        ),
                    )
                )
                continue

            if requirement.tool_ref == "artifacts.publish_text":
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
                            tool_ref="artifacts.publish_text",
                            blocks=(
                                ToolContentBlock(
                                    kind=ToolContentKind.TEXT,
                                    text=(
                                        f"Published {artifact.file_name} for the user."
                                    ),
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
                        description=requirement.description
                        or "Publish a generated text artifact for the user and return a download link.",
                        tool=StructuredTool.from_function(
                            func=None,
                            coroutine=_invoke_artifact_publish_text,
                            name=tool_name,
                            description=requirement.description
                            or "Publish a generated text artifact for the user and return a download link.",
                            args_schema=_ArtifactPublishTextArgs,
                            response_format="content_and_artifact",
                        ),
                    )
                )
                continue

            if requirement.tool_ref == "resources.fetch_text":
                resource_reader = self.services.resource_reader
                if resource_reader is None:
                    raise RuntimeError(
                        "ReActRuntime requires RuntimeServices.resource_reader for resources.fetch_text."
                    )
                reader = resource_reader

                async def _invoke_resource_fetch_text(
                    key: str,
                    scope: ResourceScope = ResourceScope.AGENT_CONFIG,
                    target_user_id: str | None = None,
                    *,
                    tool_name_for_span: str = tool_name,
                ) -> tuple[str, ToolInvocationResult]:
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
                            tool_ref="resources.fetch_text",
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
                        description=requirement.description
                        or "Fetch a Fred-managed text template or supporting resource.",
                        tool=StructuredTool.from_function(
                            func=None,
                            coroutine=_invoke_resource_fetch_text,
                            name=tool_name,
                            description=requirement.description
                            or "Fetch a Fred-managed text template or supporting resource.",
                            args_schema=_ResourceFetchTextArgs,
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
        for tool in tool_provider.get_tools():
            tool_name = tool.name.strip()
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
            description = tool.description.strip() or "No description provided."
            tools.append(
                _BoundTool(
                    runtime_name=tool_name,
                    description=description,
                    tool=tool,
                )
            )
        return tools


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


def _create_compiled_react_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    binding: BoundRuntimeContext,
    approval_policy: ToolApprovalPolicy,
    checkpointer: Checkpointer,
) -> _CompiledReActAgent:
    if approval_policy.enabled:
        bound_model = model.bind_tools(tools)

        def _system_builder(_: object) -> str:
            return system_prompt

        def _requires_human_approval(tool_name: str) -> bool:
            return requires_tool_approval(
                tool_name,
                approval_enabled=True,
                exact_required_tools=set(approval_policy.always_require_tools),
            )

        async def _hitl_callback(
            tool_name: str, args: dict[str, object]
        ) -> dict[str, object]:
            request = _build_tool_approval_request(
                binding=binding,
                tool_name=tool_name,
                tool_args=args,
            )
            decision = interrupt(request.model_dump(mode="json"))
            if _is_cancelled_human_decision(decision):
                return {"cancel": True}
            return {}

        graph = build_tool_loop(
            model=bound_model,
            tools=list(tools),
            system_builder=_system_builder,
            requires_hitl=_requires_human_approval,
            hitl_callback=_hitl_callback,
        )
        return cast(
            _CompiledReActAgent,
            graph.compile(checkpointer=checkpointer),
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
            checkpointer=checkpointer,
        ),
    )
