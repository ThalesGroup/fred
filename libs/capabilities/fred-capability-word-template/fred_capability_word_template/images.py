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

"""The session's images, placed by the model as
``![caption](img:<id>)``: attached in the chat, or extracted from an attached
Word file with the text next to them. Attachments stored before extraction
existed are backfilled the first time the images are listed.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from docx import Document
from docx.oxml.ns import qn
from sqlalchemy.exc import SQLAlchemyError

from fred_capability_word_template.render import markdown_features
from fred_capability_word_template.store import (
    AttachmentInfo,
    ImageInfo,
    get_word_template_store,
)

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class ExtractedImage:
    """One picture found in an attached Word file."""

    content: bytes
    content_type: str
    context_text: str | None
    position: int  # 1-based, in document order


# Pictures below this are icons, bullets or separators, never a diagram.
MIN_EXTRACTED_IMAGE_BYTES = 2048
_CAPTION_START_RE = re.compile(r"^\s*(figure|fig\.|schéma|schema|illustration)\b", re.I)
_MAX_CONTEXT_CHARS = 200


def _element_text(element: Any) -> str:
    return "".join(t.text or "" for t in element.iter(qn("w:t"))).strip()


def _element_style(element: Any) -> str:
    style = element.find(f"{qn('w:pPr')}/{qn('w:pStyle')}")
    return (style.get(qn("w:val")) or "") if style is not None else ""


def _is_heading_style(style_id: str) -> bool:
    lowered = style_id.lower()
    return lowered.startswith(("heading", "titre")) or lowered == "title"


def _is_caption(element: Any) -> bool:
    style = _element_style(element).lower()
    return (
        "caption" in style
        or "gende" in style
        or bool(_CAPTION_START_RE.match(_element_text(element)))
    )


def extract_docx_images(docx_bytes: bytes) -> list[ExtractedImage]:
    """Every embeddable picture in a Word file's BODY, in document order,
    each with the text that identifies it there: a caption right after it,
    else its own paragraph's text, else the nearest preceding heading, else
    the nearest preceding text. Header/footer pictures (logos), tiny ones
    and formats python-docx can't re-embed (e.g. EMF) are left out.
    CPU-bound: call it in a thread."""

    document = Document(io.BytesIO(docx_bytes))
    paragraphs = list(document.element.body.iter(qn("w:p")))
    found: list[ExtractedImage] = []
    seen: set[bytes] = set()
    last_heading = ""
    last_text = ""
    for index, element in enumerate(paragraphs):
        text = _element_text(element)
        rel_ids = [
            blip.get(qn("r:embed"))
            for blip in element.iter(qn("a:blip"))
            if blip.get(qn("r:embed"))
        ]
        for rel_id in rel_ids:
            part = document.part.related_parts.get(rel_id)
            content = getattr(part, "blob", None)
            if not content or len(content) < MIN_EXTRACTED_IMAGE_BYTES:
                continue
            content_type = sniff_image_type(content)
            if content_type is None or content in seen:
                continue
            seen.add(content)
            following = paragraphs[index + 1] if index + 1 < len(paragraphs) else None
            context = (
                _element_text(following)
                if following is not None and _is_caption(following)
                else text or last_heading or last_text
            )
            found.append(
                ExtractedImage(
                    content=content,
                    content_type=content_type,
                    context_text=context[:_MAX_CONTEXT_CHARS] or None,
                    position=len(found) + 1,
                )
            )
        if text:
            if _is_heading_style(_element_style(element)):
                last_heading = text
            last_text = text
    return found


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
    source_attachment_id: str | None = None,
) -> ImageInfo:
    sha = await asyncio.to_thread(image_sha256, content)
    return await get_word_template_store().put_image(
        session_id,
        filename=filename[:512],
        content_type=content_type,
        sha256=sha,
        content=content,
        context_text=context_text,
        source_attachment_id=source_attachment_id,
    )


async def extract_attachment_images(
    session_id: str, attachment: AttachmentInfo, content: bytes
) -> list[ImageInfo]:
    """Store every picture of an attached Word file as a session image and
    flag the attachment as extracted. Never raises: a file whose pictures
    cannot be read is flagged too (it is not parsed again)."""
    store = get_word_template_store()
    stored: list[ImageInfo] = []
    try:
        # CPU-bound (unzip + XML parse): off the event loop.
        extracted = await asyncio.to_thread(extract_docx_images, content)
        source = attachment.filename[:400]
        for image in extracted:
            if len(image.content) > MAX_IMAGE_BYTES:
                continue
            stored.append(
                await store_image(
                    session_id,
                    image.content,
                    image.content_type,
                    f"{source} - image {image.position}",
                    context_text=image.context_text,
                    source_attachment_id=attachment.attachment_id,
                )
            )
    except Exception:  # noqa: BLE001 - a malformed picture must not fail the upload
        logger.warning(
            "[WORD_TEMPLATE] session=%s pictures of %s could not be extracted",
            session_id,
            attachment.attachment_id,
            exc_info=True,
        )
    try:
        await store.mark_images_extracted(session_id, attachment.attachment_id)
    except (SQLAlchemyError, OSError):
        logger.warning(
            "[WORD_TEMPLATE] session=%s could not flag %s as extracted",
            session_id,
            attachment.attachment_id,
            exc_info=True,
        )
    if stored:
        logger.info(
            "[WORD_TEMPLATE] session=%s %d picture(s) kept from %s",
            session_id,
            len(stored),
            attachment.attachment_id,
        )
    return stored


async def session_images(
    session_id: str, attachments: Sequence[AttachmentInfo] | None = None
) -> list[ImageInfo]:
    """The session's images, oldest first, after extracting the pictures of
    any attachment not extracted yet (those stored before the images
    existed): each attachment is read once, then flagged."""
    store = get_word_template_store()
    if attachments is None:
        attachments = await store.list_attachments(session_id)
    for attachment in attachments:
        if attachment.images_extracted:
            continue
        content = await store.get_attachment_content(
            session_id, attachment.attachment_id
        )
        if content is not None:
            await extract_attachment_images(session_id, attachment, content)
    return await store.list_images(session_id)


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
        "An image attached on its own is described among the conversation's "
        "attachments under the same file name; an image taken from an attached "
        "Word file is identified by the text next to it in that file. Place an "
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
    "MIN_EXTRACTED_IMAGE_BYTES",
    "ExtractedImage",
    "batch_image_ids",
    "extract_attachment_images",
    "extract_docx_images",
    "image_sha256",
    "images_for",
    "images_fragment",
    "session_images",
    "sniff_image_type",
    "store_image",
]
