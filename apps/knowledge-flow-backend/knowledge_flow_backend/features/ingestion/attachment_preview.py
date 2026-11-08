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

"""Chat image previews: the bounded image (PNG, or JPEG for photos) a vision chat model is shown on every turn.

Only this preview is kept, never the original file. It lives in the object area of the
content store, outside the per-document tree, and goes with the attachment's fast delete.
"""

from __future__ import annotations

import asyncio
import io
import re
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

from knowledge_flow_backend.core.stores.content.base_content_store import BaseContentStore
from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorStore, is_own_session_chunk

PREVIEW_PREFIX = "chat-attachment-previews"
_DOCUMENT_UID_RE = re.compile(r"[A-Za-z0-9_-]{1,128}")
# Every chat turn resends a preview: one past this is not kept (the description answers).
PREVIEW_MAX_BYTES = 4 * 1024 * 1024
# A slow store must not pile up blocked threads: reads past this many wait briefly, then fail.
_READ_SLOTS = 8
_READ_SLOT_WAIT_S = 0.5
_read_slots = threading.BoundedSemaphore(_READ_SLOTS)
_read_pool = ThreadPoolExecutor(max_workers=_READ_SLOTS, thread_name_prefix="kf-preview-read")


class PreviewBusyError(RuntimeError):
    """Every preview read slot stayed taken for the whole wait."""


def preview_key(document_uid: str) -> str:
    if not _DOCUMENT_UID_RE.fullmatch(document_uid):
        raise ValueError("Invalid document uid")
    return f"{PREVIEW_PREFIX}/{document_uid}"


def preview_media_type(image: bytes) -> str:
    # Only PNG and JPEG are ever stored: the bytes say which.
    return "image/jpeg" if image.startswith(b"\xff\xd8\xff") else "image/png"


def store_preview(store: BaseContentStore, document_uid: str, image: bytes) -> bool:
    """False, nothing stored, when the preview is over `PREVIEW_MAX_BYTES`."""
    if len(image) > PREVIEW_MAX_BYTES:
        return False
    store.put_object(preview_key(document_uid), io.BytesIO(image), content_type=preview_media_type(image))
    return True


def delete_preview(store: BaseContentStore, document_uid: str) -> None:
    try:
        key = preview_key(document_uid)
    except ValueError:  # malformed uid: no preview can exist under it
        return
    try:
        store.delete_object(key)
    except FileNotFoundError:  # no preview kept for this attachment
        pass


async def read_owned_preview(store: BaseContentStore, vector_store: BaseVectorStore, document_uid: str, user_id: str, session_id: str) -> tuple[bytes, str] | None:
    """(bytes, media type) of the caller's own preview, None when absent or not theirs.

    Raises `PreviewBusyError` when no read slot frees up in time.
    """
    if not _DOCUMENT_UID_RE.fullmatch(document_uid):
        return None
    deadline = time.monotonic() + _READ_SLOT_WAIT_S
    while not _read_slots.acquire(blocking=False):
        if time.monotonic() >= deadline:
            raise PreviewBusyError()
        await asyncio.sleep(0.02)
    future: Future[tuple[bytes, str] | None] = _read_pool.submit(_read_owned, store, vector_store, document_uid, user_id, session_id)
    # Freed when the blocking work really ends, not when a caller gives up waiting.
    future.add_done_callback(lambda _: _read_slots.release())
    return await asyncio.wrap_future(future)


def _read_owned(store: BaseContentStore, vector_store: BaseVectorStore, document_uid: str, user_id: str, session_id: str) -> tuple[bytes, str] | None:
    # The object read is cheap; the ownership check can list many chunks, so it comes second.
    try:
        with store.get_object_stream(preview_key(document_uid)) as stream:
            image = stream.read()
        chunks = vector_store.get_chunks_for_document(document_uid)
    except (FileNotFoundError, NotImplementedError):
        return None
    # Only the uploader, from the conversation it was attached to. Unlike delete, a
    # document without chunks is refused: there is nothing left to prove ownership.
    if any(is_own_session_chunk(chunk, user_id) and (chunk.get("metadata") or {}).get("session_id") == session_id for chunk in chunks):
        return image, preview_media_type(image)
    return None
