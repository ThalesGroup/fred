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

"""The session's current document, shared by the tools, the prompt and the
routes: its base plus the operation log. A persisted snapshot,
matched by a digest of the base and the log prefix it was built from, spares
the replay; without a matching one the log is replayed and the result written
back, best effort.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.exc import SQLAlchemyError

from fred_capability_word_template.images import images_for
from fred_capability_word_template.operations import replay
from fred_capability_word_template.store import (
    BaseRef,
    Batch,
    get_word_template_store,
)

logger = logging.getLogger(__name__)


class BaseUnavailable(Exception):
    """The session's base document could not be read (template not
    fetchable, attachment gone)."""


async def load_base_bytes(
    base: BaseRef,
    session_id: str | None,
    fetch_template: Callable[[str], Awaitable[bytes]],
) -> bytes:
    """The bytes of a session's base: the ONE place tools, prompt, snapshot
    replay, preview and download read them from. A library template comes
    from ``fetch_template(key)`` (the asset port in a turn, the KF blob API
    in the router); an attachment from the capability's own table. Raises
    ``BaseUnavailable``."""
    if base.kind == "template":
        try:
            return await fetch_template(base.ref)
        except BaseUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - any fetch failure (HTTP, auth, missing asset) is BaseUnavailable
            raise BaseUnavailable(f"template {base.ref} could not be fetched") from exc
    if not session_id:
        raise BaseUnavailable("an attached file needs a session")
    content = await get_word_template_store().get_attachment_content(
        session_id, base.ref
    )
    if content is None:
        raise BaseUnavailable(f"attachment {base.ref} not found")
    return content


def content_sha256(data: bytes) -> str:
    """The analysis cache key: identical bytes are analysed once."""
    return hashlib.sha256(data).hexdigest()


def log_digest(base: BaseRef, batches: Sequence[Batch]) -> str:
    """Identity of "this base with this log" (snapshots, in-pod caches)."""
    raw = json.dumps([base.identity, list(batches)], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def save_snapshot(
    session_id: str, base: BaseRef, batches: Sequence[Batch], docx: bytes
) -> None:
    """Persist ``docx`` as the session's document after ``batches``. Failures
    are logged only: a missing snapshot means a replay, nothing worse."""
    try:
        await get_word_template_store().put_snapshot(
            session_id, len(batches), log_digest(base, batches), docx
        )
    except (SQLAlchemyError, OSError):
        logger.warning(
            "[WORD_TEMPLATE] session=%s failed to store the document snapshot",
            session_id,
            exc_info=True,
        )


async def session_docx(
    session_id: str | None,
    base: BaseRef,
    batches: Sequence[Batch],
    load_base: Callable[[], Awaitable[bytes]],
) -> bytes:
    """The session's document after ``batches``. ``load_base`` (built on
    ``load_base_bytes``) is only awaited when a replay from the base is
    needed; its errors propagate, as do replay errors."""
    batches = list(batches)
    start_doc: bytes | None = None
    start = 0
    if session_id and batches:
        try:
            snapshot = await get_word_template_store().get_snapshot(session_id)
        except (SQLAlchemyError, OSError):
            logger.warning(
                "[WORD_TEMPLATE] session=%s failed to read the document snapshot",
                session_id,
                exc_info=True,
            )
            snapshot = None
        if (
            snapshot is not None
            and 0 < snapshot.seq <= len(batches)
            and snapshot.digest == log_digest(base, batches[: snapshot.seq])
        ):
            if snapshot.seq == len(batches):
                return snapshot.docx
            start_doc, start = snapshot.docx, snapshot.seq
    if start_doc is None:
        start_doc = await load_base()
    if start == len(batches):
        return start_doc  # no batch: the base as it is
    pending = batches[start:]
    # Only the images these batches place (ids are stable, never reused:
    # the digest needs no image identity).
    images = await images_for(session_id, pending)
    # CPU-bound: off the event loop that serves every turn of the pod.
    docx = await asyncio.to_thread(replay, start_doc, pending, images)
    if session_id:
        await save_snapshot(session_id, base, batches, docx)
    return docx
