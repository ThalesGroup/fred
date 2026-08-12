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


class FinishReason(str, Enum):
    """
    Why a model call ended, normalized across providers.

    Why this exists:
    - LangChain providers report this under different keys and vocabularies
      (OpenAI: response_metadata["finish_reason"] = "stop"/"length"/"tool_calls";
      Gemini/Vertex: "STOP"/"MAX_TOKENS", or "UNKNOWN_<n>" for an enum value the
      installed SDK doesn't recognize yet; Anthropic: response_metadata["stop_reason"]
      = "end_turn"/"max_tokens"/"tool_use") — the raw value is provider- and even
      SDK-version-dependent, so it can never be fully enumerated
    - a small, Fred-owned vocabulary with a deliberate ``other`` catch-all keeps
      this typed end-to-end (live SSE event and persisted history) without ever
      rejecting a value this build doesn't recognize
    """

    stop = "stop"
    length = "length"
    content_filter = "content_filter"
    tool_calls = "tool_calls"
    error = "error"
    other = "other"


# Raw provider values (lower-cased) known to map onto the Fred vocabulary above.
# Anything absent from this table — a new provider, a new SDK enum value, a typo —
# normalizes to FinishReason.other rather than failing validation.
_FINISH_REASON_ALIASES: Dict[str, FinishReason] = {
    "stop": FinishReason.stop,
    "end_turn": FinishReason.stop,  # Anthropic
    "stop_sequence": FinishReason.stop,  # Anthropic
    "length": FinishReason.length,
    "max_tokens": FinishReason.length,  # Anthropic, Gemini/Vertex
    "content_filter": FinishReason.content_filter,
    "safety": FinishReason.content_filter,  # Gemini/Vertex
    "recitation": FinishReason.content_filter,  # Gemini/Vertex
    "tool_calls": FinishReason.tool_calls,
    "tool_use": FinishReason.tool_calls,  # Anthropic
    "function_call": FinishReason.tool_calls,  # OpenAI legacy
    "error": FinishReason.error,  # Fred's own synthetic value (agent_app.py)
}


def coerce_finish_reason(raw: object) -> Optional[FinishReason]:
    """
    Normalize any raw finish-reason value (provider string, legacy DB value, or
    already-canonical) to a `FinishReason`, `None`, or `other`.

    Why this exists:
    - shared by `ChatMetadata`'s validator (write AND read, so a row persisted
      before this normalization existed still loads without error) and by
      `fred-runtime`'s `model_metadata.py` (so the live SSE event and the
      persisted history agree on the same value for the same turn)
    """
    if raw is None:
        return None
    if isinstance(raw, FinishReason):
        return raw
    return _FINISH_REASON_ALIASES.get(str(raw).strip().lower(), FinishReason.other)


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


class HitlPendingCallRecord(BaseModel):
    """
    One tool call a persisted HITL gate covers, mirroring the live event's
    ``PendingToolCall`` (fred-sdk ``contracts/runtime.py``). Kept as its own
    record here (rather than importing fred-sdk's) because ``fred-core`` sits
    below the sdk layer and must stay self-contained.
    """

    tool_call_id: str = ""
    tool_name: str
    args_preview: str = ""


class HitlRequestPart(BaseModel):
    """
    Full structured record of a HITL pause presented to the user.

    Why this exists:
    - the ``awaiting_human`` SSE event carries the complete gate definition
      (question, choices, stage, title); storing it verbatim lets audit logs
      show exactly what the agent asked and what options were available
    - the UI can reconstruct an interactive choice card from this record when
      replaying history, instead of showing a flat system note
    - ``interrupt_id``/``checkpoint_id``/``pending_calls`` (added alongside the
      original fields, 2026-08) are the resume identity + gated tool calls: the
      original fields alone let the UI SHOW a reconstructed card but never
      ANSWER it — a page reload while a gate was still open left the turn
      genuinely un-resumable and the gated tool call stuck rendering as
      "running" (no way to correlate it as awaiting confirmation). These make
      reconstruction after a reload fully interactive again, not just readable.

    How to use it:
    - one ``HitlRequestPart`` per ``awaiting_human`` event, stored in a
      ``Channel.hitl_request`` message with ``Role.system``
    """

    type: Literal["hitl_request"] = "hitl_request"
    stage: Optional[str] = None
    title: Optional[str] = None
    question: str
    choices: List[HitlChoiceRecord]
    free_text: bool = False
    interrupt_id: Optional[str] = None
    checkpoint_id: Optional[str] = None
    pending_calls: List[HitlPendingCallRecord] = Field(default_factory=list)


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


MessagePart: TypeAlias = Annotated[
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
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


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
    finish_reason: Optional[FinishReason] = None
    sources: List[VectorSearchHit] = Field(default_factory=list)

    @field_validator("finish_reason", mode="before")
    @classmethod
    def _normalize_finish_reason(cls, v: Any) -> Optional[FinishReason]:
        return coerce_finish_reason(v)


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
            finish_reason=coerce_finish_reason(finish_reason),
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
    *,
    token_usage: Optional[Dict[str, int]] = None,
) -> ChatMessage:
    """
    Build a tool-call record message.

    How to use it:
    - call when a ``ToolCallRuntimeEvent`` is received
    - ``token_usage``: the model call that decided to make this tool call
      (TRACE-01), same shape as ``ToolCallRuntimeEvent.token_usage``
    """
    return ChatMessage(
        session_id=session_id,
        exchange_id=exchange_id,
        rank=rank,
        timestamp=datetime.now(timezone.utc),
        role=Role.assistant,
        channel=Channel.tool_call,
        parts=[ToolCallPart(call_id=call_id, name=name, args=args)],
        metadata=ChatMetadata(token_usage=ChatTokenUsage(**token_usage))
        if token_usage
        else ChatMetadata(),
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
    free_text: bool = False,
    interrupt_id: Optional[str] = None,
    checkpoint_id: Optional[str] = None,
    pending_calls: Optional[List[Dict[str, str]]] = None,
) -> ChatMessage:
    """
    Build the HITL gate record from an ``awaiting_human`` SSE event.

    Why this exists:
    - the full gate definition (question + all presented options) must survive
      in history for audit and UI replay; a flat text note loses the choices
    - ``interrupt_id``/``checkpoint_id``/``pending_calls`` are the resume
      identity — persisting them (not just the display text) is what lets the
      UI reconstruct a FULLY INTERACTIVE prompt after a page reload while the
      gate is still open, not just a readable-but-dead one

    How to use it:
    - call when an ``awaiting_human`` runtime event is received
    - pass ``choices`` as the raw list of ``{id, label}`` dicts from the event
      payload; extra keys are ignored
    - pass ``interrupt_id``/``checkpoint_id``/``pending_calls`` straight from
      the same event's ``request`` (``HumanInputRequest``) — omit only for a
      caller that genuinely has none (e.g. a non-tool-approval gate)

    Example:
    - ``make_hitl_request(sid, xid, rank, question="Proceed?",
        choices=[{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}])``
    """
    choice_records = [
        HitlChoiceRecord(id=c["id"], label=c.get("label", c["id"]))
        for c in choices
        if "id" in c
    ]
    pending_call_records = [
        HitlPendingCallRecord(
            tool_call_id=c.get("tool_call_id", ""),
            tool_name=c.get("tool_name", ""),
            args_preview=c.get("args_preview", ""),
        )
        for c in (pending_calls or [])
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
                free_text=free_text,
                interrupt_id=interrupt_id,
                checkpoint_id=checkpoint_id,
                pending_calls=pending_call_records,
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
