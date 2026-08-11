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

import logging

from fastapi import APIRouter, Depends, FastAPI
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.extract.service import (
    ExtractDocumentRequest,
    ExtractDocumentResponse,
    ExtractService,
)

logger = logging.getLogger(__name__)


class ExtractController:
    """Controller exposing on-demand exhaustive document extraction (DOCREAD-01).

    Reuses the FileNotFoundError/ValueError handlers registered by
    `SummarizeController` (same document-resolution failure modes), so it only
    registers its route.
    """

    def __init__(self, app: FastAPI, router: APIRouter):
        self.service = ExtractService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/documents/{document_uid}/extract",
            tags=["Documents"],
            summary="Exhaustively extract information from a document",
            response_model=ExtractDocumentResponse,
            description="""
        Exhaustively extracts every item matching an `instruction` from an
        already-ingested document — "list ALL the requirements", "every
        deadline". Unlike summarize (lossy, selective), this maps over EVERY
        chunk and de-duplicates the results without compressing, so nothing is
        silently dropped. The map phase runs with bounded concurrency and
        429-aware backoff, server-side, in one call.
        """,
        )
        async def extract_document(
            document_uid: str,
            request: ExtractDocumentRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            return await self.service.extract_document(user, document_uid, request)
