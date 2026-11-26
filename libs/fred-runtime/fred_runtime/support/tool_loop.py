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
Pure message-hygiene helpers for the ReAct execution loop.

Why this module exists:
- checkpointed message history can be poisoned (dangling tool calls from
  crashed turns) or unbounded; every model call must see a sanitized, bounded
  view of it
- these helpers are pure functions over message lists, kept below `react/` so
  any runtime can reuse them without platform dependencies

How to use:
- the ReAct middleware frame (`react/middleware/`,
  `CheckpointHygieneMiddleware`) applies them to the model input on every call

History note (#1972):
- this module used to also host the hand-rolled 4-node ReAct StateGraph
  (`build_tool_loop`); that loop was replaced by LangChain `create_agent` plus
  the platform middleware frame, and the node logic was re-homed into
  `react/middleware/`. Only the pure helpers remain here.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Sequence
from typing import Any, Dict, List

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)

from .thinking import content_to_text, extract_thinking_text, is_thinking_block

logger = logging.getLogger(__name__)


class ChatTurnTooLargeError(RuntimeError):
    """
    Raised when protected model-input context exceeds the character budget.

    Deliberately carries only numbers, never message content: this message
    reaches the user as-is via the generic `execution_error` path
    (`agent_app.py`), and submitted/generated text must never be echoed back.
    """

    def __init__(self, *, limit_chars: int, actual_chars: int) -> None:
        self.limit_chars = limit_chars
        self.actual_chars = actual_chars
        super().__init__(
            f"Required conversation context ({actual_chars:,} characters) exceeds the "
            f"{limit_chars:,}-character model-input budget for this deployment."
        )


class ChatTurnTooManyMessagesError(RuntimeError):
    """Raised when protected conversation context exceeds the message limit."""

    def __init__(self, *, limit_messages: int, actual_messages: int) -> None:
        self.limit_messages = limit_messages
        self.actual_messages = actual_messages
        super().__init__(
            f"Required conversation context ({actual_messages:,} messages) exceeds the "
            f"{limit_messages:,}-message model-input budget for this deployment."
        )


def compact_history_to_budget(
    messages: Sequence[BaseMessage],
    budget: int,
    measure: Callable[[Sequence[BaseMessage]], int],
    *,
    max_completed_turns: int | None = None,
) -> list[BaseMessage]:
    """Keep completed conversation anchors and the active turn within a budget.

    ``measure`` may count messages, characters, or tokens. It must be monotonic
    when messages are added. ``max_completed_turns`` bounds projection work
    when the caller knows an upper bound. An over-budget protected context is
    returned for the caller to reject with its unit-specific error.
    """
    if max_completed_turns is not None and max_completed_turns < 1:
        raise ValueError("max_completed_turns must be positive")
    original = list(messages)
    if measure(original) <= budget:
        return original

    last_human = next(
        (
            i
            for i in range(len(original) - 1, -1, -1)
            if isinstance(original[i], HumanMessage)
        ),
        None,
    )
    if last_human is None:
        return original

    first_human = next(
        i for i, message in enumerate(original) if isinstance(message, HumanMessage)
    )
    prefix = [
        message
        for message in original[:first_human]
        if isinstance(message, SystemMessage)
    ]
    active = original[last_human:]
    projected: list[list[BaseMessage]] = []
    end = last_human
    while end > first_human:
        start = next(
            (
                i
                for i in range(end - 1, first_human - 1, -1)
                if isinstance(original[i], HumanMessage)
            ),
            None,
        )
        if start is None:
            break
        final = original[end - 1]
        if isinstance(final, AIMessage) and not final.tool_calls:
            answer = final.model_copy(
                update={"content": content_to_text(final.content)}
            )
            projected.append([original[start], answer])
            if (
                max_completed_turns is not None
                and len(projected) >= max_completed_turns
            ):
                break
        end = start

    def candidate(turns: int) -> list[BaseMessage]:
        return [
            *prefix,
            *(message for pair in reversed(projected[:turns]) for message in pair),
            *active,
        ]

    if not projected:
        return candidate(0)
    latest = candidate(1)
    if measure(latest) > budget:
        return latest
    all_turns = candidate(len(projected))
    if measure(all_turns) <= budget:
        return all_turns

    low, high = 1, len(projected)
    while low + 1 < high:
        middle = (low + high) // 2
        if measure(candidate(middle)) <= budget:
            low = middle
        else:
            high = middle
    return candidate(low)


def strip_message_names(messages: List[Any]) -> List[Any]:
    """Remove provider-incompatible names from model input, preserving checkpoints."""
    return [
        message.model_copy(update={"name": None})
        if getattr(message, "name", None) is not None
        else message
        for message in messages
    ]


def sanitize_dangling_tool_calls(messages: List[Any]) -> List[Any]:
    """
    Remove any AIMessage(tool_calls=...) whose call_ids are not all answered
    by immediately-following ToolMessages, and any ToolMessage left with no
    AIMessage(tool_calls) claiming it at all.

    Why this exists:
    - When a turn crashes mid-flight (e.g. OpenAI 400 on a previous call), the
      LangGraph checkpoint stores the user message and the assistant tool_call
      request, but never the tool result. Every subsequent turn then loads that
      poisoned checkpoint state and OpenAI rejects the payload with:
        "tool_call_ids did not have response messages: <id>"
    - Symmetrically, a ToolMessage can end up with no AIMessage in front of it
      at all (its request was dropped by an earlier sanitize pass, or history
      windowing cut a pair in half) — providers reject that too, with
      "Unexpected role 'tool' after role '<previous>'".
    - Sanitizing here is the only safe place: it covers both the in-memory
      and persisted checkpoint paths, regardless of whether history restore
      ran or was skipped.

    What it does:
    - Walk through messages in order.
    - A bare ToolMessage (reached without following an AIMessage's own
      tool_calls) is orphaned — drop it.
    - For each AIMessage with tool_calls, check that every call_id has a
      matching ToolMessage immediately following it.
    - If ANY call_id is unmatched, drop the AIMessage AND any partial
      ToolMessages that followed it, then continue with the rest of the
      message list (preserving subsequent user messages so the current
      query is not lost).
    """
    result: List[Any] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        # A ToolMessage reached here was never preceded by an AIMessage(tool_calls)
        # claiming it — the branch below only ever advances `i` past an
        # AIMessage's own ToolMessages, so this one is orphaned (e.g. a prior
        # AIMessage that requested it was trimmed away, or history windowing cut
        # a pair in half). Providers reject a lone `tool` role with no matching
        # request, so drop it rather than pass it through unchanged.
        if isinstance(msg, ToolMessage):
            logger.warning(
                "[TOOL_LOOP] Dropped orphaned ToolMessage at index %d "
                "(no preceding AIMessage(tool_calls) claims it).",
                i,
            )
            i += 1
            continue
        tool_calls = (
            getattr(msg, "tool_calls", None) if isinstance(msg, AIMessage) else None
        )
        if tool_calls:
            expected_ids = {tc.get("id") for tc in tool_calls if tc.get("id")}
            # Scan immediately-following ToolMessages
            j = i + 1
            seen_ids: set[str] = set()
            while j < len(messages) and isinstance(messages[j], ToolMessage):
                call_id = getattr(messages[j], "tool_call_id", None)
                if call_id:
                    seen_ids.add(call_id)
                j += 1
            if expected_ids and expected_ids == seen_ids:
                # Fully matched — keep AIMessage + all ToolMessages
                result.extend(messages[i:j])
                i = j
            else:
                # Dangling or partial — drop AIMessage and partial ToolMessages,
                # keep everything after (user messages for the current turn).
                logger.warning(
                    "[TOOL_LOOP] Dropped dangling AIMessage(tool_calls) at index %d "
                    "expected_ids=%s seen_ids=%s. "
                    "This usually means a prior turn crashed before the tool result was stored.",
                    i,
                    expected_ids,
                    seen_ids,
                )
                i = j  # skip over partial ToolMessages too
        else:
            result.append(msg)
            i += 1
    return result


def _tool_calls_char_len(message: Any) -> int:
    """
    Character length of a message's proposed tool-call arguments.

    Why this matters (found in PR review, #2350): a tool-calling AIMessage's
    own `content` is typically empty or a short preamble — LangChain/the
    provider put the actual payload in `tool_calls[*]["args"]` instead. The
    motivating field incident's `write_document` call is exactly this shape:
    an empty-content AIMessage carrying a 22k-character `content_markdown`
    argument. Without this, that argument was invisible to
    `_message_char_len` and the whole point of this budget — catching a
    large-tool-output turn before it blows the provider's context window —
    would silently not engage on the one case it was built for.

    JSON-serialized (not just summing string leaf values): args can nest
    dicts/lists/non-string values, and this approximates what actually goes
    over the wire to the provider closely enough for a proxy budget — the
    small serialization overhead (quotes, braces, commas) only makes the
    estimate more conservative, never less.
    """
    tool_calls = getattr(message, "tool_calls", None)
    if not tool_calls:
        return 0
    total = 0
    for call in tool_calls:
        args = call.get("args") if isinstance(call, dict) else None
        if not args:
            continue
        try:
            total += len(json.dumps(args, ensure_ascii=False, default=str))
        except (TypeError, ValueError):
            total += len(str(args))
    return total


def _message_char_len(message: Any) -> int:
    """
    Character length of one message: its content (robust to multimodal
    content blocks as well as plain string content) plus any proposed
    tool-call arguments (see `_tool_calls_char_len`).

    Why character count, not tokens (#2350):
    - no exact tokenizer covers every provider this deployment can point at
      (Mistral, Azure, OpenAI, ...); a character count is a cheap, provider-
      agnostic, deterministic proxy for the same over-large-payload problem
      `max_chat_input_chars` (#2253) already counts on a single message.
    """
    content = getattr(message, "content", None)
    total = 0
    if isinstance(content, str):
        total = len(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                total += len(block)
            elif is_thinking_block(block):
                # Replayed natively for Mistral, so it counts toward the budget.
                total += len(extract_thinking_text(block))
            elif isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    total += len(text)
    return total + _tool_calls_char_len(message)


def total_char_len(messages: Sequence[BaseMessage]) -> int:
    """Total character length across a message list (see `_message_char_len`)."""
    return sum(_message_char_len(m) for m in messages)


def collect_tool_outputs(messages: List[Any]) -> Dict[str, Any]:
    """
    Collect latest ToolMessage content per tool name.
    Normalizes string content by attempting JSON decode.
    """
    tool_payloads: Dict[str, Any] = {}
    for msg in messages:
        name = getattr(msg, "name", None)
        if isinstance(msg, ToolMessage) and isinstance(name, str):
            raw = msg.content
            normalized: Any = raw
            if isinstance(raw, str):
                try:
                    normalized = json.loads(raw)
                except Exception:
                    normalized = raw
            tool_payloads[name] = normalized
    return tool_payloads
