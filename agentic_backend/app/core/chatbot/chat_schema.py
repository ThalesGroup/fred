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
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Annotated, Literal

from pydantic import BaseModel, Field, ConfigDict
from fred_core import VectorSearchHit

from app.core.agents.runtime_context import RuntimeContext  # Unchanged, as requested


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


class LinkPart(BaseModel):
    """
    Why this exists:
      - The UI needs a typed, explicit way to render links without parsing free text.
      - Lets agents express intent (citation/download/etc.) so the UI can group + style.
    """

    type: Literal["link"] = "link"
    href: str  # absolute URL
    title: Optional[str] = None  # human label; fallback to href if None
    kind: LinkKind = LinkKind.external
    rel: Optional[str] = None  # e.g. "noopener", "noreferrer", "ugc"
    mime: Optional[str] = None  # e.g. "application/pdf"
    source_id: Optional[str] = None
    # ^ if this link corresponds to a VectorSearchHit (metadata.sources),
    #   set source_id = hit.id so the UI can cross-highlight.


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
    args: Dict[str, Any]


class ToolResultPart(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    ok: Optional[bool] = None
    latency_ms: Optional[int] = None
    # Always send a string; stringify JSON results server-side to avoid UI logic.
    content: str


MessagePart = Annotated[
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

    # Escape hatch for gradual rollout; UI should ignore this.
    extras: Dict[str, Any] = Field(default_factory=dict)


# ---------- Message ----------


class ChatAskInput(BaseModel):
    user_id: str
    session_id: Optional[str] = None
    message: str
    agent_name: str
    runtime_context: Optional[RuntimeContext] = None
    client_exchange_id: str | None = None


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
    title: str
    updated_at: datetime


class SessionWithFiles(SessionSchema):
    file_names: List[str] = []


# ---------- Transport events ----------
class StreamEvent(BaseModel):
    type: Literal["stream"] = "stream"
    message: ChatMessage


class FinalEvent(BaseModel):
    type: Literal["final"] = "final"
    messages: List[ChatMessage]
    session: SessionSchema


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    content: str
    session_id: Optional[str] = None


ChatEvent = Annotated[
    Union[StreamEvent, FinalEvent, ErrorEvent], Field(discriminator="type")
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
