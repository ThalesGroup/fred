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

"""Read-only document visibility checks against the Control Plane SQL facts.

`resolve_scope` is not an authorization: the caller must already have checked the
person's read permission on that space. Index metadata is never trusted here.
"""

from __future__ import annotations

from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import ARRAY, Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

_SPACE = text(
    "SELECT id, parent_id, organization_id, deletion_id FROM space WHERE id = :space_id"
).bindparams(bindparam("space_id", type_=Uuid))

_DOCUMENTS = text(
    "SELECT d.id, d.space_id, d.deletion_id, s.deletion_id AS space_deletion_id,"
    " d.retrievable, d.retrievable_pending, p.manifest"
    " FROM document d"
    " JOIN space s ON s.id = d.space_id"
    " LEFT JOIN document_processing p"
    " ON p.document_id = d.id AND p.status = 'succeeded'"
    " WHERE d.id = ANY(:document_ids)"
).bindparams(bindparam("document_ids", type_=ARRAY(Uuid)))


class SpaceNotFoundError(LookupError):
    pass


class SpacePendingDeletionError(Exception):
    pass


@dataclass(frozen=True)
class SearchScope:
    space_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class Candidate:
    document_uid: str
    chunk_uid: str


def scope_from_space(space_id: UUID, row: Mapping[Any, Any] | None) -> SearchScope:
    """Same path as the Control Plane: ancestors and the space, never children or siblings."""
    if row is None:
        raise SpaceNotFoundError(str(space_id))
    if row["deletion_id"] is not None:
        raise SpacePendingDeletionError(str(space_id))
    path: list[UUID] = []
    parent, organization = row["parent_id"], row["organization_id"]
    if parent is not None:
        if parent != organization:
            path.append(organization)
        path.append(parent)
    path.append(row["id"])
    return SearchScope(space_ids=tuple(path))


def _document_id(candidate: Candidate) -> UUID | None:
    try:
        return UUID(candidate.document_uid)
    except ValueError:
        return None


def _published_chunks(manifest: Mapping[str, Any], wanted: set[str]) -> set[str]:
    # Chunk ids cannot be inverted to ordinals, so stop once every wanted id is found.
    generation = UUID(manifest["generation"])
    found: set[str] = set()
    for ordinal in manifest["vector_ordinals"]:
        chunk_uid = str(uuid5(generation, str(ordinal)))
        if chunk_uid in wanted:
            found.add(chunk_uid)
            if len(found) == len(wanted):
                break
    return found


def is_live_document(row: Mapping[Any, Any], allowed: Container[UUID]) -> bool:
    """In scope, not retired, in an active space, retrievable with no pending inclusion."""
    return (
        row["space_id"] in allowed
        and row["deletion_id"] is None
        and row["space_deletion_id"] is None
        and bool(row["retrievable"])
        and row["retrievable_pending"] is False
    )


def filter_candidates(
    scope: SearchScope,
    candidates: Sequence[Candidate],
    documents: Iterable[Mapping[Any, Any]],
) -> list[Candidate]:
    """Keep published, live, in-scope chunks in their original order; drop the rest."""
    allowed = set(scope.space_ids)
    visible: dict[UUID, Mapping[Any, Any]] = {
        row["id"]: row
        for row in documents
        if is_live_document(row, allowed) and row["manifest"] is not None
    }
    wanted: dict[UUID, set[str]] = {}
    for candidate in candidates:
        document_id = _document_id(candidate)
        if document_id is not None and document_id in visible:
            wanted.setdefault(document_id, set()).add(candidate.chunk_uid)
    published = {
        document_id: _published_chunks(visible[document_id]["manifest"], chunks)
        for document_id, chunks in wanted.items()
    }
    kept: list[Candidate] = []
    for candidate in candidates:
        document_id = _document_id(candidate)
        if document_id is not None and candidate.chunk_uid in published.get(
            document_id, ()
        ):
            kept.append(candidate)
    return kept


async def resolve_scope(conn: AsyncConnection, space_id: UUID) -> SearchScope:
    row = (await conn.execute(_SPACE, {"space_id": space_id})).mappings().first()
    return scope_from_space(space_id, row)


async def verify_candidates(
    conn: AsyncConnection, scope: SearchScope, candidates: Sequence[Candidate]
) -> list[Candidate]:
    """Database errors propagate: a failure is not an empty, refused result."""
    document_ids = list(
        dict.fromkeys(
            document_id
            for candidate in candidates
            if (document_id := _document_id(candidate)) is not None
        )
    )
    if not document_ids:
        return []
    result = await conn.execute(_DOCUMENTS, {"document_ids": document_ids})
    return filter_candidates(scope, candidates, result.mappings().all())
