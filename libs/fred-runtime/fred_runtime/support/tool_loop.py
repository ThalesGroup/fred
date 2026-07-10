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
- the ReAct middleware frame (`react/react_middleware.py`,
  `CheckpointHygieneMiddleware`) applies them to the model input on every call

History note (#1972):
- this module used to also host the hand-rolled 4-node ReAct StateGraph
  (`build_tool_loop`); that loop was replaced by LangChain `create_agent` plus
  the platform middleware frame, and the node logic was re-homed into
  `react/react_middleware.py`. Only the pure helpers remain here.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)


def sanitize_dangling_tool_calls(messages: List[Any]) -> List[Any]:
    """
    Remove any AIMessage(tool_calls=...) whose call_ids are not all answered
    by immediately-following ToolMessages.

    Why this exists:
    - When a turn crashes mid-flight (e.g. OpenAI 400 on a previous call), the
      LangGraph checkpoint stores the user message and the assistant tool_call
      request, but never the tool result. Every subsequent turn then loads that
      poisoned checkpoint state and OpenAI rejects the payload with:
        "tool_call_ids did not have response messages: <id>"
    - Sanitizing here is the only safe place: it covers both the in-memory
      and persisted checkpoint paths, regardless of whether history restore
      ran or was skipped.

    What it does:
    - Walk through messages in order.
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


def trim_to_human_boundary(messages: list, max_messages: int) -> list:
    """
    Keep the last `max_messages` entries, then scan forward to the first
    HumanMessage so the context never starts mid tool-call/result pair.
    """
    if len(messages) <= max_messages:
        return messages
    trimmed = messages[-max_messages:]
    for i, msg in enumerate(trimmed):
        if isinstance(msg, HumanMessage):
            return trimmed[i:]
    return trimmed


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
