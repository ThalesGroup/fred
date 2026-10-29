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

import logging
from collections import Counter
from collections.abc import Container, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import ARRAY, Uuid, bindparam, text
from sqlalchemy.ext.asyncio import AsyncConnection

from fred_core.documents.selection import DocumentScope

logger = logging.getLogger(__name__)

_SPACE = text(
    "SELECT id, parent_id, organization_id, deletion_id FROM space WHERE id = :space_id"
).bindparams(bindparam("space_id", type_=Uuid))

_DOCUMENTS = text(
    "SELECT d.id, d.folder_id, d.space_id, d.deletion_id, s.deletion_id AS space_deletion_id,"
    " d.retrievable, d.retrievable_pending,"
    " g.id AS generation_id, g.vector_ordinals"
    " FROM document d"
    " JOIN space s ON s.id = d.space_id"
    " LEFT JOIN generation g ON g.id = d.published_generation"
    " WHERE d.id = ANY(:document_ids)"
).bindparams(bindparam("document_ids", type_=ARRAY(Uuid)))


_PUBLISHED_ARTIFACT = text(
    "SELECT d.id, d.folder_id, d.space_id, d.deletion_id, s.deletion_id AS space_deletion_id,"
    " d.retrievable, d.retrievable_pending, g.prefix, a.size, a.sha256"
    " FROM document d"
    " JOIN space s ON s.id = d.space_id"
    " JOIN generation g ON g.id = d.published_generation"
    " JOIN artifact a ON a.generation_id = g.id AND a.path = :path"
    " WHERE d.id = :document_id"
).bindparams(bindparam("document_id", type_=Uuid))


_FOLDERS = text(
    "SELECT id, path FROM folder WHERE id = ANY(:folder_ids)"
    " AND space_id = ANY(:space_ids) AND deletion_id IS NULL"
).bindparams(
    bindparam("folder_ids", type_=ARRAY(Uuid)),
    bindparam("space_ids", type_=ARRAY(Uuid)),
)


@dataclass(frozen=True)
class PublishedArtifact:
    prefix: str
    size: int
    sha256: str


class SpaceNotFoundError(LookupError):
    pass


class SpacePendingDeletionError(Exception):
    pass


@dataclass(frozen=True)
class SearchScope:
    space_ids: tuple[UUID, ...]
    document_scope: DocumentScope = field(default_factory=DocumentScope)
    folder_paths: Mapping[UUID, str] = field(default_factory=dict)

    @property
    def selection_terms(self) -> tuple[dict[str, list[str]], ...]:
        """AND of unions for index prefiltering; SQL still verifies every hit."""
        return tuple(
            {
                "folder_path": [
                    self.folder_paths[id]
                    for id in selection.folder_ids
                    if id in self.folder_paths
                ],
                "document_uid": [str(id) for id in selection.document_ids],
            }
            for selection in self.document_scope.selections
        )


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


def _published_chunks(
    generation_id: UUID, vector_ordinals: Iterable[int], wanted: set[str]
) -> set[str]:
    # Chunk ids cannot be inverted to ordinals, so stop once every wanted id is found.
    found: set[str] = set()
    for ordinal in vector_ordinals:
        chunk_uid = str(uuid5(generation_id, str(ordinal)))
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
        if is_live_document(row, allowed)
        and row["generation_id"] is not None
        and (
            not scope.document_scope.selections
            or scope.document_scope.covers(row["id"], row["folder_id"])
        )
    }
    wanted: dict[UUID, set[str]] = {}
    for candidate in candidates:
        document_id = _document_id(candidate)
        if document_id is not None and document_id in visible:
            wanted.setdefault(document_id, set()).add(candidate.chunk_uid)
    published = {
        document_id: _published_chunks(
            visible[document_id]["generation_id"],
            visible[document_id]["vector_ordinals"],
            chunks,
        )
        for document_id, chunks in wanted.items()
    }
    kept: list[Candidate] = []
    dropped: Counter[str] = Counter()
    for candidate in candidates:
        document_id = _document_id(candidate)
        if document_id is not None and candidate.chunk_uid in published.get(
            document_id, ()
        ):
            kept.append(candidate)
        elif document_id is None:
            dropped["invalid_document_uid"] += 1
        elif document_id not in visible:
            dropped["document_missing_or_not_visible"] += 1
        else:
            dropped["chunk_not_published"] += 1
    logger.info(
        "[VECTOR][PUBLICATION] checked",
        extra={
            "event_name": "vector_publication_checked",
            "candidates": len(candidates),
            "kept_hits": len(kept),
            "drop_reasons": dict(dropped),
        },
    )
    return kept


async def resolve_scope(
    conn: AsyncConnection, space_id: UUID, document_scope: DocumentScope | None = None
) -> SearchScope:
    row = (await conn.execute(_SPACE, {"space_id": space_id})).mappings().first()
    scope = scope_from_space(space_id, row)
    selection = document_scope or DocumentScope()
    folder_ids = list({id for item in selection.selections for id in item.folder_ids})
    paths = {}
    if folder_ids:
        rows = (
            (
                await conn.execute(
                    _FOLDERS,
                    {"folder_ids": folder_ids, "space_ids": list(scope.space_ids)},
                )
            )
            .mappings()
            .all()
        )
        paths = {row["id"]: row["path"] for row in rows}
    # A missing/retired/out-of-space folder selects nothing, never the corpus.
    selection = selection.model_copy(
        update={
            "selections": tuple(
                item.model_copy(
                    update={
                        "folder_ids": tuple(id for id in item.folder_ids if id in paths)
                    }
                )
                for item in selection.selections
            )
        }
    )
    return replace(scope, document_scope=selection, folder_paths=paths)


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
        logger.info(
            "[VECTOR][SQL] skipped",
            extra={
                "event_name": "vector_visibility_skipped",
                "candidates": len(candidates),
                "kept_hits": 0,
                "reason": "no_valid_document_ids",
            },
        )
        return []
    result = await conn.execute(_DOCUMENTS, {"document_ids": document_ids})
    documents = result.mappings().all()
    kept = filter_candidates(scope, candidates, documents)
    # Aggregate facts only; no document content or additional database reads.
    rejected: Counter[str] = Counter()
    for row in documents:
        if row["space_id"] not in scope.space_ids:
            rejected["out_of_scope"] += 1
        if row["deletion_id"] is not None:
            rejected["document_deleted"] += 1
        if row["space_deletion_id"] is not None:
            rejected["space_deleted"] += 1
        if not row["retrievable"]:
            rejected["not_retrievable"] += 1
        if row["retrievable_pending"] is not False:
            rejected["retrievable_pending"] += 1
        if row["generation_id"] is None:
            rejected["not_published"] += 1
    logger.info(
        "[VECTOR][SQL] checked",
        extra={
            "event_name": "vector_visibility_checked",
            "candidates": len(candidates),
            "requested_documents": len(document_ids),
            "found_documents": len(documents),
            "kept_hits": len(kept),
            "rejected_hits": len(candidates) - len(kept),
            "document_rejection_facts": dict(rejected),
        },
    )
    return kept


async def published_artifact(
    conn: AsyncConnection, scope: SearchScope, document_id: UUID, path: str
) -> PublishedArtifact | None:
    """Read the published artifact and its visibility facts in one query."""
    result = await conn.execute(
        _PUBLISHED_ARTIFACT, {"document_id": document_id, "path": path}
    )
    row = result.mappings().first()
    if (
        row is None
        or not is_live_document(row, scope.space_ids)
        or (
            scope.document_scope.selections
            and not scope.document_scope.covers(document_id, row["folder_id"])
        )
    ):
        return None
    return PublishedArtifact(
        prefix=row["prefix"], size=row["size"], sha256=row["sha256"]
    )


@dataclass(frozen=True)
class PublishedDocument:
    document_id: UUID
    name: str
    source_revision: str
    artifacts: dict[str, PublishedArtifact]


_TABULAR_DOCUMENTS = text(
    "WITH page AS (SELECT d.id, d.name, d.sha256, d.folder_id, d.space_id,"
    " d.deletion_id, s.deletion_id AS space_deletion_id,"
    " d.retrievable, d.retrievable_pending, g.id AS generation_id, g.prefix"
    " FROM document d JOIN space s ON s.id = d.space_id"
    " JOIN generation g ON g.id = d.published_generation"
    " WHERE d.space_id = ANY(:space_ids) AND d.id > :after"
    " AND (:all_documents OR d.id = ANY(:document_ids))"
    " AND EXISTS (SELECT 1 FROM artifact a WHERE a.generation_id = g.id"
    " AND a.path LIKE 'datasets/%.parquet')"
    " ORDER BY d.id LIMIT 100)"
    " SELECT page.*, a.path, a.size, a.sha256 AS artifact_sha256"
    " FROM page JOIN artifact a ON a.generation_id = page.generation_id"
    " ORDER BY page.id, a.path"
).bindparams(
    bindparam("space_ids", type_=ARRAY(Uuid)),
    bindparam("document_ids", type_=ARRAY(Uuid)),
    bindparam("after", type_=Uuid),
)


async def published_tabular_documents(
    conn: AsyncConnection,
    scope: SearchScope,
    *,
    after: UUID,
    document_ids: Sequence[UUID] | None = None,
) -> tuple[list[PublishedDocument], UUID | None]:
    """One bounded page, using the same placement/lifecycle rules as other reads.

    Return the cursor of the scanned page, including refused rows. Artifacts are
    joined to one published generation in one statement, never mixed across reads.
    """
    if scope.document_scope.is_empty or document_ids == []:
        return [], None
    rows = (
        (
            await conn.execute(
                _TABULAR_DOCUMENTS,
                {
                    "space_ids": list(scope.space_ids),
                    "after": after,
                    "all_documents": document_ids is None,
                    "document_ids": list(document_ids or ()),
                },
            )
        )
        .mappings()
        .all()
    )
    documents: dict[UUID, PublishedDocument] = {}
    for row in rows:
        if not is_live_document(
            row, scope.space_ids
        ) or not scope.document_scope.covers(row["id"], row["folder_id"]):
            continue
        document = documents.setdefault(
            row["id"],
            PublishedDocument(
                document_id=row["id"],
                name=row["name"],
                source_revision=row["sha256"],
                artifacts={},
            ),
        )
        document.artifacts[row["path"]] = PublishedArtifact(
            prefix=row["prefix"],
            size=row["size"],
            sha256=row["artifact_sha256"],
        )
    return list(documents.values()), rows[-1]["id"] if rows else None
