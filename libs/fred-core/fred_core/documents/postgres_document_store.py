# Copyright Thales 2025
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

from __future__ import annotations

import logging
from typing import Any, List, Optional, cast

from pydantic import ValidationError
from sqlalchemy import (
    BigInteger,
    CursorResult,
    bindparam,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.document_store import (
    BaseDocumentMetadataStore,
    DocumentMetadataDeserializationError,
)
from fred_core.documents.document_structures import (
    DocumentMetadata,
    ProcessingStage,
    ProcessingStatus,
)
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory, use_session

logger = logging.getLogger(__name__)

# Chunk size for `bulk_mark_vector_done`'s `WHERE document_uid IN (...)` batches --
# bounds each statement's parameter count for very large repairs (e.g. ~10,000
# document_uids) while the whole call still runs inside one transaction.
_BULK_UPDATE_CHUNK_SIZE = 2000


class PostgresDocumentMetadataStore(BaseDocumentMetadataStore):
    """PostgreSQL-backed document metadata store using declarative ORM."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)
        self._is_postgres = engine.dialect.name == "postgresql"

    # ---------- helpers ----------

    @staticmethod
    def _to_dict(md: DocumentMetadata) -> dict[str, Any]:
        return md.model_dump(mode="json")

    @staticmethod
    def _from_row(row: DocumentMetadataRow) -> DocumentMetadata:
        try:
            return DocumentMetadata.model_validate(row.doc or {})
        except ValidationError as e:
            raise DocumentMetadataDeserializationError(
                f"Invalid metadata JSON: {e}"
            ) from e

    @staticmethod
    def _require_uid(md: DocumentMetadata) -> str:
        uid = md.identity.document_uid
        if not uid:
            raise ValueError("Metadata must contain a 'document_uid'")
        return uid

    # ---------- reads ----------

    async def count_all(self, session: AsyncSession | None = None) -> int:
        """Return total number of document metadata records (current live count)."""
        async with use_session(self._sessions, session) as s:
            result = await s.execute(
                select(func.count()).select_from(DocumentMetadataRow)
            )
            return int(result.scalar_one())

    async def count_by_team(
        self, team_id: str, session: AsyncSession | None = None
    ) -> int:
        """Count documents owned by one team.

        A document's team is indirect: `DocumentMetadataRow` has no `team_id`
        column, only `tag_ids` — a document belongs to a team through the
        `owner_id` of one of its tags (`TagRow`, same table/engine, no
        cross-database join needed). `owner_id` is taken verbatim, including
        personal-space ids (`personal-<uid>`) — the same convention
        knowledge-flow already uses when stamping `document.created_total`/
        `document.deleted_total` KPI events with `dims.team_id`
        (`features/metadata/service.py`), so a document counts for a personal
        space the same way it counts for a real team. See
        `NOTES-OBSERV-02-FOLLOWUPS.md` #1.
        """
        async with use_session(self._sessions, session) as s:
            team_tag_ids = (
                (
                    await s.execute(
                        select(TagRow.tag_id).where(TagRow.owner_id == team_id)
                    )
                )
                .scalars()
                .all()
            )
            if not team_tag_ids:
                return 0

            if self._is_postgres:
                cond: ColumnElement[bool] = cast(
                    ColumnElement[bool],
                    DocumentMetadataRow.tag_ids.overlap(list(team_tag_ids)),
                )
                result = await s.execute(
                    select(func.count()).select_from(DocumentMetadataRow).where(cond)
                )
                return int(result.scalar_one())

            # SQLite (tests): no native array overlap operator — filter in Python.
            wanted = set(team_tag_ids)
            rows = (
                (await s.execute(select(DocumentMetadataRow.tag_ids))).scalars().all()
            )
            return sum(1 for tag_ids in rows if wanted.intersection(tag_ids or []))

    async def get_metadata_by_uid(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> Optional[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            row = await s.get(DocumentMetadataRow, document_uid)
        return self._from_row(row) if row else None

    async def get_metadata_by_uids(
        self, document_uids: list[str], session: AsyncSession | None = None
    ) -> list[DocumentMetadata]:
        """Return metadata for a targeted uid list with one SQL query."""
        unique_uids = list(dict.fromkeys(document_uids))
        if not unique_uids:
            return []

        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(DocumentMetadataRow).where(
                            DocumentMetadataRow.document_uid.in_(unique_uids)
                        )
                    )
                )
                .scalars()
                .all()
            )

        row_by_uid = {row.document_uid: row for row in rows}
        return [
            self._from_row(row_by_uid[document_uid])
            for document_uid in unique_uids
            if document_uid in row_by_uid
        ]

    async def list_by_source_tag(
        self, source_tag: str, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            rows = (
                (
                    await s.execute(
                        select(DocumentMetadataRow).where(
                            DocumentMetadataRow.source_tag == source_tag
                        )
                    )
                )
                .scalars()
                .all()
            )
        return [self._from_row(row) for row in rows]

    async def get_metadata_in_tag(
        self, tag_id: str, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(
                ColumnElement[bool], DocumentMetadataRow.tag_ids.contains([tag_id])
            )
            async with use_session(self._sessions, session) as s:
                rows = (
                    (await s.execute(select(DocumentMetadataRow).where(cond)))
                    .scalars()
                    .all()
                )
            return [self._from_row(row) for row in rows]

        # SQLite: load all and filter in Python
        docs = await self.get_all_metadata(filters={}, session=session)
        return [md for md in docs if tag_id in (md.tags.tag_ids or [])]

    async def browse_metadata_in_tag(
        self,
        tag_id: str,
        offset: int = 0,
        limit: int = 50,
        session: AsyncSession | None = None,
    ) -> tuple[list[DocumentMetadata], int]:
        if self._is_postgres:
            cond: ColumnElement[bool] = cast(
                ColumnElement[bool], DocumentMetadataRow.tag_ids.contains([tag_id])
            )
            async with use_session(self._sessions, session) as s:
                total_result = await s.execute(
                    select(func.count()).select_from(DocumentMetadataRow).where(cond)
                )
                total = total_result.scalar_one()
                rows = (
                    (
                        await s.execute(
                            select(DocumentMetadataRow)
                            .where(cond)
                            .limit(limit)
                            .offset(offset)
                        )
                    )
                    .scalars()
                    .all()
                )
            return [self._from_row(row) for row in rows], int(total)

        # SQLite: filter in Python
        docs = await self.get_all_metadata(filters={}, session=session)
        filtered = [md for md in docs if tag_id in (md.tags.tag_ids or [])]
        return filtered[offset : offset + limit], len(filtered)

    async def total_size_by_tags(
        self, tag_ids: List[str], session: AsyncSession | None = None
    ) -> dict[str, int]:
        unique = list(dict.fromkeys(tag_ids))
        if not unique:
            return {}
        # SQLite in tests has no array overlap operator — fall back to the
        # per-tag Python sum in the base class.
        if not self._is_postgres:
            return await super().total_size_by_tags(unique, session=session)

        wanted = set(unique)
        # `file_size_bytes` lives inside the JSONB `doc` blob; extract + cast so
        # the whole tag's size is summed in one query, no pagination, no per-doc
        # metadata deserialization.
        size_expr = func.coalesce(
            sql_cast(
                DocumentMetadataRow.doc["file"]["file_size_bytes"].astext, BigInteger
            ),
            0,
        )
        # Array overlap (`&&`) hits the GIN index, so only documents in one of the
        # requested tags are scanned; a document may carry several of them.
        cond = cast(ColumnElement[bool], DocumentMetadataRow.tag_ids.overlap(unique))
        result: dict[str, int] = {tag_id: 0 for tag_id in unique}
        async with use_session(self._sessions, session) as s:
            rows = (
                await s.execute(
                    select(DocumentMetadataRow.tag_ids, size_expr).where(cond)
                )
            ).all()
        for row_tags, size in rows:
            for tag_id in row_tags or []:
                if tag_id in wanted:
                    result[tag_id] += int(size or 0)
        return result

    async def get_all_metadata(
        self, filters: dict, session: AsyncSession | None = None
    ) -> List[DocumentMetadata]:
        async with use_session(self._sessions, session) as s:
            rows = (await s.execute(select(DocumentMetadataRow))).scalars().all()
        docs = [self._from_row(row) for row in rows]
        return [
            md for md in docs if self._match_nested(md.model_dump(mode="json"), filters)
        ]

    # ---------- writes ----------

    async def save_metadata(
        self, metadata: DocumentMetadata, session: AsyncSession | None = None
    ) -> None:
        uid = self._require_uid(metadata)
        async with use_session(self._sessions, session) as s:
            row = await s.get(DocumentMetadataRow, uid)
            if row is None:
                row = DocumentMetadataRow(document_uid=uid)
                s.add(row)
            self._apply(row, metadata)

    async def update_metadata(
        self, metadata: DocumentMetadata, session: AsyncSession | None = None
    ) -> bool:
        """Update one metadata row, reporting whether the document still existed.

        A single conditional UPDATE rather than `get` + save: a writer that
        outlived the document's deletion (see the base-class contract) must not
        be able to re-create it, and a read-then-write only narrows that window
        instead of closing it.
        """
        uid = self._require_uid(metadata)
        async with use_session(self._sessions, session) as s:
            # cast: AsyncSession.execute is typed as returning Result, but a DML
            # statement always yields a CursorResult, which is what carries rowcount.
            result = cast(
                CursorResult[Any],
                await s.execute(
                    update(DocumentMetadataRow)
                    .where(DocumentMetadataRow.document_uid == uid)
                    .values(
                        source_tag=metadata.source.source_tag,
                        date_added_to_kb=metadata.source.date_added_to_kb,
                        tag_ids=list(metadata.tags.tag_ids or []),
                        doc=self._to_dict(metadata),
                    )
                ),
            )
            return result.rowcount > 0

    def _apply(self, row: DocumentMetadataRow, metadata: DocumentMetadata) -> None:
        """Copy a metadata payload onto a row — the column list `update_metadata`
        must stay in sync with."""
        row.source_tag = metadata.source.source_tag
        row.date_added_to_kb = metadata.source.date_added_to_kb
        row.tag_ids = list(metadata.tags.tag_ids or [])
        row.doc = self._to_dict(metadata)

    async def bulk_mark_vector_done(
        self,
        source_tag: str,
        document_uids: list[str],
        session: AsyncSession | None = None,
    ) -> list[str]:
        """Atomically set `processing.stages.vector = done` and clear any
        `processing.errors.vector` for exactly these document_uids -- nothing else
        in `doc` (identity, source, tags, ACL, other stages/errors, extensions,
        business timestamps) is touched. `processing`/`processing.stages` are
        created if the document's JSON doesn't have them yet (`jsonb_set(...,
        create_missing=true)` alone does NOT create missing *intermediate* parent
        objects in PostgreSQL -- only the final path element -- so this builds the
        `processing` object explicitly via `COALESCE(...) || jsonb_build_object(...)`
        instead of relying on that).

        `source_tag` re-scopes the `WHERE` clause at write time, not just at the
        caller's earlier scan time (`WHERE source_tag = :source_tag AND
        document_uid IN (...)`): a document whose `source_tag` changed between the
        scan and this write is out of scope and must not be silently repaired.

        One transaction for the whole call, chunked into bounded
        `WHERE ... IN (...)` statements (`_BULK_UPDATE_CHUNK_SIZE`) so a single call
        stays well clear of practical statement-parameter limits even at ~10,000
        uids: if any chunk's UPDATE fails, or either postcondition below fails, the
        whole call raises before returning -- the caller's transaction (this
        method's own, when `session` is None; see `use_session`) rolls back
        entirely, so a partially-applied repair can never be observed.

        Postconditions checked before returning (both required, both raise on
        failure so the caller rolls back):
          1. every requested document_uid was actually found under `source_tag` --
             an absent uid, or one whose `source_tag` no longer matches, fails the
             whole batch rather than being silently skipped.
          2. every updated document_uid reads back `processing.stages.vector ==
             "done"` -- a defensive read-back check, independent of the UPDATE
             statement's own correctness.

        Semantically idempotent: re-running with the same `source_tag` and uids
        converges to the same end state. This is not a guaranteed physical no-op --
        PostgreSQL may still rewrite a row even when the JSON value it computes is
        unchanged -- only that the observable result is identical.
        """
        unique_uids = list(dict.fromkeys(document_uids))
        if not unique_uids:
            return []

        async with use_session(self._sessions, session) as s:
            if self._is_postgres:
                update_stmt = text(
                    """
                    UPDATE metadata
                    SET doc = doc || jsonb_build_object(
                        'processing',
                        COALESCE(doc->'processing', '{}'::jsonb)
                        || jsonb_build_object(
                            'stages',
                            COALESCE(doc->'processing'->'stages', '{}'::jsonb) || jsonb_build_object('vector', 'done')
                        )
                        || jsonb_build_object(
                            'errors',
                            COALESCE(doc->'processing'->'errors', '{}'::jsonb) - 'vector'
                        )
                    )
                    WHERE source_tag = :source_tag
                      AND document_uid IN :uids
                    RETURNING document_uid
                    """
                ).bindparams(bindparam("uids", expanding=True))
                updated: list[str] = []
                for i in range(0, len(unique_uids), _BULK_UPDATE_CHUNK_SIZE):
                    chunk = unique_uids[i : i + _BULK_UPDATE_CHUNK_SIZE]
                    result = await s.execute(
                        update_stmt, {"source_tag": source_tag, "uids": chunk}
                    )
                    updated.extend(row[0] for row in result.fetchall())

                missing = set(unique_uids) - set(updated)
                if missing:
                    raise RuntimeError(
                        f"bulk_mark_vector_done: {len(missing)} document_uid(s) not found under "
                        f"source_tag={source_tag!r} (absent, or its source_tag changed since the "
                        "scan) -- rolling back the whole repair batch instead of applying a partial one."
                    )

                verify_stmt = text(
                    """
                    SELECT document_uid
                    FROM metadata
                    WHERE document_uid IN :uids
                      AND doc #>> '{processing,stages,vector}' = 'done'
                    """
                ).bindparams(bindparam("uids", expanding=True))
                verified: set[str] = set()
                for i in range(0, len(updated), _BULK_UPDATE_CHUNK_SIZE):
                    chunk = updated[i : i + _BULK_UPDATE_CHUNK_SIZE]
                    result = await s.execute(verify_stmt, {"uids": chunk})
                    verified.update(row[0] for row in result.fetchall())
                not_verified = set(updated) - verified
                if not_verified:
                    raise RuntimeError(
                        f"bulk_mark_vector_done: {len(not_verified)} document_uid(s) did not read back "
                        "processing.stages.vector == 'done' after the update -- rolling back the whole "
                        "repair batch."
                    )

                return updated

            # SQLite (tests): no jsonb `||`/`#>>` operators used above -- per-row
            # read/modify/write in the same transaction, applying the identical
            # source_tag scoping and postcondition checks the Postgres path
            # enforces directly in SQL.
            rows = (
                (
                    await s.execute(
                        select(DocumentMetadataRow).where(
                            DocumentMetadataRow.document_uid.in_(unique_uids),
                            DocumentMetadataRow.source_tag == source_tag,
                        )
                    )
                )
                .scalars()
                .all()
            )
            found_by_uid = {row.document_uid: row for row in rows}
            missing = set(unique_uids) - set(found_by_uid)
            if missing:
                raise RuntimeError(
                    f"bulk_mark_vector_done: {len(missing)} document_uid(s) not found under "
                    f"source_tag={source_tag!r} (absent, or its source_tag changed since the "
                    "scan) -- rolling back the whole repair batch instead of applying a partial one."
                )

            updated = []
            for document_uid, row in found_by_uid.items():
                metadata = self._from_row(row)
                metadata.processing.mark_done(ProcessingStage.VECTORIZED)
                row.doc = self._to_dict(metadata)
                updated.append(document_uid)

            not_verified = [
                document_uid
                for document_uid in updated
                if (found_by_uid[document_uid].doc or {})
                .get("processing", {})
                .get("stages", {})
                .get(ProcessingStage.VECTORIZED.value)
                != ProcessingStatus.DONE.value
            ]
            if not_verified:
                raise RuntimeError(
                    f"bulk_mark_vector_done: {len(not_verified)} document_uid(s) did not read back "
                    "processing.stages.vector == 'done' after the update -- rolling back the whole "
                    "repair batch."
                )

            return updated

    async def delete_metadata(
        self, document_uid: str, session: AsyncSession | None = None
    ) -> bool:
        """Delete one metadata row, reporting whether this call removed it.

        A single conditional DELETE rather than `get` + `delete`: the row carries
        no `version_id_col`, so two concurrent callers could both load it and both
        "succeed", and each would then release the document's storage quota — the
        same bytes credited twice (#2149). Exactly one caller can observe
        `rowcount == 1`, so exactly one releases.
        """
        async with use_session(self._sessions, session) as s:
            # cast: AsyncSession.execute is typed as returning Result, but a DML
            # statement always yields a CursorResult, which is what carries rowcount.
            result = cast(
                CursorResult[Any],
                await s.execute(
                    delete(DocumentMetadataRow).where(
                        DocumentMetadataRow.document_uid == document_uid
                    )
                ),
            )
            return result.rowcount > 0

    async def clear(self, session: AsyncSession | None = None) -> None:
        async with use_session(self._sessions, session) as s:
            await s.execute(delete(DocumentMetadataRow))

    # ---------- nested filter helper ----------

    def _match_nested(self, item: dict, filter_dict: dict) -> bool:
        """
        Recursively match a filter dict against a nested dict (string-compare for robustness).
        Mirrors the DuckDB/OpenSearch semantics to keep callers consistent.
        """
        for key, value in filter_dict.items():
            if key == "processing_stages" and isinstance(value, dict):
                stages = item.get("processing", {}).get("stages", {})
                if not isinstance(stages, dict):
                    return False

                for stage_key, expected in value.items():
                    current = stages.get(stage_key)
                    if isinstance(expected, list):
                        if isinstance(current, list):
                            if not any(str(c) in map(str, expected) for c in current):
                                return False
                        else:
                            if str(current) not in map(str, expected):
                                return False
                    else:
                        if str(current) != str(expected):
                            return False
                continue

            if isinstance(value, dict):
                sub = item.get(key, {})
                if not isinstance(sub, dict) or not self._match_nested(sub, value):
                    return False
            else:
                cur = item.get(key, None)
                if cur is None:
                    if key in {"document_name", "document_uid"}:
                        cur = item.get("identity", {}).get(key)
                    elif key in {"source_tag", "retrievable"}:
                        cur = item.get("source", {}).get(key)
                    elif key == "tag_ids":
                        cur = item.get("tags", {}).get("tag_ids")

                if isinstance(value, list):
                    if isinstance(cur, list):
                        if not any(str(c) in map(str, value) for c in cur):
                            return False
                    else:
                        if str(cur) not in map(str, value):
                            return False
                else:
                    if str(cur) != str(value):
                        return False

        return True
