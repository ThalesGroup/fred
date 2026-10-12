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

import asyncio
import base64
import hashlib
import json
import logging
import sys
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

from fred_core import KeycloakUser
from fred_core.documents.document_store import DocumentDiscoveryEntry
from fred_core.documents.document_structures import DocumentMetadata
from pydantic import BaseModel, ConfigDict, ValidationError

from knowledge_flow_backend.features.corpus_tree.structure import DocumentTreeRequest, DocumentTreeResponse
from knowledge_flow_backend.features.corpus_tree.tree_builder import DocLeaf, build_tree, prune_empty_folders, render_tree
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.structure import Tag, TagType
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)

# Matches the controller-level cap on /tags (tag_controller.py) -- high enough that
# a single call returns the whole folder structure under a prefix, no pagination.
_MAX_FOLDERS = 10_000


class InvalidTreePage(ValueError):
    def __init__(self, message: str, reason: str = "invalid_cursor") -> None:
        super().__init__(message)
        self.reason = reason


class _TreePosition(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    version: int
    query: str
    uid: str
    value: str | None


def _query_fingerprint(user: KeycloakUser, request: DocumentTreeRequest) -> str:
    fields = request.model_dump(exclude={"max_chars", "limit", "cursor"})
    fields["caller"] = user.uid
    fields["name_filter"] = (request.name_filter or "").lower()
    fields["working_directory"] = TagService._normalize_path(request.working_directory or "")
    for key in ("tag_ids", "document_uids"):
        fields[key] = sorted(set(fields[key] or ()))
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def _decode_cursor(cursor: str, fingerprint: str, sort_by: str) -> tuple[str | None, str]:
    try:
        position = _TreePosition.model_validate_json(base64.b64decode(cursor, altchars=b"-_", validate=True))
        if position.version != 1 or position.query != fingerprint or not position.uid:
            raise ValueError("Cursor does not match this query or scope")
        if sort_by == "name" and position.value is None:
            raise ValueError("Invalid name position")
        if sort_by == "added_to_kb" and position.value is not None:
            value = datetime.fromisoformat(position.value)
            if value.tzinfo is None:
                raise ValueError("Arrival position requires timezone")
        return position.value, position.uid
    except (ValueError, ValidationError) as exc:
        raise InvalidTreePage("Invalid cursor. Restart with the same query and scope without a cursor.") from exc


def _encode_cursor(entry: DocumentDiscoveryEntry, fingerprint: str) -> str:
    value = _TreePosition(version=1, query=fingerprint, uid=entry.document.document_uid, value=entry.sort_value)
    return base64.urlsafe_b64encode(value.model_dump_json().encode()).decode()


def _leaf(document: DocumentMetadata) -> DocLeaf:
    return DocLeaf(
        document_uid=document.document_uid,
        document_name=document.document_name,
        created=document.identity.created,
        added_to_kb=document.source.date_added_to_kb if "date_added_to_kb" in document.source.model_fields_set else None,
        modified=document.identity.modified,
        title=document.identity.title,
        file_type=document.file.file_type.value,
        mime_type=document.file.mime_type,
        language=document.file.language,
        page_count=document.file.page_count,
        row_count=document.file.row_count,
        labels=document.labels,
        source=document.source.source_tag,
    )


def _selected_folders(tags: Sequence[Tag], requested: Sequence[str]) -> list[str]:
    requested_ids = set(requested)
    paths = {tag.full_path for tag in tags if tag.id in requested_ids}
    selected = []
    for tag in tags:
        segments = tag.full_path.split("/")
        if any("/".join(segments[:depth]) in paths for depth in range(1, len(segments) + 1)):
            selected.append(tag.id)
    return selected


def _render_page(tags: Sequence[Tag], entries: list[DocumentDiscoveryEntry], max_chars: int, selected_folder_ids: set[str] | None = None, explicit_uids: set[str] | None = None) -> tuple[str, int]:
    if not entries:
        return "(empty)", 0
    by_id = {tag.id: tag for tag in tags}

    def render(count: int) -> str:
        docs = [entry.document for entry in entries[:count]]
        members: dict[str, list[str]] = {}
        for doc in docs:
            for tag_id in doc.tags.tag_ids or ():
                if tag_id in by_id and (selected_folder_ids is None or tag_id in selected_folder_ids or doc.document_uid in (explicit_uids or ())):
                    members.setdefault(tag_id, []).append(doc.document_uid)
        folders = [(by_id[tag_id].full_path, uids, tag_id) for tag_id, uids in members.items()]
        root = build_tree(folders=folders, leaves_by_uid={doc.document_uid: _leaf(doc) for doc in docs})
        prune_empty_folders(root)
        return render_tree(root, max_chars=sys.maxsize)[0]

    low, high = 0, len(entries)
    best = ""
    while low < high:
        middle = (low + high + 1) // 2
        text = render(middle)
        if len(text) <= max_chars:
            low, best = middle, text
        else:
            high = middle - 1
    if low == 0:
        raise InvalidTreePage("One document cannot fit max_chars. Increase max_chars (up to 60000) or narrow working_directory.", reason="budget_exceeded")
    return best, low


class CorpusTreeService:
    """
    Read-only navigation/projection over the already-ingested corpus, rendered
    as a readable folder/document listing for agent tools.

    Bounded context: this is corpus navigation, not a filesystem. It never
    stores bytes and never mutates anything — every document it lists was
    already ingested. It is intentionally distinct from the future
    `WorkspaceService` (mutable, persistent user/agent files, currently
    implemented under the `/fs` routes — see FILESYSTEM.md "Bounded
    contexts"). Do not add write, quota, or provenance behavior here; that
    domain belongs to Workspace.

    Fred rationale:
    - Documents are organized via hierarchical tags (Tag.path/name/full_path).
      One tag listing already returns the whole folder subtree plus each folder's
      direct document ids; we only need one more batched metadata lookup to
      resolve those ids to display names. See tree_builder.py for the recursive
      nesting/rendering/pruning algorithm itself.
    - Authorization goes through the same ReBAC chokepoints as vector search:
      `TagService.list_all_tags_for_user` (owner_filter/team_id scoped, incl. the
      service_agent branch) decides which folders are visible, and
      `MetadataService.get_documents_by_uids` ReBAC-filters the leaves (indexed
      `document_uid IN (...)`, not a full-table scan — see its docstring). The
      tree is derived from the authorized tag set — never store-enumerated and
      filtered after — so a caller cannot see folders across team boundaries.

    No business-label filtering here, deliberately: a folder tree renders
    every folder in scope, and mixing in a "find documents by label"
    narrowing pulls two different questions ("where is X in the corpus" vs
    "give me every document labeled X") into one tool with a size-budgeted,
    non-exhaustive response shape — the wrong shape for the second question.
    Label resolution lives entirely in `MetadataService.get_document_uids_with_any_label`/
    `get_documents_with_label_page`, consumed by the separate, admin-gated
    `document_label_search` capability (`fred-runtime`), not this one.
    """

    def __init__(self):
        self.tag_service = TagService()
        self.metadata_service = MetadataService()

    async def get_tree(self, user: KeycloakUser, request: DocumentTreeRequest) -> DocumentTreeResponse:
        if request.limit is not None:
            return await self._get_page(user, request)
        tags = await self.tag_service.list_all_tags_for_user(
            user,
            tag_type=TagType.DOCUMENT,
            path_prefix=request.working_directory,
            limit=_MAX_FOLDERS,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )

        scoped = tags
        if request.tag_ids:
            allowed_ids = set(request.tag_ids)
            allowed_paths = {t.full_path for t in tags if t.id in allowed_ids}
            scoped = [t for t in tags if t.id in allowed_ids or any(t.full_path == p or t.full_path.startswith(p + "/") for p in allowed_paths)]

        # A library scope and a document scope UNION, they do not intersect -- the
        # same semantics vector search applies (`vector_search_service`: library
        # hits and document hits are merged). Ticking a library and one document
        # elsewhere means "that library, plus that document", never "the document
        # only if it happens to sit in that library".
        selected_uids = set(request.document_uids or ())
        in_scope_uids: Optional[set] = None
        if selected_uids:
            scoped_ids = {t.id for t in scoped}
            in_scope_uids = selected_uids
            if request.tag_ids:
                in_scope_uids = in_scope_uids | {uid for t in scoped for uid in t.item_ids}
            scoped = [t for t in tags if t.id in scoped_ids or (selected_uids & set(t.item_ids))]

        folders: List[Tuple[str, List[str], str]] = [(t.full_path, t.item_ids, t.id) for t in scoped]

        all_uids = sorted({uid for _, item_ids, _ in folders for uid in item_ids})
        if in_scope_uids is not None:
            # Narrowing the resolved leaves narrows the tree on its own:
            # `build_tree` skips any uid it cannot resolve to a name.
            all_uids = [uid for uid in all_uids if uid in in_scope_uids]
        leaves_by_uid = await self._resolve_leaves(user, all_uids)

        root = build_tree(folders=folders, leaves_by_uid=leaves_by_uid)
        if in_scope_uids is not None:
            prune_empty_folders(root)
        text, truncated = await asyncio.to_thread(render_tree, root, max_chars=request.max_chars)
        return DocumentTreeResponse(tree=text, truncated=truncated)

    async def _get_page(self, user: KeycloakUser, request: DocumentTreeRequest) -> DocumentTreeResponse:
        limit = request.limit
        assert limit is not None
        fingerprint = _query_fingerprint(user, request)
        after = _decode_cursor(request.cursor, fingerprint, request.sort_by) if request.cursor else None
        tags = await self.tag_service.list_tag_descriptors_for_user(
            user,
            tag_type=TagType.DOCUMENT,
            path_prefix=request.working_directory,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )
        selected = None
        if request.tag_ids:
            selected = await asyncio.to_thread(_selected_folders, tags, request.tag_ids)
        elif request.document_uids:
            selected = []
        entries, unknown = await self.metadata_service.discover_documents_page(
            user,
            folder_ids=[tag.id for tag in tags],
            selected_folder_ids=selected,
            document_uids=request.document_uids,
            name_filter=request.name_filter,
            sort_by=request.sort_by,
            sort_order=request.sort_order,
            limit=limit + 1,
            after=after,
        )
        text, emitted = await asyncio.to_thread(_render_page, tags, entries[:limit], request.max_chars, None if selected is None else set(selected), set(request.document_uids or ()))
        next_cursor = _encode_cursor(entries[emitted - 1], fingerprint) if emitted and emitted < len(entries) else None
        return DocumentTreeResponse(tree=text, truncated=emitted < min(limit, len(entries)), next_cursor=next_cursor, has_unknown_arrivals=unknown if request.sort_by == "added_to_kb" else None)

    async def _resolve_leaves(self, user: KeycloakUser, document_uids: List[str]) -> Dict[str, DocLeaf]:
        if not document_uids:
            return {}
        # `get_documents_by_uids` -> `get_metadata_by_uids` chunks its
        # `document_uid IN (...)` query internally (`_BULK_UPDATE_CHUNK_SIZE`),
        # so even a tree spanning the full `_MAX_FOLDERS` (10,000 folders)
        # cannot approach a driver bind-parameter ceiling.
        docs = await self.metadata_service.get_documents_by_uids(user, document_uids)
        return {document.document_uid: _leaf(document) for document in docs}
