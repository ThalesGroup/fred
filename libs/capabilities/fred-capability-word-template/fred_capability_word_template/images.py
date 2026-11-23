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

"""The session's chat images, placed by the model as ``![caption](img:<id>)``."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from fred_capability_word_template.render import markdown_features
from fred_capability_word_template.store import (
    ImageInfo,
    get_word_template_store,
)

MAX_IMAGE_BYTES = 10 * 1024 * 1024
IMAGE_REF_PREFIX = "img:"

# The formats python-docx embeds natively, recognized by their magic bytes -
# a browser-supplied content type or file name is not trusted.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
)


def sniff_image_type(content: bytes) -> str | None:
    return next(
        (mime for magic, mime in _IMAGE_SIGNATURES if content.startswith(magic)),
        None,
    )


def image_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# --- which images a batch needs --------------------------------------------------------


def batch_image_ids(batches: Iterable[Sequence[Mapping[str, Any]]]) -> set[str]:
    """Every ``img:`` id the operations of ``batches`` place (only ``write``
    and ``insert_after`` render Markdown blocks)."""
    ids: set[str] = set()
    for batch in batches:
        for op in batch:
            if not isinstance(op, Mapping):
                continue
            if op.get("op") not in ("write", "insert_after"):
                continue
            markdown = op.get("markdown")
            if isinstance(markdown, str) and IMAGE_REF_PREFIX in markdown:
                ids.update(markdown_features(markdown).image_ids)
    return ids


async def images_for(
    session_id: str | None, batches: Iterable[Sequence[Mapping[str, Any]]]
) -> dict[str, bytes]:
    """The bytes of the images ``batches`` place, in one lookup (none when
    they place none). An unknown id is absent: validation reports it."""
    wanted = batch_image_ids(batches)
    if not wanted or not session_id:
        return {}
    return await get_word_template_store().get_images(session_id, wanted)


# --- capture ----------------------------------------------------------------------------


async def store_image(
    session_id: str,
    content: bytes,
    content_type: str,
    filename: str,
    *,
    context_text: str | None = None,
) -> ImageInfo:
    sha = await asyncio.to_thread(image_sha256, content)
    return await get_word_template_store().put_image(
        session_id,
        filename=filename[:512],
        content_type=content_type,
        sha256=sha,
        content=content,
        context_text=context_text,
    )


async def session_images(session_id: str) -> list[ImageInfo]:
    """The images attached to this conversation, oldest first."""
    return await get_word_template_store().list_images(session_id)


# --- prompt -----------------------------------------------------------------------------


def _clip(text: str, limit: int = 160) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else f"{flat[:limit]}..."


def images_fragment(images: Sequence[ImageInfo]) -> str | None:
    """The images available for the document and the rule for placing them.
    None when there are none."""
    if not images:
        return None
    lines = ["IMAGES AVAILABLE FOR THE DOCUMENT (id - file name - text next to it):"]
    for image in images:
        line = f"- {image.image_id} - {image.filename}"
        if image.context_text:
            line += f' - near: "{_clip(image.context_text)}"'
        lines.append(line)
    lines.append(
        "An image is described among the conversation's attachments under "
        "the same file name. Place an "
        "image where it illustrates the content, when the collaborator asks for "
        "it or the document calls for it: in a write or insert_after, on its own "
        "line, exactly as ![caption](img:<id>) - the caption says what the image "
        "shows, in the document's language. Copy the id exactly as listed. Never "
        "say an image was placed unless the edit that places it succeeded."
    )
    return "\n".join(lines)


__all__ = [
    "IMAGE_REF_PREFIX",
    "MAX_IMAGE_BYTES",
    "batch_image_ids",
    "image_sha256",
    "images_for",
    "images_fragment",
    "session_images",
    "sniff_image_type",
    "store_image",
]
