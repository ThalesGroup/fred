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

`resolve_scope` applies the authorized corpus returned by Control Plane, then
checks current publication and lifecycle facts. Index metadata is never trusted here.
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
from fred_core.documents.transport import DocumentAccessContext

logger = logging.getLogger(__name__)

_SPACE = text(
    "SELECT id, retired FROM cp_read.space_state WHERE id = :space_id"
).bindparams(bindparam("space_id", type_=Uuid))

_CONVERSATION = text(
    "SELECT conversation_id FROM cp_read.conversation"
    " WHERE conversation_id = :conversation_id AND space_id = :space_id AND owner = :user_id"
).bindparams(
    bindparam("conversation_id", type_=Uuid), bindparam("space_id", type_=Uuid)
)

# Keep the Python row vocabulary local; the SQL boundary has explicit conversation names.
_DOCUMENT_FACTS = (
    "d.document_id AS id, d.folder_id, d.space_id, d.conversation_id AS session_id,"
    " d.conversation_owner AS session_user_id, d.visible, d.rejection_reasons,"
    " d.generation_id, d.vector_ordinals"
)
_DOCUMENTS = text(
    # Only literal SQL and the fixed _DOCUMENT_FACTS column list are concatenated;
    # document_ids is supplied separately as a bound parameter to execute().
    "SELECT "  # nosec B608
    + _DOCUMENT_FACTS
    + " FROM cp_read.document_visibility d WHERE d.document_id = ANY(:document_ids)"
).bindparams(bindparam("document_ids", type_=ARRAY(Uuid)))

_PUBLISHED_ARTIFACT = text(
    # _DOCUMENT_FACTS is a fixed column list; document_id and path are bound
    # parameters passed separately to execute(), never interpolated into SQL.
    "SELECT " + _DOCUMENT_FACTS + ", a.prefix, a.size, a.sha256"  # nosec B608
    " FROM cp_read.document_visibility d"
    " JOIN cp_read.published_artifact a ON a.document_id = d.document_id AND a.path = :path"
    " WHERE d.document_id = :document_id"
).bindparams(bindparam("document_id", type_=Uuid))

_FOLDERS = text(
    "SELECT id, path FROM cp_read.folder_path WHERE id = ANY(:folder_ids)"
    " AND space_id = ANY(:space_ids)"
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
    space_id: UUID
    space_ids: tuple[UUID, ...]
    document_scope: DocumentScope = field(default_factory=DocumentScope)
    folder_paths: Mapping[UUID, str] = field(default_factory=dict)
    conversation_id: UUID | None = None
    attachment_ids: tuple[UUID, ...] = ()
    user_id: str | None = None

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
    """A live corpus document in scope, retrievable with no pending inclusion."""
    return row["space_id"] in allowed and row["session_id"] is None and row["visible"]


def is_visible_document(scope: SearchScope, row: Mapping[Any, Any]) -> bool:
    """One union policy for chunks, Markdown and tabular published artifacts."""
    if row["session_id"] is None:
        return is_live_document(row, scope.space_ids) and (
            not scope.document_scope.selections
            or scope.document_scope.covers(row["id"], row["folder_id"])
        )
    return (
        scope.conversation_id is not None
        and scope.user_id is not None
        and row["session_id"] == scope.conversation_id
        and row["space_id"] == scope.space_id
        and row["id"] in scope.attachment_ids
        and row["session_user_id"] == scope.user_id
        and row["visible"]
    )


def filter_candidates(
    scope: SearchScope,
    candidates: Sequence[Candidate],
    documents: Iterable[Mapping[Any, Any]],
) -> list[Candidate]:
    """Keep published, live, in-scope chunks in their original order; drop the rest."""
    visible: dict[UUID, Mapping[Any, Any]] = {
        row["id"]: row for row in documents if is_visible_document(scope, row)
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
    conn: AsyncConnection,
    context: DocumentAccessContext,
    *,
    user_id: str,
    authorized_space_ids: tuple[UUID, ...],
) -> SearchScope:
    space_id = context.space_id
    row = (await conn.execute(_SPACE, {"space_id": space_id})).mappings().first()
    if row is None:
        raise SpaceNotFoundError(str(space_id))
    if row["retired"]:
        raise SpacePendingDeletionError(str(space_id))
    scope = SearchScope(space_id=space_id, space_ids=authorized_space_ids)
    selection = context.document_scope
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
    scope = replace(scope, document_scope=selection, folder_paths=paths)
    if context.conversation_id is not None:
        conversation = (
            (
                await conn.execute(
                    _CONVERSATION,
                    {
                        "conversation_id": context.conversation_id,
                        "space_id": space_id,
                        "user_id": user_id,
                    },
                )
            )
            .mappings()
            .first()
        )
        if conversation is not None:
            scope = replace(
                scope,
                conversation_id=context.conversation_id,
                attachment_ids=context.attachment_ids,
                user_id=user_id,
            )
            if scope.attachment_ids:
                rows = (
                    (
                        await conn.execute(
                            _DOCUMENTS, {"document_ids": list(scope.attachment_ids)}
                        )
                    )
                    .mappings()
                    .all()
                )
                scope = replace(
                    scope,
                    attachment_ids=tuple(
                        row["id"]
                        for row in rows
                        if row["session_id"] is not None
                        and is_visible_document(scope, row)
                    ),
                )
    return scope


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
        if row["session_id"] is not None and not is_visible_document(scope, row):
            rejected["attachment"] += 1
        if row["space_id"] not in scope.space_ids:
            rejected["out_of_scope"] += 1
        rejected.update(row["rejection_reasons"])
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
    if row is None or not is_visible_document(scope, row):
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
    session_id: UUID | None


_TABULAR_DOCUMENTS = text(
    # Only the fixed _DOCUMENT_FACTS column list is inserted into literal SQL;
    # all scope identifiers, pagination and filters are bound via execute().
    "WITH page AS (SELECT " + _DOCUMENT_FACTS + ", d.name, d.source_revision AS sha256"  # nosec B608
    " FROM cp_read.document_visibility d"
    " WHERE d.space_id = ANY(:space_ids) AND d.document_id > :after"
    " AND d.generation_id IS NOT NULL"
    " AND ((:include_corpus AND d.conversation_id IS NULL) OR (d.conversation_id = :conversation_id"
    " AND d.space_id = :space_id AND d.document_id = ANY(:attachment_ids)))"
    " AND (:all_documents OR d.document_id = ANY(:document_ids))"
    " AND EXISTS (SELECT 1 FROM cp_read.published_artifact a WHERE a.document_id = d.document_id"
    " AND a.path LIKE 'datasets/%.parquet')"
    " ORDER BY d.document_id LIMIT 100)"
    " SELECT page.*, a.path, a.size, a.sha256 AS artifact_sha256, a.prefix"
    " FROM page JOIN cp_read.published_artifact a ON a.document_id = page.id"
    " ORDER BY page.id, a.path"
).bindparams(
    bindparam("space_ids", type_=ARRAY(Uuid)),
    bindparam("document_ids", type_=ARRAY(Uuid)),
    bindparam("after", type_=Uuid),
    bindparam("conversation_id", type_=Uuid),
    bindparam("space_id", type_=Uuid),
    bindparam("attachment_ids", type_=ARRAY(Uuid)),
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
    if (
        scope.document_scope.is_empty and not scope.attachment_ids
    ) or document_ids == []:
        return [], None
    rows = (
        (
            await conn.execute(
                _TABULAR_DOCUMENTS,
                {
                    "space_ids": list(
                        dict.fromkeys((*scope.space_ids, scope.space_id))
                    ),
                    "after": after,
                    "include_corpus": bool(scope.space_ids)
                    and not scope.document_scope.is_empty,
                    "conversation_id": scope.conversation_id,
                    "space_id": scope.space_id,
                    "attachment_ids": list(scope.attachment_ids),
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
        if not is_visible_document(scope, row):
            continue
        document = documents.setdefault(
            row["id"],
            PublishedDocument(
                document_id=row["id"],
                name=row["name"],
                session_id=row["session_id"],
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
