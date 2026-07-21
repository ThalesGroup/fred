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
    # Full structured record of a HITL pause (question + choices presented)
    hitl_request = "hitl_request"
    # User's selection after a HITL gate (choice_id + optional label)
    hitl_response = "hitl_response"


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


class HitlChoiceRecord(BaseModel):
    """
    One option that was presented to the user in a HITL gate.

    Why this exists:
    - the full choice list must survive in history for audit and UI replay;
      storing only the question text loses the structured options that were shown
    """

    id: str
    label: str


class HitlRequestPart(BaseModel):
    """
    Full structured record of a HITL pause presented to the user.

    Why this exists:
    - the ``awaiting_human`` SSE event carries the complete gate definition
      (question, choices, stage, title); storing it verbatim lets audit logs
      show exactly what the agent asked and what options were available
    - the UI can reconstruct an interactive choice card from this record when
      replaying history, instead of showing a flat system note

    How to use it:
    - one ``HitlRequestPart`` per ``awaiting_human`` event, stored in a
      ``Channel.hitl_request`` message with ``Role.system``
    """

    type: Literal["hitl_request"] = "hitl_request"
    stage: Optional[str] = None
    title: Optional[str] = None
    question: str
    choices: List[HitlChoiceRecord]


class HitlResponsePart(BaseModel):
    """
    User's selection after a HITL gate.

    Why this exists:
    - the resume payload (which option was picked, or what text was typed) is
      the user's half of the HITL exchange; omitting it from history breaks
      audit trails and makes replay incomplete
    - for free-text HITL gates, ``choice_id`` carries the typed text directly
      (the runtime convention from ``choice_step``)

    How to use it:
    - one ``HitlResponsePart`` per HITL resume turn, stored in a
      ``Channel.hitl_response`` message with ``Role.user``
    - ``label`` is denormalized from the matching ``HitlChoiceRecord`` when
      known; it may be absent for free-text responses
    """

    type: Literal["hitl_response"] = "hitl_response"
    choice_id: str
    label: Optional[str] = None


_CORE_PART_KINDS = frozenset(
    {
        "text",
        "code",
        "image_url",
        "tool_call",
        "tool_result",
        "hitl_request",
        "hitl_response",
    }
)


class UiPartRecord(BaseModel):
    """
    Open pass-through record for a capability-emitted ``ui_part``.

    Why this exists:
    - the runtime ``UiPart`` union is OPEN: capability packages register new
      part kinds (``link``, ``geo``, ``ppt_preview``, …) at pod boot, so core
      history storage cannot enumerate them
    - dropping unknown kinds at persistence time silently breaks history
      replay for capability UI (the part renders live over SSE, then vanishes
      on reload) — this record retains every field verbatim instead

    How to use it:
    - validate any serialized ui_part dict with
      ``UiPartRecord.model_validate(part_dict)``; all fields beyond ``type``
      are kept as extras and round-trip through ``model_dump``
    """

    model_config = ConfigDict(extra="allow")

    type: str

    @field_validator("type")
    @classmethod
    def _reject_core_kinds(cls, v: str) -> str:
        # A malformed CORE part (e.g. a "text" part missing its text) must fail
        # loudly on its own model, never silently degrade into an open record.
        if v in _CORE_PART_KINDS:
            raise ValueError(f"'{v}' is a core message part kind, not a ui_part")
        return v


CoreMessagePart: TypeAlias = Annotated[
    Union[
        TextPart,
        CodePart,
        ImageUrlPart,
        ToolCallPart,
        ToolResultPart,
        HitlRequestPart,
        HitlResponsePart,
    ],
    Field(discriminator="type"),
]

MessagePart: TypeAlias = Union[CoreMessagePart, UiPartRecord]
"""
All storable message parts: the discriminated core union, plus the open
``UiPartRecord`` fallback for capability-emitted ui_part kinds (the ``type``
validator on ``UiPartRecord`` keeps core kinds out of the fallback branch).

Note: ``agentic-backend`` extends the core union with LinkPart and GeoPart in
its own ``chat_schema`` module. The fred-core version covers all parts needed
for pod-agent history storage.
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
    ui_parts: Optional[List[Dict[str, Any]]] = None,
) -> ChatMessage:
    """
    Build the terminal assistant message for a turn.

    How to use it:
    - call after accumulating all assistant delta tokens into ``text``
    - pass the FinalRuntimeEvent's serialized ``ui_parts`` so capability chat
      parts (link, ppt_preview, …) survive into history — they are appended
      after the text part, mirroring the live SSE message shape
    """
    parts: List[MessagePart] = [TextPart(text=text)] if text else []
    for raw in ui_parts or []:
        parts.append(UiPartRecord.model_validate(raw))
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.assistant,
        channel=Channel.final,
        parts=parts,
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


def make_hitl_request(
    session_id: str,
    exchange_id: str,
    rank: int,
    *,
    question: str,
    choices: List[Dict[str, str]],
    stage: Optional[str] = None,
    title: Optional[str] = None,
) -> ChatMessage:
    """
    Build the HITL gate record from an ``awaiting_human`` SSE event.

    Why this exists:
    - the full gate definition (question + all presented options) must survive
      in history for audit and UI replay; a flat text note loses the choices

    How to use it:
    - call when an ``awaiting_human`` runtime event is received
    - pass ``choices`` as the raw list of ``{id, label}`` dicts from the event
      payload; extra keys are ignored

    Example:
    - ``make_hitl_request(sid, xid, rank, question="Proceed?",
        choices=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}])``
    """
    choice_records = [
        HitlChoiceRecord(id=c["id"], label=c.get("label", c["id"]))
        for c in choices
        if "id" in c
    ]
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.system,
        channel=Channel.hitl_request,
        parts=[
            HitlRequestPart(
                stage=stage,
                title=title,
                question=question,
                choices=choice_records,
            )
        ],
    )


def make_hitl_response(
    session_id: str,
    exchange_id: str,
    rank: int,
    *,
    choice_id: str,
    label: Optional[str] = None,
) -> ChatMessage:
    """
    Build the user's HITL selection record from a resume turn.

    Why this exists:
    - the user's choice is the second half of the HITL exchange; without it
      the audit record is incomplete and the UI cannot show what was selected

    How to use it:
    - call at the start of a HITL resume turn, before processing agent events
    - ``choice_id`` is the raw id selected (or the typed text for free-text gates)
    - ``label`` is denormalized from the matching choice when known

    Example:
    - ``make_hitl_response(sid, xid, rank, choice_id="yes", label="Yes")``
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.user,
        channel=Channel.hitl_response,
        parts=[HitlResponsePart(choice_id=choice_id, label=label)],
    )
