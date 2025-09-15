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

from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, VectorSearchHit, get_current_user
from pydantic import BaseModel, Field

from app.features.vector_search.vector_search_service import VectorSearchService
from app.features.vector_search.vector_search_structures import SearchPolicy, SearchPolicyName, SearchRequest

logger = logging.getLogger(__name__)

# ---------------- Echo types for UI OpenAPI ----------------

EchoPayload = Union[SearchPolicy, SearchPolicyName]


class EchoEnvelope(BaseModel):
    kind: Literal["SearchPolicy", "SearchPolicyName"]
    payload: EchoPayload = Field(..., description="Schema payload being echoed")


class VectorSearchController:
    """
    REST + MCP tool: vector similarity search.
    Pass-through: returns List[VectorSearchHit] from the service.
    """

    def __init__(self, router: APIRouter):
        self.service = VectorSearchService()

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
        )
        def vector_search(
            request: SearchRequest,
            user: KeycloakUser = Depends(get_current_user),
        ) -> List[VectorSearchHit]:
            hits = self.service.search(
                question=request.question,
                user=user,
                top_k=request.top_k,
                document_library_tags_ids=request.document_library_tags_ids,
                policy_name=request.search_policy,
            )
            # hits is expected to be List[VectorSearchHit]
            return hits
