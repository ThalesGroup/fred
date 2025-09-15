# Copyright Thales 2025
# Licensed under the Apache License, Version 2.0 (the "License");
# ...

import logging
from typing import List

from fastapi import APIRouter, Depends
from fred_core import KeycloakUser, VectorSearchHit, get_current_user

from app.features.vector_search.vector_search_service import VectorSearchService
from app.features.vector_search.vector_search_structures import SearchRequest

logger = logging.getLogger(__name__)


class VectorSearchController:
    """
    REST + MCP tool: vector similarity search.
    Pass-through: returns List[VectorSearchHit] from the service.
    """

    def __init__(self, router: APIRouter):
        self.service = VectorSearchService()

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
            )
            # hits is expected to be List[VectorSearchHit]
            return hits
