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

import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from fred_core import Action, KeycloakUser, Resource, authorize

from knowledge_flow_backend.features.tag.structure import TagType
from knowledge_flow_backend.features.tag.tag_service import TagService
from knowledge_flow_backend.features.tree.structure import DocumentTreeRequest, DocumentTreeResponse
from knowledge_flow_backend.features.tree.tree_builder import build_tree, render_tree

logger = logging.getLogger(__name__)

# Matches the controller-level cap on /tags (tag_controller.py) -- high enough that
# a single call returns the whole folder structure under a prefix, no pagination.
_MAX_FOLDERS = 10_000


class TreeService:
    """
    Builds a readable, recursive folder/document listing for agent tools.

    Fred rationale:
    - Documents are organized via hierarchical tags (Tag.path/name/full_path).
      One /tags?path_prefix=... call already returns the whole folder subtree plus
      each folder's direct document ids; we only need one more batched metadata
      lookup to resolve those ids to display names. See tree_builder.py for the
      recursive nesting/rendering/pruning algorithm itself.
    """

    def __init__(self):
        from knowledge_flow_backend.features.metadata.service import MetadataService

        self.tag_service = TagService()
        self.metadata_service = MetadataService()

    @authorize(Action.READ, Resource.DOCUMENTS)
    async def get_tree(self, user: KeycloakUser, request: DocumentTreeRequest) -> DocumentTreeResponse:
        tags = await self.tag_service.list_all_tags_for_user(
            user,
            tag_type=TagType.DOCUMENT,
            path_prefix=request.working_directory,
            limit=_MAX_FOLDERS,
            owner_filter=request.owner_filter,
            team_id=request.team_id,
        )

        if request.tag_ids:
            allowed_ids = set(request.tag_ids)
            allowed_paths = {t.full_path for t in tags if t.id in allowed_ids}
            tags = [t for t in tags if t.id in allowed_ids or any(t.full_path == p or t.full_path.startswith(p + "/") for p in allowed_paths)]

        all_uids = sorted({uid for t in tags for uid in t.item_ids})
        leaves_by_uid = await self._resolve_leaves(user, all_uids)

        folders: List[Tuple[str, List[str], str]] = [(t.full_path, t.item_ids, t.id) for t in tags]
        root = build_tree(folders=folders, leaves_by_uid=leaves_by_uid)
        text, truncated = render_tree(root, max_chars=request.max_chars)
        return DocumentTreeResponse(tree=text, truncated=truncated)

    async def _resolve_leaves(self, user: KeycloakUser, document_uids: List[str]) -> Dict[str, Tuple[str, Optional[datetime]]]:
        if not document_uids:
            return {}
        docs = await self.metadata_service.get_documents_metadata(user, {"document_uid": document_uids})
        return {d.identity.document_uid: (d.identity.document_name, d.identity.created) for d in docs}
