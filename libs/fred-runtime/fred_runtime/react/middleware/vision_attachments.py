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

"""VisionAttachmentsMiddleware - the conversation's newest images, for a vision model."""

from __future__ import annotations

import asyncio
import base64
import logging
import math
from collections.abc import Awaitable, Callable, Collection
from typing import Protocol, runtime_checkable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage

from fred_runtime.common.session_image_previews import SessionImage, image_size
from fred_runtime.runtime_support.authority import RunStopError

logger = logging.getLogger(__name__)

# Older images keep only their description in the attachments context.
MAX_VISION_IMAGES = 5
_PREFACE = (
    "[Pixels of the most recent images attached to this conversation, "
    "newest first. Look at them directly instead of searching for them.]"
)
PIXELS_ONLY_LINE = "Pixels included in this conversation; no text description provided."
# Where the model-written part of a Knowledge Flow image summary starts: limits
# note, vision summary, or the no-description line. Header and SVG facts precede it.
_DESCRIPTION_STARTS = (
    "Limits: this description was written once",
    "Vision summary:",
    "No visual description is available for this image",
)
_SUMMARY_INDENT = "    "
# Description lines are quoted (`    > text`, empty `    >`) so none reads as an attachment.
_QUOTED_LINE = f"{_SUMMARY_INDENT}>"
_NAME_LINE = "Image attachment: {name}"
# History-budget cost of one image: ~width*height/750 tokens at the preview's
# 1568 px long edge, in characters at the 1.35 chars/token ratio the budget
# (`_V2_MAX_HISTORY_CHARS`) is calibrated on.
_PREVIEW_MAX_EDGE_PX = 1568
_PIXELS_PER_TOKEN = 750
_CHARS_PER_TOKEN = 1.35
# Client errors that never mean "this request's content was refused".
_NOT_A_CONTENT_REFUSAL = frozenset({401, 403, 429})


@runtime_checkable
class SessionImageSource(Protocol):
    async def recent_session_images(self, limit: int) -> list[SessionImage]: ...


class VisionAttachmentsMiddleware(AgentMiddleware):
    """
    Adds the newest image attachments to the FIRST user message of every model
    call: a stable request prefix keeps provider prompt caching while the set is
    unchanged. Request-scoped, fetched once per turn, never checkpointed.
    """

    def __init__(
        self,
        *,
        source: SessionImageSource,
        session_id: str | None = None,
    ) -> None:
        super().__init__()
        self._source = source
        self._session_id = session_id
        self._blocks: list[dict] | None = None
        self._chars = 0
        self._uids: frozenset[str] = frozenset()
        self._lock = asyncio.Lock()

    async def _image_blocks(self) -> list[dict]:
        async with self._lock:
            if self._blocks is None:
                images = await self._source.recent_session_images(MAX_VISION_IMAGES)
                self._blocks = _blocks(images)
                self._chars = _images_chars(images)
                self._uids = frozenset(image.document_uid for image in images)
                if images:
                    logger.info(
                        "[VISION] %d image(s) selected for the model requests: session=%s uids=%s",
                        len(images),
                        self._session_id,
                        ",".join(sorted(self._uids)),
                    )
            return self._blocks

    async def reserved_chars(self) -> int:
        """History-budget characters the images of this turn will take."""
        await self._image_blocks()
        return self._chars

    def release(self) -> None:
        """No pixels and no omitted description for the rest of this turn."""
        self._blocks, self._chars = [], 0

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        blocks = await self._image_blocks()
        if not blocks:
            return await handler(request)
        messages: list[AnyMessage] = list(request.messages)
        index = next(
            (i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), None
        )
        if index is None:
            return await handler(request)
        messages[index] = _with_blocks(message=messages[index], blocks=blocks)
        try:
            return await handler(
                request.override(
                    messages=messages,
                    system_message=self._system_message(request.system_message),
                )
            )
        except Exception as exc:
            status = _content_refusal_status(exc)
            if status is None:
                raise
            # A provider refusing images must not break the conversation for good:
            # the rest of the turn goes without pixels, descriptions intact.
            logger.warning(
                "[VISION] Model refused a request with %d image(s) (%s, status %d): "
                "retrying without pixels; session=%s uids=%s",
                len(self._uids),
                type(exc).__name__,
                status,
                self._session_id,
                ",".join(sorted(self._uids)),
            )
            self.release()
            return await handler(request)

    def _system_message(self, message: SystemMessage | None) -> SystemMessage | None:
        # The description of an image sent as pixels competes with what the model
        # sees, so it is left out.
        if message is None or not isinstance(message.content, str):
            return message
        rewritten = omit_pixel_image_descriptions(message.content, self._uids)
        if rewritten == message.content:
            return message
        return message.model_copy(update={"content": rewritten})


def _content_refusal_status(exc: BaseException) -> int | None:
    """The provider's 4xx status when it may have refused the images, else None."""
    if isinstance(exc, RunStopError):
        return None
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int) and 400 <= status < 500:
        return None if status in _NOT_A_CONTENT_REFUSAL else status
    return None


def omit_pixel_image_descriptions(text: str, document_uids: Collection[str]) -> str:
    """Drop the vision description of each listed image, keeping its header and SVG facts."""
    markers = tuple(f"[{uid}]" for uid in document_uids if uid)
    if not markers:
        return text
    lines = text.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        out.append(line)
        index += 1
        if not (line.startswith("- ") and any(marker in line for marker in markers)):
            continue
        end = index
        while end < len(lines) and lines[end].startswith(_SUMMARY_INDENT):
            end += 1
        block = lines[index:end]
        cut = next(
            (
                i
                for i, row in enumerate(block)
                if _unquoted(row).startswith(_DESCRIPTION_STARTS)
            ),
            None,
        )
        if cut is not None:
            kept = block[:cut]
            while kept and not _unquoted(kept[-1]):
                kept.pop()
            spacer = [_QUOTED_LINE] if kept else []
            block = [*kept, *spacer, f"{_QUOTED_LINE} {PIXELS_ONLY_LINE}"]
        out.extend(block)
        index = end
    return "\n".join(out)


def _unquoted(row: str) -> str:
    return row.strip().removeprefix(">").strip()


def image_chars(data: bytes) -> int:
    """Conservative history-budget cost of one image, in characters."""
    width, height = image_size(data) or (_PREVIEW_MAX_EDGE_PX, _PREVIEW_MAX_EDGE_PX)
    scale = min(1.0, _PREVIEW_MAX_EDGE_PX / max(width, height, 1))
    tokens = (width * scale) * (height * scale) / _PIXELS_PER_TOKEN
    return math.ceil(tokens * _CHARS_PER_TOKEN)


def _images_chars(images: list[SessionImage]) -> int:
    """History-budget cost of the blocks `_blocks` builds for these images."""
    if not images:
        return 0
    return len(_PREFACE) + sum(
        len(_NAME_LINE.format(name=image.name)) + image_chars(image.data)
        for image in images
    )


def _blocks(images: list[SessionImage]) -> list[dict]:
    if not images:
        return []
    blocks: list[dict] = [{"type": "text", "text": _PREFACE}]
    for image in images:
        url = f"data:{image.mime};base64,{base64.b64encode(image.data).decode('ascii')}"
        blocks.append({"type": "text", "text": _NAME_LINE.format(name=image.name)})
        blocks.append({"type": "image_url", "image_url": {"url": url}})
    return blocks


def _with_blocks(message: AnyMessage, blocks: list[dict]) -> AnyMessage:
    content = message.content
    head: list[str | dict] = (
        [{"type": "text", "text": content}]
        if isinstance(content, str)
        else list(content)
    )
    return message.model_copy(update={"content": [*head, *blocks]})
