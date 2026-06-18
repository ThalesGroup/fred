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
Model-native reasoning block detection for ReAct streaming (RUNTIME-05 Layer 2b).

Why this module exists:
- reasoning-capable models (Mistral with `reasoning_effort`, Claude extended
  thinking, DeepSeek/OpenAI-compatible gateways) interleave reasoning blocks with
  the answer inside `AIMessageChunk.content`
- those blocks MUST NOT leak into the plain assistant transcript or the final
  answer text — they belong on the `THOUGHT_*` stream as `source="model_native"`
- both the transcript codec (`react_message_codec`) and the stream adapter
  (`react_stream_adapter`) need the same predicate to recognise a reasoning block

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

Example:
- `if is_thinking_block(block): fragment = extract_thinking_text(block)`
"""

from __future__ import annotations

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
