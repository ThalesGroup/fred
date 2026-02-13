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
from typing import List, Literal, Union

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fred_core import KeycloakUser, VectorSearchHit, get_current_user
from fred_core.kpi import phase_timer
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import get_kpi_writer
from knowledge_flow_backend.features.vector_search.vector_search_service import VectorSearchService
from knowledge_flow_backend.features.vector_search.vector_search_structures import RerankRequest, SearchPolicyName, SearchRequest

logger = logging.getLogger(__name__)

# ---------------- Echo types for UI OpenAPI ----------------

EchoPayload = Union[SearchPolicyName]


class EchoEnvelope(BaseModel):
    kind: Literal["SearchPolicyName"]
    payload: EchoPayload = Field(..., description="Schema payload being echoed")


class VectorSearchController:
    """
    REST + MCP tool: vector similarity search.
    Pass-through: returns List[VectorSearchHit] from the service.
    """

    def __init__(self, router: APIRouter):
        self.service = VectorSearchService()
        self.kpi = get_kpi_writer()

        @router.post(
            "/schemas/echo",
            tags=["Schemas"],
            summary="Ignore. Not a real endpoint.",
            description="Ignore. This endpoint is only used to include some types (mainly one used in websocket) in the OpenAPI spec, so they can be generated as typescript types for the UI. This endpoint is not really used, this is just a code generation hack.",
        )
        def echo_schema(envelope: EchoEnvelope) -> None:
            pass

        @router.post(
            "/vector/search",
            tags=["Vector Search"],
            summary="Search documents using vectorization",
            description="Returns ranked VectorSearchHit objects for the query.",
            response_model=list[VectorSearchHit],
            operation_id="search_documents_using_vectorization",
            responses={status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Internal server error", "content": {"application/json": {"example": {"detail": "An error occurred during search"}}}}},
        )
        async def vector_search(
            request: SearchRequest,
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[VectorSearchHit]:
            try:
                async with phase_timer(self.kpi, "vector_search"):
                    hits = await self.service.search(
                        question=request.question,
                        user=user,
                        top_k=request.top_k,
                        document_library_tags_ids=request.document_library_tags_ids,
                        document_uids=request.document_uids,
                        policy_name=request.search_policy,
                        session_id=request.session_id,
                        include_session_scope=request.include_session_scope,
                        include_corpus_scope=request.include_corpus_scope,
                    )
                return hits
            except Exception as e:
                raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

        @router.post(
            "/vector/test",
            summary="Test endpoint that always returns a successful dummy response.",
            description="A simple test endpoint for POST requests. Returns a fixed list of VectorSearchHit.",
            response_model=list[VectorSearchHit],
            operation_id="test_post_success",
        )
        def test_post_success(
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[VectorSearchHit]:
            """Always succeeds and returns a dummy VectorSearchHit."""
            logger.info("SECURITY: test_post_success called by user: %s", user.username)

            # Construct a dummy hit to ensure the return type matches the schema
            dummy_hit = VectorSearchHit(content="This is a test document chunk.", uid="test-doc-001", title="Dummy Test Document", score=0.99, rank=1, type="test")

            return [dummy_hit]

        @router.post(
            "/vector/rerank",
            tags=["Vector Search"],
            summary="Sort documents according to their relevance",
            description="Returns a list of VectorSearchHit sorted by relevance",
            response_model=List[VectorSearchHit],
            operation_id="rerank_documents",
            status_code=status.HTTP_200_OK,
        )
        async def rerank(
            request: RerankRequest,
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[VectorSearchHit]:
            async with phase_timer(self.kpi, "vector_rerank"):
                documents = await run_in_threadpool(
                    self.service.rerank_documents,
                    question=request.question,
                    documents=request.documents,
                    top_r=request.top_r,
                )
            return documents
