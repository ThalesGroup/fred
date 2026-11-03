# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded navigation over CP-owned facts, using the search admission/scope seam."""

from uuid import UUID

from fastapi import HTTPException
from fred_core.documents.access import resolve_scope
from fred_core.documents.transport import DocumentAccessContext
from fred_core.documents.tree import DocumentTreeDocument, DocumentTreeFolder, DocumentTreeSpace
from sqlalchemy import ARRAY, Uuid, bindparam, text
from sqlalchemy.dialects.postgresql import JSONB

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.document_tree.structures import DocumentTreeResponse

# Relational form of DocumentScope.covers: AND between clauses, OR within each
# clause, exact folder IDs (never descendants). resolve_scope remains the sole
# resolver of authority and live folder selections. Filter BEFORE applying limit.
_CORPUS = """
WITH selected_documents AS (
    SELECT d.document_id, d.space_id, d.folder_id, d.name, d.mime, d.created_at,
           COALESCE(f.path, '/') AS path
    FROM cp_read.document_visibility d
    LEFT JOIN cp_read.folder_path f ON f.id = d.folder_id AND f.space_id = d.space_id
    WHERE d.space_id = ANY(:space_ids) AND d.visible AND d.conversation_id IS NULL
      AND (d.folder_id IS NULL OR f.id IS NOT NULL)
      AND NOT EXISTS (
          SELECT 1 FROM jsonb_array_elements(:selections) clause
          WHERE NOT (clause->'document_ids' ? d.document_id::text
                     OR COALESCE(clause->'folder_ids' ? d.folder_id::text, false))
      )
), selected_folders AS (
    SELECT f.* FROM cp_read.folder_path f
    WHERE f.space_id = ANY(:space_ids) AND NOT EXISTS (
        SELECT 1 FROM jsonb_array_elements(:selections) clause
        WHERE NOT (clause->'folder_ids' ? f.id::text)
    )
), scoped_folders AS (
    SELECT f.* FROM cp_read.folder_path f
    JOIN cp_read.space_state s ON s.id = f.space_id AND NOT s.retired
    WHERE f.space_id = ANY(:space_ids)
      AND (EXISTS (SELECT 1 FROM selected_folders child
                   WHERE child.space_id = f.space_id AND child.path LIKE f.path || '%')
           OR EXISTS (SELECT 1 FROM selected_documents d
                      WHERE d.space_id = f.space_id AND d.path LIKE f.path || '%'))
)
"""
_BINDINGS = (
    bindparam("space_ids", type_=ARRAY(Uuid)),
    bindparam("selections", type_=JSONB),
)
# Only fixed SQL fragments are concatenated; all request values use bound parameters.
_ANCHOR = text(_CORPUS + "SELECT space_id, path FROM scoped_folders WHERE id = :folder_id").bindparams(*_BINDINGS, bindparam("folder_id", type_=Uuid))  # nosec B608
_ENTRIES = text(
    _CORPUS
    + """
, entries AS (
    SELECT 'folder' AS kind, id, space_id, path, name, NULL::uuid AS folder_id,
           NULL::text AS mime, NULL::timestamptz AS added_at
    FROM scoped_folders
    UNION ALL
    SELECT 'document', document_id, space_id, path, name, folder_id, mime, created_at
    FROM selected_documents
)
SELECT e.*, s.name AS space_name FROM entries e
JOIN cp_read.space_state s ON s.id = e.space_id AND NOT s.retired
WHERE (:anchor_space IS NULL OR e.space_id = :anchor_space) AND e.path LIKE :prefix
ORDER BY e.space_id, e.path COLLATE "C", e.kind DESC, e.name COLLATE "C", e.id
LIMIT :fetch_limit
"""  # nosec B608
).bindparams(*_BINDINGS, bindparam("anchor_space", type_=Uuid))


class DocumentTreeService:
    async def tree(
        self,
        *,
        context: DocumentAccessContext,
        user_id: str,
        authorized_space_ids: tuple[UUID, ...],
        folder_id: UUID | None,
        limit: int,
    ) -> DocumentTreeResponse:
        engine = ApplicationContext.get_instance().get_pg_async_engine()
        async with engine.connect() as conn:
            # Attachments do not participate in this operation, even if supplied.
            corpus_context = context.model_copy(update={"conversation_id": None, "attachment_ids": ()})
            scope = await resolve_scope(conn, corpus_context, user_id=user_id, authorized_space_ids=authorized_space_ids)
            params = {"space_ids": list(scope.space_ids), "selections": scope.document_scope.model_dump(mode="json")["selections"]}
            anchor = None
            if folder_id is not None:
                anchor = (await conn.execute(_ANCHOR, {**params, "folder_id": folder_id})).mappings().first()
                if anchor is None:
                    raise HTTPException(404, "folder_not_found")
            rows = (
                (
                    await conn.execute(
                        _ENTRIES,
                        {
                            **params,
                            "anchor_space": anchor["space_id"] if anchor else None,
                            "prefix": anchor["path"] + "%" if anchor else "%",
                            "fetch_limit": limit + 1,
                        },
                    )
                )
                .mappings()
                .all()
            )
        spaces: dict[UUID, DocumentTreeSpace] = {}
        folders = []
        documents = []
        for row in rows[:limit]:
            space_id = row["space_id"]
            spaces.setdefault(space_id, DocumentTreeSpace(space_id=space_id, name=row["space_name"]))
            if row["kind"] == "folder":
                path = row["path"].strip("/").split("/")
                folders.append(DocumentTreeFolder(folder_id=row["id"], space_id=space_id, parent_id=UUID(path[-2]) if len(path) > 1 else None, name=row["name"]))
            else:
                documents.append(DocumentTreeDocument(document_uid=row["id"], space_id=space_id, folder_id=row["folder_id"], name=row["name"], mime=row["mime"], added_at=row["added_at"]))
        return DocumentTreeResponse(spaces=tuple(spaces.values()), folders=tuple(folders), documents=tuple(documents), truncated=len(rows) > limit)
