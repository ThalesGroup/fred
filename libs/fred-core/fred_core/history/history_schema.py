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
Core conversation message schema shared across Fred backends.

Why this module exists:
- ``agentic-backend`` and ``fred-runtime`` pods both need to construct, persist,
  and retrieve typed conversation messages
- defining the schema here in ``fred-core`` means both backends import from one
  canonical source without any layer-rule violation

How to use it:
- use ``ChatMessage`` as the unit of history storage and retrieval
- use ``Role`` and ``Channel`` to classify messages
- use the ``make_*`` factories for the most common message shapes

Example:
    from fred_core.history.history_schema import ChatMessage, Role, Channel, TextPart

    msg = ChatMessage(
        session_id="s1",
        exchange_id="ex1",
        rank=0,
        timestamp=datetime.now(timezone.utc),
        role=Role.user,
        channel=Channel.final,
        parts=[TextPart(text="Hello")],
    )

Note on MessagePart coverage:
- this module defines the core structural parts (text, code, image, tool_call,
  tool_result) that are sufficient for pod-agent history storage
- ``agentic-backend`` extends the part union with UI-specific types (LinkPart,
  GeoPart) in its own ``chat_schema`` module
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Dict, List, Literal, Optional, TypeAlias, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fred_core.store import VectorSearchHit

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Role(str, Enum):
    user = "user"
    assistant = "assistant"
    tool = "tool"
    system = "system"


class Channel(str, Enum):
    # Main response shown to the user
    final = "final"
    # Planned steps
    plan = "plan"
    # High-level reasoning summary
    thought = "thought"
    # Observations / tool logs not shown as the final answer
    observation = "observation"
    # Tool invocation record
    tool_call = "tool_call"
    # Tool invocation result
    tool_result = "tool_result"
    # Agent-level error (transport errors use a separate event type)
    error = "error"
    # Injected context, tips, HITL events
    system_note = "system_note"


# ---------------------------------------------------------------------------
# Message parts
# ---------------------------------------------------------------------------


class TextPart(BaseModel):
    """
    Why this exists:
    - the most common message content; keeps the union discriminated by ``type``
    """

    type: Literal["text"] = "text"
    text: str


class CodePart(BaseModel):
    """
    Why this exists:
    - code snippets need language tagging so the UI can apply syntax highlighting
    """

    type: Literal["code"] = "code"
    language: Optional[str] = None
    code: str


class ImageUrlPart(BaseModel):
    """
    Why this exists:
    - agents can return image references that the UI should render inline
    """

    type: Literal["image_url"] = "image_url"
    url: str
    alt: Optional[str] = None


class ToolCallPart(BaseModel):
    """
    Why this exists:
    - tool invocations must be stored as structured records so the UI can display
      them in a timeline and analytics can aggregate tool usage

    How to use it:
    - ``args`` accepts a dict, a JSON string, or any scalar; it is always normalized
      to a dict before storage
    """

    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    args: Dict[str, Any]

    @field_validator("args", mode="before")
    @classmethod
    def _parse_args(cls, v: Any) -> Dict[str, Any]:
        if isinstance(v, dict):
            return v
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    return parsed
                return {"_raw": parsed}
            except Exception:
                return {"_raw": v}
        return {"_raw": str(v)}


class ToolResultPart(BaseModel):
    """
    Why this exists:
    - tool results must be stored alongside the call so history is self-contained
      for audit and replay

    How to use it:
    - ``content`` accepts str, dict, or list; non-str values are JSON-serialized
    """

    type: Literal["tool_result"] = "tool_result"
    call_id: str
    ok: Optional[bool] = None
    latency_ms: Optional[int] = None
    content: str

    @field_validator("content", mode="before")
    @classmethod
    def _ensure_str(cls, v: Any) -> str:
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False)
        if not isinstance(v, str):
            return str(v)
        return v


MessagePart: TypeAlias = Annotated[
    Union[TextPart, CodePart, ImageUrlPart, ToolCallPart, ToolResultPart],
    Field(discriminator="type"),
]
"""
Discriminated union of all core message parts.

Note: ``agentic-backend`` extends this union with LinkPart and GeoPart in its
own ``chat_schema`` module. The fred-core version covers all parts needed for
pod-agent history storage.
"""


# ---------------------------------------------------------------------------
# Token usage and metadata
# ---------------------------------------------------------------------------


class ChatTokenUsage(BaseModel):
    """Token counts attached to an assistant message."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


class ChatMetadata(BaseModel):
    """
    Small structured metadata attached to each stored message.

    Why this exists:
    - analytics queries need model name, token counts, and agent identity without
      deserializing the full message parts
    - ``extra="allow"`` lets subclasses and external callers attach extra fields
      without breaking storage
    """

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = None
    token_usage: Optional[ChatTokenUsage] = None
    agent_id: Optional[str] = None
    latency_ms: Optional[int] = None
    finish_reason: Optional[str] = None
    sources: List[VectorSearchHit] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Message
# ---------------------------------------------------------------------------


class ChatMessage(BaseModel):
    """
    The unit of conversation history storage.

    Invariants:
    - ``rank`` strictly increases per ``session_id``
    - exactly one ``assistant``/``final`` per ``exchange_id``
    - tool_call and tool_result are separate messages (not buried in blocks)

    Why this exists:
    - a single, queryable row per message keeps history linear, auditable,
      and independent of the LangGraph checkpoint blob format
    """

    session_id: str
    exchange_id: str
    rank: int
    timestamp: datetime
    role: Role
    channel: Channel
    parts: List[MessagePart]
    metadata: ChatMetadata = Field(default_factory=ChatMetadata)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def make_user_text(
    session_id: str, exchange_id: str, rank: int, text: str
) -> ChatMessage:
    """
    Build a user message with a single TextPart.

    How to use it:
    - call once per user turn before invoking the runtime
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.user,
        channel=Channel.final,
        parts=[TextPart(text=text)],
    )


def make_assistant_final(
    session_id: str,
    exchange_id: str,
    rank: int,
    text: str,
    *,
    model: Optional[str] = None,
    usage: Optional[ChatTokenUsage] = None,
    sources: Optional[List[VectorSearchHit]] = None,
    finish_reason: Optional[str] = None,
) -> ChatMessage:
    """
    Build the terminal assistant message for a turn.

    How to use it:
    - call after accumulating all assistant delta tokens into ``text``
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.assistant,
        channel=Channel.final,
        parts=[TextPart(text=text)] if text else [],
        metadata=ChatMetadata(
            model=model,
            token_usage=usage,
            finish_reason=finish_reason,
            sources=sources or [],
        ),
    )


def make_tool_call(
    session_id: str,
    exchange_id: str,
    rank: int,
    call_id: str,
    name: str,
    args: Dict[str, Any],
) -> ChatMessage:
    """
    Build a tool-call record message.

    How to use it:
    - call when a ``ToolCallRuntimeEvent`` is received
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.assistant,
        channel=Channel.tool_call,
        parts=[ToolCallPart(call_id=call_id, name=name, args=args)],
    )


def make_tool_result(
    session_id: str,
    exchange_id: str,
    rank: int,
    call_id: str,
    content: str,
    *,
    ok: Optional[bool] = None,
    latency_ms: Optional[int] = None,
) -> ChatMessage:
    """
    Build a tool-result record message.

    How to use it:
    - call when a ``ToolResultRuntimeEvent`` is received
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.tool,
        channel=Channel.tool_result,
        parts=[
            ToolResultPart(
                call_id=call_id, ok=ok, latency_ms=latency_ms, content=content
            )
        ],
    )
