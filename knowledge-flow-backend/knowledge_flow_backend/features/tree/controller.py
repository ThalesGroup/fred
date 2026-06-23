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

from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.tree.service import TreeService
from knowledge_flow_backend.features.tree.structure import DocumentTreeRequest, DocumentTreeResponse

logger = logging.getLogger(__name__)


class TreeController:
    """
    Controller exposing a recursive, readable folder/document listing.
    """

    def __init__(self, router: APIRouter):
        self.service = TreeService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/documents/tree",
            tags=["Documents"],
            summary="List documents and folders as a readable tree",
            response_model=DocumentTreeResponse,
            description="""
        Returns a recursive listing of folders (hierarchical document tags) and the
        documents within them, rendered as indented text starting from
        `working_directory` (root when unset).

        A document belonging to several folders appears as a leaf under each one.
        When the rendering would exceed `max_chars`, the deepest branches are pruned
        first and `truncated` is set to true -- callers should narrow
        `working_directory` or use vector search instead of trying to browse
        everything.
        """,
        )
        async def get_document_tree(
            request: DocumentTreeRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            return await self.service.get_tree(user, request)
