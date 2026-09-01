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
Model-native reasoning block handling (RUNTIME-05 Layer 2b / 2c).

Why this module exists:
- reasoning-capable models (Mistral with `reasoning_effort`, Claude extended
  thinking, DeepSeek/OpenAI-compatible gateways) interleave reasoning blocks with
  the answer inside `AIMessage(Chunk).content`
- those blocks MUST NOT leak into the plain assistant transcript, the final answer
  text, OR the assistant messages replayed to the model on the next tool-loop step
  (raw reasoning content is rejected by Mistral with HTTP 422 and pollutes context)
- they belong on the `THOUGHT_*` stream as `source="model_native"`

This lives in `support/` because both the ReAct stream/codec layer (`react/`) and
the shared tool loop (`support/tool_loop.py`) need it; `support/` is below `react/`
so there is no layering inversion.

Design note — be permissive (RFC AGENT-THINKING-API §7.3):
- the Fred catalogue routes Mistral through the OpenAI-compatible client
  (`provider: openai`, `base_url: .../v1`), so reasoning may arrive as dict-shaped
  content blocks (`type="thinking"` / `type="reasoning"`), as a top-level
  `reasoning_content`, OR as provider SDK objects (e.g. Mistral `ThinkChunk`) when
  a native client is used
- this module duck-types all of those shapes instead of importing any provider SDK,
  so a missing optional dependency never breaks the path

How to use:
- `is_thinking_block(item)` — does one content block carry model reasoning?
- `extract_thinking_text(item)` — pull the plain reasoning text out of one block
- `content_to_text(content)` — render message content as text, dropping reasoning
- `strip_reasoning_from_history(messages)` — sanitise assistant messages before replay
- `thread_reasoning_within_open_turn(messages)` — same, but keeping the current
  turn's reasoning as text. This is the #1780 reasoning-drift fix and it IS
  wired: `CheckpointHygieneMiddleware` calls it on every ReAct turn (the
  docstring said "not yet wired" long after it shipped).
"""

from __future__ import annotations

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage

# Content-block `type` discriminators that mark provider-native reasoning.
# `thinking` covers Anthropic extended thinking and Mistral `ThinkChunk`;
# `reasoning` covers OpenAI-compatible reasoning blocks.
THINKING_BLOCK_TYPES = frozenset({"thinking", "reasoning"})


def block_type(item: object) -> str | None:
    """
    Return the `type` discriminator of one content block, or None.

    Handles both dict-shaped blocks (`{"type": ...}`) and provider SDK objects
    exposing a `.type` attribute.
    """

    if isinstance(item, dict):
        candidate = item.get("type")
    else:
        candidate = getattr(item, "type", None)
    return candidate if isinstance(candidate, str) else None


def is_thinking_block(item: object) -> bool:
    """Return True when one content block carries model-native reasoning."""

    return block_type(item) in THINKING_BLOCK_TYPES


def _join_text_chunks(chunks: object) -> str:
    """
    Concatenate a nested list of text chunks into one plain string.

    Mistral wraps reasoning as `thinking: [{"type": "text", "text": "..."}]`; this
    flattens that list (and the SDK-object equivalent) into a single fragment.
    """

    if isinstance(chunks, str):
        return chunks
    if not isinstance(chunks, (list, tuple)):
        return ""
    parts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, str):
            parts.append(chunk)
        elif isinstance(chunk, dict):
            text = chunk.get("text")
            if isinstance(text, str):
                parts.append(text)
        else:
            text = getattr(chunk, "text", None)
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def extract_thinking_text(item: object) -> str:
    """
    Extract the plain reasoning text from one thinking/reasoning content block.

    Permissive across shapes:
    - dict `{"type": "thinking", "thinking": [{"text": "..."}]}` (Mistral nested)
    - dict `{"type": "thinking", "thinking": "..."}` / `{"type": "reasoning",
      "reasoning": "..."}` (string forms)
    - dict `{"type": "thinking", "text": "..."}` (Anthropic-style)
    - provider SDK object (e.g. Mistral `ThinkChunk`) exposing `.thinking`,
      `.reasoning`, or `.text`

    Returns "" when no reasoning text can be recovered.
    """

    if isinstance(item, dict):
        for key in ("thinking", "reasoning"):
            value = item.get(key)
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple)):
                joined = _join_text_chunks(value)
                if joined:
                    return joined
        text = item.get("text")
        return text if isinstance(text, str) else ""

    nested = getattr(item, "thinking", None)
    if nested is not None:
        joined = _join_text_chunks(nested)
        if joined:
            return joined
    for attr in ("reasoning", "text"):
        value = getattr(item, attr, None)
        if isinstance(value, str):
            return value
    return ""


def content_to_text(content: object, *, out_fragments: list[str] | None = None) -> str:
    """
    Render LangChain message content as one plain string, dropping reasoning blocks.

    Provider-native reasoning blocks (Mistral `ThinkChunk`, Claude thinking) are
    excluded from the returned text — they surface separately as `THOUGHT_*` events
    and must never appear as plain assistant text.

    When ``out_fragments`` is given, each reasoning block's text is appended to it so
    the caller can split reasoning from the answer in a single pass (used by the
    stream adapter); otherwise reasoning is simply dropped (used by the transcript
    codec). Non-reasoning blocks render identically in both modes.
    """

    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    rendered_parts: list[str] = []
    for item in content:
        if is_thinking_block(item):
            if out_fragments is not None:
                fragment = extract_thinking_text(item)
                if fragment:
                    out_fragments.append(fragment)
            continue
        if isinstance(item, dict) and "text" in item:
            rendered_parts.append(str(item["text"]))
        else:
            rendered_parts.append(str(item))
    return "\n".join(part for part in rendered_parts if part)


def strip_reasoning_from_history(
    messages: Sequence[BaseMessage],
) -> list[BaseMessage]:
    """
    Return a copy of the transcript safe to replay to the model.

    Why this exists (RUNTIME-05 Layer 2c):
    - reasoning-capable models leave provider reasoning blocks inside the assistant
      message stored in the LangGraph checkpoint (e.g. `content=[''], reasoning in
      additional_kwargs`, or a list of `type="thinking"` blocks)
    - on the next tool-loop step the whole transcript is replayed; Mistral rejects
      such assistant content with HTTP 422 ("content … should be a valid string")
      and replaying raw reasoning pollutes the model context

    What it does:
    - only `AIMessage` content with a list shape is collapsed to clean text (reasoning
      dropped); a `model_copy` preserves `tool_calls`, `id`, and metadata
    - `HumanMessage` / `ToolMessage` / `SystemMessage` are left untouched, so
      multimodal human content (e.g. base64 image blocks) is preserved verbatim

    The dropped reasoning is not lost for the UI — it was already streamed as
    `THOUGHT_*` events with `source="model_native"`.
    """

    sanitised: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, AIMessage) and isinstance(message.content, list):
            sanitised.append(
                message.model_copy(update={"content": content_to_text(message.content)})
            )
        else:
            sanitised.append(message)
    return sanitised


# Marker prefixing re-homed reasoning. Deliberately explicit: the text lands in
# an ordinary assistant `content` field, so the model must be able to tell its
# own recalled reasoning from something it said to the user.
RECALLED_REASONING_PREFIX = "[your reasoning so far this turn] "


def _rehome_reasoning_as_text(message: AIMessage) -> AIMessage:
    """
    Collapse one assistant message to text, KEEPING its reasoning.

    The counterpart of `strip_reasoning_from_history`'s per-message branch: same
    flattening, opposite decision about the reasoning blocks.
    """

    fragments: list[str] = []
    answer = content_to_text(message.content, out_fragments=fragments)
    reasoning = "".join(fragments).strip()
    if not reasoning:
        return message.model_copy(update={"content": answer})
    recalled = f"{RECALLED_REASONING_PREFIX}{reasoning}"
    merged = f"{recalled}\n\n{answer}" if answer else recalled
    return message.model_copy(update={"content": merged})


def thread_reasoning_within_open_turn(
    messages: Sequence[BaseMessage],
) -> list[BaseMessage]:
    """
    Replay the model's reasoning inside the turn it belongs to; strip it elsewhere.

    Why this exists (GH #1780 — root-cause fix + guardrail):
    - a reasoning model that calls a tool gets its own message back with the
      content emptied, so it re-derives the same plan and re-issues the same
      call — measured at 10/10 turns, 2.8 duplicate calls per question
    - provider-native `thinking` blocks cannot carry that reasoning back:
      `langchain_openai._format_message_content` drops them on both
      `chat/completions` and `responses`, and the native `langchain_mistralai`
      client blanks assistant content entirely whenever tool calls are present.
      An ordinary `text` block is the only channel that survives either client
    - reasoning from turns the user has already closed is NOT replayed: it costs
      context on every later request and its value expires with the question

    The open turn is everything after the last `HumanMessage` — the same
    boundary `trim_to_human_boundary` uses.

    NOT wired into `CheckpointHygieneMiddleware` yet: whether re-homed reasoning
    suppresses the duplicate calls the way verbatim replay did (p = 0.034,
    §C.6) is an open measurement. A `thinking` block is privileged context; a
    `text` block is ordinary assistant speech, and the effect may not transport.
    """

    last_human = -1
    for index, message in enumerate(messages):
        if message.type == "human":
            last_human = index

    threaded: list[BaseMessage] = []
    for index, message in enumerate(messages):
        if not (isinstance(message, AIMessage) and isinstance(message.content, list)):
            threaded.append(message)
        elif index > last_human:
            threaded.append(_rehome_reasoning_as_text(message))
        else:
            # Closed turn — same treatment as today.
            threaded.append(
                message.model_copy(update={"content": content_to_text(message.content)})
            )
    return threaded
