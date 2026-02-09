# Copyright Thales 2025
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

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, TypeAlias, Union

from fred_core import VectorSearchHit
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agentic_backend.core.agents.runtime_context import (
    RuntimeContext,  # Unchanged, as requested
)


# ---------- Core enums ----------
class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class Channel(str, Enum):
    # UI-facing buckets
    final = "final"  # the answer to display as the main assistant bubble
    plan = "plan"  # planned steps
    thought = "thought"  # high-level reasoning summary (safe/structured)
    observation = "observation"  # observations/logs, eg from tools, not the final
    tool_call = "tool_call"
    tool_result = "tool_result"
    error = "error"  # agent-level error (transport errors use ErrorEvent)
    system_note = "system_note"  # injected context, tips, etc.


class FinishReason(str, Enum):
    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    tool_calls = "tool_calls"
    cancelled = "cancelled"
    other = "other"


# ---------- Typed message parts ----------
class LinkKind(str, Enum):
    citation = "citation"  # source supporting the answer
    download = "download"  # file to fetch (pdf, csv, etc.)
    external = "external"  # generic external link
    dashboard = "dashboard"  # e.g., Grafana, Kibana
    related = "related"  # further reading
    view = "view"  # for pdf preview


class LinkPart(BaseModel):
    """
    Why this exists:
      - The UI needs a typed, explicit way to render links without parsing free text.
      - Lets agents express intent (citation/download/etc.) so the UI can group + style.
    """

    type: Literal["link"] = "link"
    href: Optional[str] = None  # absolute URL
    title: Optional[str] = None  # human label; fallback to href if None
    kind: LinkKind = LinkKind.external
    rel: Optional[str] = None  # e.g. "noopener", "noreferrer", "ugc"
    mime: Optional[str] = None  # e.g. "application/pdf"
    source_id: Optional[str] = None
    # ^ if this link corresponds to a VectorSearchHit (metadata.sources),
    #   set source_id = hit.id so the UI can cross-highlight.
    document_uid: Optional[str] = None
    file_name: Optional[str] = None


class GeoPart(BaseModel):
    """
    Why this exists:
      - Maps shouldn't be 'imagined' from text. We carry real data (GeoJSON FeatureCollection)
        so the UI can render it with Leaflet immediately.
      - Optional presentation hints keep style logic minimal in the UI.
    """

    type: Literal["geo"] = "geo"
    # Strict GeoJSON to avoid format proliferation; agents must normalize before emitting.
    # Expecting: {"type":"FeatureCollection","features":[...]}
    geojson: Dict[str, Any]
    # Optional UI hints; the UI should treat all as best-effort:
    popup_property: Optional[str] = None  # property to show in popups if present
    fit_bounds: bool = True  # auto-fit map to the features
    style: Optional[Dict[str, Any]] = None
    # e.g. {"weight":2,"opacity":0.8,"fillOpacity":0.1}


class TextPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class CodePart(BaseModel):
    type: Literal["code"] = "code"
    language: Optional[str] = None
    code: str


class ImageUrlPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    url: str
    alt: Optional[str] = None


class ToolCallPart(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    args: Dict[str, Any]  # normalized dict after validation

    @field_validator("args", mode="before")
    @classmethod
    def parse_args(cls, v: Any) -> Dict[str, Any]:
        # Accept dicts directly
        if isinstance(v, dict):
            return v
        # Try to parse JSON strings; if scalar/array, wrap as {"_raw": ...}
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
                return {"_raw": parsed}
            except Exception:
                return {"_raw": v}
        # Fallback: stringify any other object
        return {"_raw": str(v)}


class ToolResultPart(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    ok: Optional[bool] = None
    latency_ms: Optional[int] = None
    # Always send a string; stringify JSON results server-side to avoid UI logic.
    content: str

    # Dev ergonomics: accept dict/list/other and stringify.
    @field_validator("content", mode="before")
    @classmethod
    def _ensure_str_content(cls, v: Any) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        if not isinstance(v, str):
            return str(v)
        return v


MessagePart: TypeAlias = Annotated[
    Union[
        TextPart,
        CodePart,
        ImageUrlPart,
        ToolCallPart,
        ToolResultPart,
        LinkPart,
        GeoPart,
    ],
    Field(discriminator="type"),
]


# ---------- Token usage ----------
class ChatTokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


# ---------- Message metadata (small, strong) ----------
class ChatMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Optional[str] = None
    token_usage: Optional[ChatTokenUsage] = None
    # Keep your VectorSearchHit untouched
    sources: List[VectorSearchHit] = Field(default_factory=list)

    agent_name: Optional[str] = None
    latency_ms: Optional[int] = None
    finish_reason: Optional[FinishReason] = None
    runtime_context: Optional[RuntimeContext] = None

    # Escape hatch for gradual rollout; UI should ignore this.
    extras: Dict[str, Any] = Field(default_factory=dict)


# ---------- Message ----------


class BaseWsInput(BaseModel):
    agent_name: str
    runtime_context: Optional[RuntimeContext] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None


class ChatAskInput(BaseWsInput):
    type: Literal["ask"] = "ask"
    session_id: str
    message: str
    client_exchange_id: Optional[str] = (
        None  # le front l’envoie; sinon backend génère l’exchange_id
    )


class HumanResumeInput(BaseWsInput):
    type: Literal["human_resume"] = "human_resume"
    session_id: str = Field(..., description="Required session id for resume")
    exchange_id: str
    payload: Dict[str, Any] = Field(default_factory=dict)


ChatWsInput = Annotated[
    Union[ChatAskInput, HumanResumeInput], Field(discriminator="type")
]


class ChatMessage(BaseModel):
    """
    The only thing the UI needs to render a conversation.
    Invariants:
      - rank strictly increases per session_id
      - exactly one assistant/final per exchange_id
      - tool_call/tool_result are separate messages (not buried in blocks)
    """

    session_id: str
    exchange_id: str
    rank: int
    timestamp: datetime

    role: Role
    channel: Channel
    parts: List[MessagePart]

    metadata: ChatMetadata = Field(default_factory=ChatMetadata)


# ---------- Sessions ----------
class SessionSchema(BaseModel):
    id: str
    user_id: str
    agent_name: str | None = None
    title: str
    updated_at: datetime
    next_rank: int | None = None
    preferences: Dict[str, Any] | None = None


class AttachmentRef(BaseModel):
    id: str
    name: str


class SessionWithFiles(SessionSchema):
    agents: set[str]  # Set of all agents used in this conversation
    file_names: List[str] = []
    attachments: List[AttachmentRef] = []


class ChatbotRuntimeSummary(BaseModel):
    """Lightweight runtime snapshot for UI recap."""

    sessions_total: int
    agents_active_total: int
    attachments_total: int
    attachments_sessions: int
    max_attachments_per_session: int


# ---------- Transport events ----------
class StreamEvent(BaseModel):
    type: Literal["stream"] = "stream"
    message: ChatMessage


class SessionEvent(BaseModel):
    type: Literal["session"] = "session"
    session: SessionSchema


class FinalEvent(BaseModel):
    type: Literal["final"] = "final"
    messages: List[ChatMessage]
    session: SessionSchema


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    content: str
    session_id: Optional[str] = None


class HitlChoice(BaseModel):
    """Choice option surfaced to the user during HITL."""

    id: str
    label: str
    description: Optional[str] = None
    default: Optional[bool] = None


class HitlPayload(BaseModel):
    """
    Normalized HITL payload sent by agents when calling `interrupt()`.
    Backwards-compatible: extra keys are preserved for legacy agents/UI.
    """

    stage: Optional[str] = None
    title: Optional[str] = None
    question: Optional[str] = None
    choices: Optional[List[HitlChoice]] = None
    free_text: Optional[bool] = None
    metadata: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None

    model_config = ConfigDict(extra="allow")


def validate_hitl_payload(raw: Any) -> HitlPayload:
    """
    Central HITL payload validation (runtime enforcement).
    Accepts extra keys but enforces minimal UX safety:
      - question or title must be present and non-empty
      - choices, if provided, must be non-empty with unique ids and max one default
    """
    payload = HitlPayload.model_validate(raw)

    # question/title presence
    has_question = bool((payload.question or "").strip())
    has_title = bool((payload.title or "").strip())
    if not (has_question or has_title):
        raise ValueError("HITL payload requires a non-empty 'question' or 'title'.")

    # choices validation
    if payload.choices is not None:
        if len(payload.choices) == 0:
            raise ValueError("HITL payload 'choices' must be a non-empty list.")
        ids = [c.id.strip() for c in payload.choices if isinstance(c.id, str)]
        if any(not cid for cid in ids):
            raise ValueError("HITL payload 'choices' entries must have a non-empty id.")
        if len(ids) != len(set(ids)):
            raise ValueError("HITL payload 'choices' ids must be unique.")
        defaults = [c for c in payload.choices if c.default]
        if len(defaults) > 1:
            raise ValueError(
                "HITL payload 'choices' cannot have more than one default choice."
            )

    # metadata: best-effort check for JSON-serializable dict
    if payload.metadata is not None and not isinstance(payload.metadata, dict):
        raise ValueError("HITL payload 'metadata' must be a dictionary if provided.")

    return payload


class AwaitingHumanEvent(BaseModel):
    """
    Emitted when an agent interrupts and awaits human input (HITL).
    The payload is agent-defined (e.g., question + data snapshot).
    """

    type: Literal["awaiting_human"] = "awaiting_human"
    session_id: str
    exchange_id: str
    # Accept the normalized schema while preserving legacy payloads that may include arbitrary keys.
    payload: Union[HitlPayload, Dict[str, Any]]


ChatEvent = Annotated[
    Union[StreamEvent, SessionEvent, FinalEvent, ErrorEvent, AwaitingHumanEvent],
    Field(discriminator="type"),
]


def make_user_text(session_id, exchange_id, rank, text: str) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.utcnow(),
        role=Role.user,
        channel=Channel.final,
        parts=[TextPart(text=text)],
    )


def make_assistant_final(
    session_id,
    exchange_id,
    rank,
    parts: List[MessagePart],
    model: str,
    sources: List[VectorSearchHit],
    usage: ChatTokenUsage,
) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.utcnow(),
        role=Role.assistant,
        channel=Channel.final,
        parts=parts,
        metadata=ChatMetadata(model=model, token_usage=usage, sources=sources),
    )


def make_tool_call(session_id, exchange_id, rank, call_id, name, args) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.utcnow(),
        role=Role.assistant,
        channel=Channel.tool_call,
        parts=[ToolCallPart(call_id=call_id, name=name, args=args)],
    )


def make_tool_result(
    session_id, exchange_id, rank, call_id, ok, ms, content
) -> ChatMessage:
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.utcnow(),
        role=Role.tool,
        channel=Channel.tool_result,
        parts=[ToolResultPart(call_id=call_id, ok=ok, latency_ms=ms, content=content)],
    )
