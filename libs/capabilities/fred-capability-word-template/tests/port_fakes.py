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

"""In-memory fakes of the word_template store and the asset port, so the
tools, the middleware and the router run offline (no Postgres, no KF)."""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Collection
from datetime import UTC, datetime

from fred_capability_word_template.store import (
    AttachmentInfo,
    BaseRef,
    Batch,
    BatchAuthor,
    BatchConflict,
    BatchRecord,
    ImageInfo,
    SessionState,
    Snapshot,
    WordTemplateStore,
    Writer,
    new_attachment_id,
    new_image_id,
)
from fred_sdk.contracts.runtime import AgentAssetPort


def _now() -> datetime:
    return datetime.now(UTC)


class FakeWordTemplateStore(WordTemplateStore):
    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}
        self.batches: dict[str, list[Batch]] = {}
        self.authors: dict[str, list[BatchAuthor]] = {}
        self.analyses: dict[str, str] = {}
        self.snapshots: dict[str, Snapshot] = {}
        # session -> [(info, content)], oldest first
        self.attachments: dict[str, list[tuple[AttachmentInfo, bytes]]] = {}
        # session -> [(info, content)], oldest first
        self.images: dict[str, list[tuple[ImageInfo, bytes]]] = {}

    def _row(self, session_id: str, writer: Writer) -> SessionState:
        row = self.sessions.get(session_id)
        if row is None:
            row = SessionState(session_id=session_id, user_id=writer.user_id)
            self.sessions[session_id] = row
        row.user_id = writer.user_id
        row.team_id = writer.team_id or row.team_id
        row.agent_instance_id = writer.agent_instance_id or row.agent_instance_id
        row.updated_at = _now()
        return row

    async def get_session(self, session_id: str) -> SessionState | None:
        row = self.sessions.get(session_id)
        if row is None:
            return None
        state = copy.copy(row)
        state.batch_count = len(self.batches.get(session_id, []))
        return state

    @staticmethod
    def _set_base(row: SessionState, base: BaseRef) -> None:
        if base.kind == "attachment":
            row.attachment_id = base.ref
        else:
            row.template_key = base.ref
            row.attachment_id = None

    async def select_base(
        self, session_id: str, base: BaseRef, writer: Writer, *, expected_count: int
    ) -> None:
        if len(self.batches.get(session_id, [])) != expected_count:
            raise BatchConflict(session_id)
        self._set_base(self._row(session_id, writer), base)

    async def append_batch(
        self,
        session_id: str,
        base: BaseRef,
        operations: Batch,
        writer: Writer,
        *,
        expected_count: int,
        author: BatchAuthor = "model",
    ) -> int:
        log = self.batches.setdefault(session_id, [])
        if len(log) != expected_count:
            raise BatchConflict(session_id)
        row = self._row(session_id, writer)
        if row.pinned_at is None:
            self._set_base(row, base)
            row.pinned_at = _now()
        log.append(copy.deepcopy(operations))
        authors = self.authors.setdefault(session_id, [])
        padding: list[BatchAuthor] = ["model"] * (len(log) - 1 - len(authors))
        authors.extend(padding)
        authors.append(author)
        return len(log)

    async def list_batches(self, session_id: str) -> list[Batch]:
        return copy.deepcopy(self.batches.get(session_id, []))

    async def list_batch_records(self, session_id: str) -> list[BatchRecord]:
        authors = self.authors.get(session_id, [])
        return [
            BatchRecord(
                seq=index,
                author=authors[index - 1] if index - 1 < len(authors) else "model",
                operations=copy.deepcopy(batch),
            )
            for index, batch in enumerate(self.batches.get(session_id, []), start=1)
        ]

    async def drop_last_batch(
        self, session_id: str, *, expected_count: int | None = None
    ) -> Batch | None:
        log = self.batches.get(session_id, [])
        if expected_count is not None and len(log) != expected_count:
            raise BatchConflict(session_id)
        if not log:
            return None
        dropped = log.pop()
        authors = self.authors.get(session_id, [])
        del authors[len(log) :]
        self.snapshots.pop(session_id, None)
        if not log and session_id in self.sessions:
            self.sessions[session_id].pinned_at = None
        return dropped

    async def get_analysis(self, content_sha256: str) -> str | None:
        return self.analyses.get(content_sha256)

    async def put_analysis(self, content_sha256: str, analysis_json: str) -> None:
        self.analyses[content_sha256] = analysis_json

    async def put_attachment(
        self, session_id: str, filename: str, sha256: str, content: bytes
    ) -> AttachmentInfo:
        kept = self.attachments.setdefault(session_id, [])
        for info, _content in kept:
            if info.sha256 == sha256:
                return info
        info = AttachmentInfo(
            new_attachment_id({i.attachment_id for i, _ in kept}),
            filename,
            sha256,
            len(content),
        )
        kept.append((info, bytes(content)))
        return info

    async def list_attachments(self, session_id: str) -> list[AttachmentInfo]:
        return [info for info, _ in self.attachments.get(session_id, [])]

    async def get_attachment_content(
        self, session_id: str, attachment_id: str
    ) -> bytes | None:
        return next(
            (
                content
                for info, content in self.attachments.get(session_id, [])
                if info.attachment_id == attachment_id
            ),
            None,
        )

    async def delete_attachment(
        self, session_id: str, attachment_id: str, *, keep_image_ids: Collection[str]
    ) -> bool:
        kept = self.attachments.get(session_id, [])
        remaining = [(i, c) for i, c in kept if i.attachment_id != attachment_id]
        self.attachments[session_id] = remaining
        self.images[session_id] = [
            (info, content)
            for info, content in self.images.get(session_id, [])
            if info.source_attachment_id != attachment_id
            or info.image_id in keep_image_ids
        ]
        return len(remaining) != len(kept)

    async def delete_image(self, session_id: str, image_id: str) -> bool:
        kept = self.images.get(session_id, [])
        self.images[session_id] = [(i, c) for i, c in kept if i.image_id != image_id]
        return len(self.images[session_id]) != len(kept)

    async def mark_images_extracted(self, session_id: str, attachment_id: str) -> None:
        kept = self.attachments.get(session_id, [])
        for index, (info, content) in enumerate(kept):
            if info.attachment_id == attachment_id:
                kept[index] = (
                    dataclasses.replace(info, images_extracted=True),
                    content,
                )

    async def put_image(
        self,
        session_id: str,
        *,
        filename: str,
        content_type: str,
        sha256: str,
        content: bytes,
        context_text: str | None = None,
        source_attachment_id: str | None = None,
    ) -> ImageInfo:
        kept = self.images.setdefault(session_id, [])
        for info, _content in kept:
            if info.sha256 == sha256:
                return info
        info = ImageInfo(
            image_id=new_image_id({i.image_id for i, _ in kept}),
            filename=filename,
            content_type=content_type,
            sha256=sha256,
            size=len(content),
            context_text=context_text,
            source_attachment_id=source_attachment_id,
        )
        kept.append((info, bytes(content)))
        return info

    async def list_images(self, session_id: str) -> list[ImageInfo]:
        return [info for info, _ in self.images.get(session_id, [])]

    async def get_image(
        self, session_id: str, image_id: str
    ) -> tuple[ImageInfo, bytes] | None:
        return next(
            (
                (info, content)
                for info, content in self.images.get(session_id, [])
                if info.image_id == image_id
            ),
            None,
        )

    async def get_images(
        self, session_id: str, image_ids: Collection[str]
    ) -> dict[str, bytes]:
        return {
            info.image_id: content
            for info, content in self.images.get(session_id, [])
            if info.image_id in image_ids
        }

    async def get_snapshot(self, session_id: str) -> Snapshot | None:
        return self.snapshots.get(session_id)

    async def put_snapshot(
        self, session_id: str, seq: int, digest: str, docx: bytes
    ) -> None:
        self.snapshots[session_id] = Snapshot(seq=seq, digest=digest, docx=docx)


class FakeAssets(AgentAssetPort):
    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self.blobs: dict[str, bytes] = dict(blobs or {})
        self.store_calls: list[dict] = []
        self.fetch_calls: list[str] = []

    async def store(
        self,
        key: str,
        content: bytes,
        *,
        content_type: str | None = None,
        filename: str | None = None,
    ) -> str:
        self.store_calls.append(
            {"key": key, "content": bytes(content), "filename": filename}
        )
        self.blobs[key] = bytes(content)
        return key

    async def fetch(self, key: str) -> bytes:
        self.fetch_calls.append(key)
        return self.blobs[key]

    async def delete(self, key: str) -> None:
        self.blobs.pop(key, None)
