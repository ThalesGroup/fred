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

from fastapi import APIRouter, Depends, Query
from fred_core.documents.access import SpaceNotFoundError, SpacePendingDeletionError
from fred_core.documents.transport import DocumentAccessContext
from fred_core.kpi import phase_timer
from fred_core.security.delegation import AssertedUser
from fred_core.store import VectorSearchHit

from knowledge_flow_backend.application_context import get_kpi_writer
from knowledge_flow_backend.features.document_scope import document_access_context
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
            "/documents/search",
            tags=["Vector Search"],
            summary="Search documents using vectorization",
            description="Returns up to top_k ranked published chunks from the selected corpus (context space and ancestors) and explicitly listed attachments in the exact owned conversation. Two active sources use reciprocal-rank fusion with chunk deduplication; a single source preserves its ranking and scores. Fewer hits, including an empty array, are valid. No offset or pagination token. Scores depend on the search policy and are not probabilities. A hit is rechecked against publication and lifecycle facts.",
            response_model=list[VectorSearchHit],
            operation_id="search_documents",
        )
        async def vector_search(
            request: SearchRequest,
            context: DocumentAccessContext = Depends(document_access_context),
            person: AssertedUser = Depends(delegated_person),
        ) -> List[VectorSearchHit]:
            await require_space_read(person, context.space_id)
            try:
                async with phase_timer(self.kpi, "vector_search"):
                    return await self.service.search(
                        question=request.question,
                        user=person,
                        top_k=request.top_k,
                        policy_name=request.search_policy,
                        context=context,
                    )
            except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
                raise _space_error(exc) from None

        @router.get(
            "/documents/{document_uid}/chunks",
            tags=["Vector Search"],
            summary="Fetch a document's published chunks in index order",
            description="Returns chunks from the published generation of a visible corpus document or explicitly authorized conversation attachment, in chunk_index order, capped by limit (default 200, maximum 1000). No continuation token or truncation flag: reaching the limit does not establish completeness. An empty array also covers no visible chunks or a vector store without direct chunk-read support. This is not an existence check or a whole-document guarantee.",
            response_model=List[VectorSearchHit],
            operation_id="get_document_chunks",
        )
        async def get_document_chunks_ordered(
            document_uid: str,
            context: DocumentAccessContext = Depends(document_access_context),
            limit: int = Query(default=200, ge=1, le=1000),
            person: AssertedUser = Depends(delegated_person),
        ) -> List[VectorSearchHit]:
            await require_space_read(person, context.space_id)
            try:
                async with phase_timer(self.kpi, "vector_document_chunks"):
                    return await self.service.get_document_chunks_ordered(
                        user=person,
                        document_uid=document_uid,
                        context=context,
                        limit=limit,
                    )
            except (SpaceNotFoundError, SpacePendingDeletionError) as exc:
                raise _space_error(exc) from None
