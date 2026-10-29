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
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fred_core.documents.access import SpaceNotFoundError, SpacePendingDeletionError
from fred_core.kpi import phase_timer
from fred_core.security.delegation import AssertedUser
from fred_core.store import VectorSearchHit

from knowledge_flow_backend.application_context import get_kpi_writer
from knowledge_flow_backend.features.vector_search.vector_search_service import VectorSearchService
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchRequest
from knowledge_flow_backend.security.weaver_admission import _space_error, delegated_person, require_space_read

logger = logging.getLogger(__name__)


class VectorSearchController:
    """Corpus search for capabilities, in the space of the calling agent turn."""

    def __init__(self, router: APIRouter):
        self.service = VectorSearchService()
        self.kpi = get_kpi_writer()

        @router.post(
            "/vector/search",
            tags=["Vector Search"],
            summary="Search documents using vectorization",
            description="Returns ranked hits from the space and its ancestors, published documents only.",
            response_model=list[VectorSearchHit],
            operation_id="search_documents_using_vectorization",
        )
        async def vector_search(
            request: SearchRequest,
            person: AssertedUser = Depends(delegated_person),
        ) -> List[VectorSearchHit]:
            await require_space_read(person, request.space_id)
            try:
                async with phase_timer(self.kpi, "vector_search"):
                    return await self.service.search(
                        question=request.question,
                        user=person,
                        top_k=request.top_k,
                        policy_name=request.search_policy,
                        space_id=request.space_id,
                    )
            except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
                raise _space_error(exc) from None

        @router.get(
            "/vector/document-chunks",
            tags=["Vector Search"],
            summary="Fetch a document's published chunks in index order",
            description="Returns a whole table intact; the document must be published in the space or its ancestors.",
            response_model=List[VectorSearchHit],
            operation_id="get_document_chunks_ordered",
        )
        async def get_document_chunks_ordered(
            document_uid: str,
            space_id: UUID,
            limit: int = Query(default=200, ge=1, le=1000),
            person: AssertedUser = Depends(delegated_person),
        ) -> List[VectorSearchHit]:
            await require_space_read(person, space_id)
            try:
                async with phase_timer(self.kpi, "vector_document_chunks"):
                    return await self.service.get_document_chunks_ordered(
                        user=person,
                        document_uid=document_uid,
                        space_id=space_id,
                        limit=limit,
                    )
            except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
                raise _space_error(exc) from None
