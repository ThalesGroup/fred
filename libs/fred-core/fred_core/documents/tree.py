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

"""Read-only listing of the documents a search scope can return, with folder names.

Same rule as `verify_candidates`. The scope is not an authorization: the caller must
already have checked the person's read permission on that space.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ARRAY, Integer, Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from fred_core.documents.access import SearchScope, is_live_document

_SPACES = text(
    "SELECT id, kind, name FROM space WHERE id = ANY(:space_ids)"
).bindparams(bindparam("space_ids", type_=ARRAY(Uuid)))

_DOCUMENTS = text(
    "SELECT d.id, d.space_id, d.folder_id, d.name, d.mime, d.created_at,"
    " d.deletion_id, s.deletion_id AS space_deletion_id,"
    " d.retrievable, d.retrievable_pending, f.path,"
    " (p.document_id IS NOT NULL) AS published"
    " FROM document d"
    " JOIN space s ON s.id = d.space_id"
    " LEFT JOIN folder f ON f.id = d.folder_id AND f.deletion_id IS NULL"
    " LEFT JOIN document_processing p"
    " ON p.document_id = d.id AND p.status = 'succeeded'"
    " WHERE d.space_id = ANY(:space_ids)"
    # Prefilter only, so hidden documents cannot exhaust the limit; Python still decides.
    " AND d.deletion_id IS NULL AND s.deletion_id IS NULL"
    " AND d.retrievable AND d.retrievable_pending IS FALSE"
    " AND p.document_id IS NOT NULL"
    " ORDER BY d.space_id, f.path NULLS FIRST, d.name, d.id"
    " LIMIT :limit"
).bindparams(
    bindparam("space_ids", type_=ARRAY(Uuid)), bindparam("limit", type_=Integer)
)

_FOLDER_NAMES = text(
    "SELECT id, name FROM folder WHERE id = ANY(:folder_ids) AND deletion_id IS NULL"
).bindparams(bindparam("folder_ids", type_=ARRAY(Uuid)))


@dataclass(frozen=True)
class SpaceLabel:
    space_id: UUID
    kind: str
    name: str


@dataclass(frozen=True)
class VisibleDocument:
    document_uid: str
    name: str
    mime: str
    added_at: datetime
    space_id: UUID
    folder_ids: tuple[UUID, ...]
    folder_names: tuple[str, ...]


@dataclass(frozen=True)
class DocumentListing:
    spaces: tuple[SpaceLabel, ...]
    documents: tuple[VisibleDocument, ...]
    truncated: bool


def folder_chain(row: Mapping[Any, Any]) -> tuple[UUID, ...] | None:
    """Folder ids from the space root down to the document; None when undecidable."""
    if row["folder_id"] is None:
        return ()
    if row["path"] is None:
        return None
    try:
        chain = tuple(UUID(part) for part in row["path"].strip("/").split("/"))
    except ValueError:
        return None
    return chain if chain[-1] == row["folder_id"] else None


def visible_rows(
    scope: SearchScope, rows: Iterable[Mapping[Any, Any]]
) -> list[tuple[Mapping[Any, Any], tuple[UUID, ...]]]:
    """Keep live, published documents whose folder path is known, in row order."""
    allowed = set(scope.space_ids)
    kept: list[tuple[Mapping[Any, Any], tuple[UUID, ...]]] = []
    for row in rows:
        if not (is_live_document(row, allowed) and row["published"]):
            continue
        chain = folder_chain(row)
        if chain is not None:
            kept.append((row, chain))
    return kept


def build_documents(
    kept: Iterable[tuple[Mapping[Any, Any], tuple[UUID, ...]]],
    names: Mapping[UUID, str],
) -> tuple[VisibleDocument, ...]:
    """Name each folder chain; a document with an unnamed ancestor is dropped."""
    return tuple(
        VisibleDocument(
            document_uid=str(row["id"]),
            name=row["name"],
            mime=row["mime"],
            added_at=row["created_at"],
            space_id=row["space_id"],
            folder_ids=chain,
            folder_names=tuple(names[folder_id] for folder_id in chain),
        )
        for row, chain in kept
        if all(folder_id in names for folder_id in chain)
    )


def space_labels(
    scope: SearchScope, rows: Iterable[Mapping[Any, Any]]
) -> tuple[SpaceLabel, ...]:
    by_id = {row["id"]: row for row in rows}
    return tuple(
        SpaceLabel(space_id, str(by_id[space_id]["kind"]), by_id[space_id]["name"])
        for space_id in scope.space_ids
        if space_id in by_id
    )


async def list_visible_documents(
    conn: AsyncConnection, scope: SearchScope, *, max_rows: int = 2000
) -> DocumentListing:
    """Database errors propagate: a failure is not an empty listing."""
    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    space_ids = list(scope.space_ids)
    spaces = (await conn.execute(_SPACES, {"space_ids": space_ids})).mappings().all()
    result = await conn.execute(
        _DOCUMENTS, {"space_ids": space_ids, "limit": max_rows + 1}
    )
    # One extra row is read so truncation is detected, never guessed.
    rows = result.mappings().all()
    truncated = len(rows) > max_rows
    kept = visible_rows(scope, rows[:max_rows])
    folder_ids = list(dict.fromkeys(f for _, chain in kept for f in chain))
    names: dict[UUID, str] = {}
    if folder_ids:
        named = await conn.execute(_FOLDER_NAMES, {"folder_ids": folder_ids})
        names = {row["id"]: row["name"] for row in named.mappings().all()}
    return DocumentListing(
        spaces=space_labels(scope, spaces),
        documents=build_documents(kept, names),
        truncated=truncated,
    )
