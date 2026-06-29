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
Portable image re-injection for the shared ReAct-style tool loop (RUNTIME-08).

Why this module exists:
- a built-in tool such as ``attachments.read_image`` fetches image bytes and
  returns them on its ``ToolInvocationResult`` artifact (``images``), never in the
  model-visible tool text
- to let a vision-capable model actually see those pixels, the loop must hand the
  image to the model through the one transport every provider accepts: a **user**
  message content block in the OpenAI ``image_url`` data-URL shape. Images in the
  ``tool`` role are Anthropic-specific and rejected by OpenAI-compatible
  endpoints, so this is the provider-neutral path

How to use it:
- after the tool node runs, call ``build_image_injection_messages(messages)`` and
  append the returned ``HumanMessage`` list to the graph state before the next
  model call

Example:
- ``injected = build_image_injection_messages(state["messages"])``
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.messages import BaseMessage, HumanMessage, ToolMessage

logger = logging.getLogger(__name__)


def _data_url(mime_type: str, base64_data: str) -> str:
    return f"data:{mime_type};base64,{base64_data}"


def _image_blocks_from_artifact(artifact: object) -> list[dict[str, Any]]:
    """
    Build OpenAI-style ``image_url`` blocks from one tool artifact.

    Duck-typed on purpose: the artifact is normally a ``ToolInvocationResult`` with
    an ``images`` tuple of ``ToolImageContent``, but any artifact exposing the same
    ``images`` shape (``mime_type`` / ``base64_data`` / optional ``label``) works,
    and artifacts without images are simply skipped.
    """
    images = getattr(artifact, "images", None)
    if not images:
        return []
    blocks: list[dict[str, Any]] = []
    for image in images:
        mime_type = getattr(image, "mime_type", None)
        base64_data = getattr(image, "base64_data", None)
        if not isinstance(mime_type, str) or not isinstance(base64_data, str):
            continue
        if not mime_type or not base64_data:
            continue
        label = getattr(image, "label", None)
        if isinstance(label, str) and label.strip():
            blocks.append({"type": "text", "text": f"Attached image: {label}"})
        blocks.append(
            {
                "type": "image_url",
                "image_url": {"url": _data_url(mime_type, base64_data)},
            }
        )
    return blocks


def _trailing_tool_messages(messages: Sequence[BaseMessage]) -> list[ToolMessage]:
    """
    Return the contiguous run of ``ToolMessage`` at the end of ``messages``.

    Only the most-recent tool batch is considered so that an image is injected
    exactly once: on later loop passes the previously injected ``HumanMessage`` is
    not a ``ToolMessage`` and breaks the trailing run.
    """
    trailing: list[ToolMessage] = []
    for message in reversed(messages):
        if isinstance(message, ToolMessage):
            trailing.append(message)
        else:
            break
    trailing.reverse()
    return trailing


def build_image_injection_messages(
    messages: Sequence[BaseMessage],
) -> list[HumanMessage]:
    """
    Build the user-message image blocks to inject after the latest tool batch.

    Returns one ``HumanMessage`` carrying every image produced by the trailing
    tool results, or an empty list when no tool image is present. The bytes ride
    on each ``ToolMessage.artifact`` (not the model-visible tool text), so nothing
    here re-reads the tool text or leaks base64 into it.
    """
    blocks: list[dict[str, Any]] = []
    for tool_message in _trailing_tool_messages(messages):
        blocks.extend(_image_blocks_from_artifact(tool_message.artifact))
    if not blocks:
        return []
    logger.debug(
        "[MULTIMODAL] injecting %d image block(s) as a user message", len(blocks)
    )
    # cast: LangChain's content type is invariant over the block element type; our
    # OpenAI image_url blocks are valid content but don't match the exact union.
    return [HumanMessage(content=cast(Any, blocks))]
