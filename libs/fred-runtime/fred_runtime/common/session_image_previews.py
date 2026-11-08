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

"""Previews (PNG, or JPEG for photos) of a conversation's newest images, for a vision model.

The inventory comes from control-plane, the pixels from Knowledge Flow, both with the
turn's own credentials (person or delegated), like the other conversation-scoped reads.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from fred_runtime.common.kf_base_client import KfBaseClient, KnowledgeFlowAgentContext
from fred_runtime.runtime_context import get_runtime_context
from fred_runtime.runtime_support.authority import RunStopError

logger = logging.getLogger(__name__)

# Resent on every model call of the turn: past this an image keeps its description only.
_MAX_PREVIEW_BYTES = 4 * 1024 * 1024
# Inventory plus previews, before the first model call of a turn: past it, descriptions only.
_FETCH_BUDGET_S = 5.0
# An image head line of the frontend's attachments context, never a quoted description line.
_IMAGE_LINE_RE = re.compile(r"^-[ \t].*: conversation image\b", re.MULTILINE)
# Same rule as the frontend's attachments context: some stores send no or a generic mime.
_IMAGE_FILE_NAME_RE = re.compile(r"\.(png|jpe?g|gif|bmp|svg|webp|ico)\Z", re.IGNORECASE)


@dataclass(frozen=True)
class SessionImage:
    name: str
    document_uid: str
    data: bytes
    mime: str


def _not_found(result: object) -> bool:
    return (
        isinstance(result, httpx.HTTPStatusError) and result.response.status_code == 404
    )


def _sniffed_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return "image/jpeg" if data.startswith(b"\xff\xd8\xff") else None


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) read from a PNG or JPEG header, None when unreadable."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and data[12:16] == b"IHDR":
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if data[:2] != b"\xff\xd8":
        return None
    index = 2
    while index + 9 <= len(data) and data[index] == 0xFF:
        marker = data[index + 1]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height = int.from_bytes(data[index + 5 : index + 7], "big")
            width = int.from_bytes(data[index + 7 : index + 9], "big")
            return width, height
        index += 2 + int.from_bytes(data[index + 2 : index + 4], "big")
    return None


def _is_image(entry: dict[str, Any]) -> bool:
    return str(entry.get("mime") or "").startswith("image/") or bool(
        _IMAGE_FILE_NAME_RE.search(str(entry.get("name") or ""))
    )


def select_recent_images(inventory: Any, limit: int) -> list[tuple[str, str]]:
    """(name, document_uid) of the newest image attachments, newest first, one per uid."""
    if not isinstance(inventory, list):
        return []
    # Listed oldest first: created_at decides, then the later position.
    newest: dict[str, tuple[tuple[str, int], str]] = {}
    for position, entry in enumerate(inventory):
        if not (
            isinstance(entry, dict)
            and isinstance(entry.get("document_uid"), str)
            and _is_image(entry)
        ):
            continue
        uid = entry["document_uid"]
        key = (str(entry.get("created_at") or ""), position)
        if uid not in newest or key > newest[uid][0]:
            newest[uid] = (key, str(entry.get("name") or uid))
    ranked = sorted(newest.items(), key=lambda item: item[1][0], reverse=True)
    return [(name, uid) for uid, (_, name) in ranked[:limit]]


async def fetch_recent_session_images(
    agent: KnowledgeFlowAgentContext, *, limit: int
) -> list[SessionImage]:
    """Never raises for a missing or unreadable image: it is skipped with a warning.

    A `RunStopError` (lost authority, unavailable delegation) still stops the run.
    """
    context = agent.runtime_context
    team_id, session_id = context.team_id, context.session_id
    if not (team_id and session_id):
        return []
    markdown = context.attachments_markdown
    # Absent (API callers, queued messages): the session may still hold images, so ask.
    if markdown is not None and not _IMAGE_LINE_RE.search(markdown):
        return []
    try:
        return await asyncio.wait_for(
            _fetch(agent, team_id, session_id, limit), _FETCH_BUDGET_S
        )
    except TimeoutError:
        logger.warning(
            "[VISION] Image pixels skipped: fetch over %.0f s", _FETCH_BUDGET_S
        )
        return []


async def _fetch(
    agent: KnowledgeFlowAgentContext, team_id: str, session_id: str, limit: int
) -> list[SessionImage]:
    config = get_runtime_context().config
    if not config.control_plane_url or config.control_plane_http_client is None:
        logger.warning("[VISION] No control-plane client: image pixels skipped")
        return []
    inventory_client = KfBaseClient(frozenset({"GET"}), agent=agent)
    inventory_client.base_url = config.control_plane_url.rstrip("/")
    inventory_client.client = config.control_plane_http_client
    try:
        response = await inventory_client._request_with_token_refresh(
            "GET",
            f"/teams/{quote(team_id, safe='')}/sessions/{quote(session_id, safe='')}/attachments",
            phase_name="vision_attachment_inventory",
        )
        selected = select_recent_images(response.json(), limit)
    except RunStopError:
        raise
    except Exception as exc:
        if _not_found(exc):
            # API callers without a managed conversation: nothing to show.
            logger.debug("[VISION] No attachment inventory for this session")
        else:
            logger.warning(
                "[VISION] Attachment inventory unavailable: %s: %s",
                type(exc).__name__,
                exc,
            )
        return []
    if not selected:
        return []

    kf_client = KfBaseClient(frozenset({"GET"}), agent=agent)

    async def preview(document_uid: str) -> tuple[bytes, str]:
        response = await kf_client._request_with_token_refresh(
            "GET",
            f"/fast/preview/{quote(document_uid, safe='')}",
            phase_name="vision_attachment_preview",
            params={"session_id": session_id},
        )
        if len(response.content) > _MAX_PREVIEW_BYTES:
            raise ValueError(
                f"preview of {len(response.content)} bytes over the {_MAX_PREVIEW_BYTES} cap"
            )
        mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
        # Anything else (an HTML error page, corrupt bytes) would fail every turn
        # at the provider: the image keeps its description instead.
        size = image_size(response.content)
        if mime != _sniffed_mime(response.content) or not size or 0 in size:
            raise ValueError(
                f"not a readable PNG or JPEG preview ({mime or 'no type'})"
            )
        return response.content, mime

    results = await asyncio.gather(
        *(preview(uid) for _, uid in selected), return_exceptions=True
    )
    images: list[SessionImage] = []
    for (name, uid), result in zip(selected, results, strict=True):
        if isinstance(result, RunStopError):
            raise result
        if _not_found(result):
            # Attached before previews existed: its description answers instead.
            logger.debug("[VISION] Image uid=%s has no preview", uid)
        elif isinstance(result, BaseException):
            logger.warning(
                "[VISION] Image uid=%s skipped: %s: %s",
                uid,
                type(result).__name__,
                result,
            )
        else:
            images.append(
                SessionImage(
                    name=name, document_uid=uid, data=result[0], mime=result[1]
                )
            )
    return images
