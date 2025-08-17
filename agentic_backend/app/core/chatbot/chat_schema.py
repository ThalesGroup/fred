# chat_schema.py

from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Annotated, Literal
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict, ValidationError

from fred_core import VectorSearchHit


# ---------- Enums for clarity ----------
class MessageType(str, Enum):
    human = "human"
    ai = "ai"
    system = "system"
    tool = "tool"

class Sender(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"

class MessageSubtype(str, Enum):
    final = "final"
    thought = "thought"
    tool_result = "tool_result"
    plan = "plan"
    execution = "execution"
    observation = "observation"
    error = "error"
    injected_context = "injected_context"

class FinishReason(str, Enum):
    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    tool_calls = "tool_calls"
    cancelled = "cancelled"
    other = "other"

class ToolResultBlock(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    name: str
    content: str           # final string, even if tool gave JSON (stringify on server)
    ok: Optional[bool] = None
    latency_ms: Optional[int] = None

class TextBlock(BaseModel):
    type: Literal["text"] = "text"
    text: str

class CodeBlock(BaseModel):
    type: Literal["code"] = "code"
    language: Optional[str] = None
    code: str

class ImageUrlBlock(BaseModel):
    type: Literal["image_url"] = "image_url"
    url: str
    alt: Optional[str] = None

MessageBlock = Annotated[
    Union[TextBlock, ToolResultBlock, CodeBlock, ImageUrlBlock],
    Field(discriminator="type"),
]

# ---------- Token usage ----------
class ChatTokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int

# ---------- Tool calls ----------

class ToolCall(BaseModel):
    name: str
    args: Optional[Dict[str, Any]] = None
    result_preview: Optional[str] = None
    error: Optional[str] = None
    latency_ms: Optional[int] = None

# ---------- Strongly-typed metadata ----------
class ChatMessageMetadata(BaseModel):
    """
    A typed container for message metadata sent to the UI.
    Add new first-class fields here as your UI needs them.
    Unknown keys go into `extras` by design (no surprises).
    """
    model_config = ConfigDict(extra="forbid")  # prevent silent schema drift

    # Common
    model: Optional[str] = None
    token_usage: Optional[ChatTokenUsage] = None
    sources: List[VectorSearchHit] = Field(default_factory=list)

    # Helpful details
    latency_seconds: Optional[float] = None
    agent_name: Optional[str] = None
    finish_reason: Optional[FinishReason] = None

    # Domain-specific passthroughs
    fred: Optional[Dict[str, Any]] = None
    thought: Optional[Union[str, Dict[str, Any]]] = None
    tool_call: Optional[ToolCall] = None

    # Future-proof escape hatch
    extras: Dict[str, Any] = Field(default_factory=dict)

    def merge_extras(self, **kwargs) -> None:
        self.extras.update({k: v for k, v in kwargs.items() if v is not None})


# ---------- Unified message ----------
class ChatMessagePayload(BaseModel):
    exchange_id: str = Field(..., description="Unique ID for this question/reply exchange")
    user_id: str
    type: MessageType
    sender: Sender
    content: str
    blocks: Optional[List[MessageBlock]] = None
    timestamp: datetime  # serializes to ISO-8601; strings are accepted and parsed
    session_id: str = Field(..., description="Conversation ID")
    rank: int = Field(..., description="Monotonic message index within the session")
    metadata: ChatMessageMetadata = Field(default_factory=ChatMessageMetadata)
    subtype: Optional[MessageSubtype] = None

    # Convenience helper for incremental population
    def with_metadata(
        self,
        model: Optional[str] = None,
        token_usage: Optional[ChatTokenUsage] = None,
        sources: Optional[List[Union[VectorSearchHit, dict]]] = None,
        latency_seconds: Optional[float] = None,
        agent_name: Optional[str] = None,
        finish_reason: Optional[FinishReason] = None,
        fred: Optional[Dict[str, Any]] = None,
        thought: Optional[Union[str, Dict[str, Any]]] = None,
        **extras,
    ) -> "ChatMessagePayload":
        if model is not None:
            self.metadata.model = model
        if token_usage is not None:
            self.metadata.token_usage = token_usage
        if sources:
            normalized: List[VectorSearchHit] = []
            for s in sources:
                if isinstance(s, VectorSearchHit):
                    normalized.append(s)
                elif isinstance(s, dict):
                    try:
                        normalized.append(VectorSearchHit.model_validate(s))
                    except ValidationError:
                        # If a hit doesn't validate, keep it in extras rather than crashing
                        extras.setdefault("invalid_sources", []).append(s)
            self.metadata.sources = normalized
        if latency_seconds is not None:
            self.metadata.latency_seconds = latency_seconds
        if agent_name is not None:
            self.metadata.agent_name = agent_name
        if finish_reason is not None:
            self.metadata.finish_reason = finish_reason
        if fred is not None:
            self.metadata.fred = fred
        if thought is not None:
            self.metadata.thought = thought
        if extras:
            self.metadata.merge_extras(**extras)
        return self


# ---------- Session ----------
class SessionSchema(BaseModel):
    id: str
    user_id: str
    title: str
    updated_at: datetime

class SessionWithFiles(SessionSchema):
    file_names: List[str] = []


# ---------- Events (discriminated union) ----------
class StreamEvent(BaseModel):
    type: Literal["stream"] = "stream"
    message: ChatMessagePayload

class FinalEvent(BaseModel):
    type: Literal["final"] = "final"
    messages: List[ChatMessagePayload]
    session: SessionSchema

class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    content: str
    session_id: Optional[str] = None

ChatEvent = Annotated[Union[StreamEvent, FinalEvent, ErrorEvent], Field(discriminator="type")]


# ---------- Utilities ----------
def clean_token_usage(raw: dict) -> ChatTokenUsage:
    """
    Normalize an LLM token-usage dict into our typed model.
    Unknown keys are ignored; zeros are fine.
    """
    return ChatTokenUsage(
        input_tokens=int(raw.get("input_tokens", 0) or 0),
        output_tokens=int(raw.get("output_tokens", 0) or 0),
        total_tokens=int(raw.get("total_tokens", 0) or 0),
    )


def clean_agent_metadata(raw: dict) -> ChatMessageMetadata:
    """
    Convert a raw LLM response_metadata dict into ChatMessageMetadata.
    Validates sources as VectorSearchHit; non-conforming entries are placed in extras.
    """
    meta = ChatMessageMetadata()

    if m := raw.get("model_name"):
        meta.model = m
    if fr := raw.get("finish_reason"):
        try:
            meta.finish_reason = FinishReason(str(fr))
        except ValueError:
            meta.finish_reason = FinishReason.other
    if fu := raw.get("fred"):
        meta.fred = fu
    if th := raw.get("thought"):
        meta.thought = th

    # Normalize sources
    invalid: List[Any] = []
    for s in (raw.get("sources") or []):
        if isinstance(s, VectorSearchHit):
            meta.sources.append(s)
        elif isinstance(s, dict):
            try:
                meta.sources.append(VectorSearchHit.model_validate(s))
            except ValidationError:
                invalid.append(s)
        # else: silently ignore unexpected types
    if invalid:
        meta.extras["invalid_sources"] = invalid

    return meta
