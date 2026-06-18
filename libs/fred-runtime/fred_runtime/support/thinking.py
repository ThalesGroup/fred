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


def content_to_text(content: object) -> str:
    """
    Render LangChain message content as one plain string, dropping reasoning blocks.

    Provider-native reasoning blocks (Mistral `ThinkChunk`, Claude thinking) are
    excluded — they surface separately as `THOUGHT_*` events and must never appear
    as plain assistant text. Non-reasoning blocks render exactly as before.
    """

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        rendered_parts: list[str] = []
        for item in content:
            if is_thinking_block(item):
                continue
            if isinstance(item, dict) and "text" in item:
                rendered_parts.append(str(item["text"]))
            else:
                rendered_parts.append(str(item))
        return "\n".join(part for part in rendered_parts if part)
    return str(content)


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
