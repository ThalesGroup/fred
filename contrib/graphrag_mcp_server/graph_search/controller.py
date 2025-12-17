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
from typing import Any, Dict, List

from fastapi import APIRouter, Body, HTTPException

from graph_search.service import GraphSearchService
from graph_search.utils import GraphSearchRequest

logger = logging.getLogger(__name__)


class GraphNodeController:
    """
    FastAPI controller exposing endpoints related to the GraphSearchService
    (Graphiti + Neo4j + OpenAI).

    Clean version:
    - no authentication
    - no user handling
    """

    def __init__(self, router: APIRouter):
        self.service = GraphSearchService()
        self._register_routes(router)

    # -----------------------------------------------------
    # ROUTES REGISTRATION
    # -----------------------------------------------------
    def _register_routes(self, router: APIRouter) -> None:
        """Register all API routes for graph search."""

        @router.post(
            "/graph/search",
            tags=["GraphSearch"],
            summary="Perform a Graphiti search, optionally centered on a specific node.",
            operation_id="graph_search",
        )
        async def graph_search(req: GraphSearchRequest = Body(...)) -> List[Dict[str, Any]]:
            """
            Perform a semantic graph search using Graphiti, Neo4j and OpenAI.

            Args:
                req: GraphSearchRequest containing:
                     - query: text to search for
                     - center_uid: optional node UID to bias the search around
                     - top_k: number of results to return

            Returns:
                A list of node results as dictionaries.

            Raises:
                HTTPException: for invalid input or internal service errors.
            """
            if not req.query:
                raise HTTPException(status_code=400, detail="The 'query' field is required.")

            query = req.query
            center_uid = req.center_uid or ""
            top_k = req.top_k or 5

            try:
                results = await self.service.search_nodes(
                    query=query,
                    top_k=top_k,
                    center_uid=center_uid,
                )
                return [r.model_dump() for r in results]

            except Exception as e:
                logger.exception("Graph search failed")
                raise HTTPException(status_code=500, detail=str(e)) from e
