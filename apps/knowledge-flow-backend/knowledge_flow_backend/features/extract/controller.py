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

from fastapi import APIRouter, Depends
from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.document_scope import document_access_context
from knowledge_flow_backend.features.extract.service import (
    ExtractDocumentRequest,
    ExtractDocumentResponse,
    ExtractService,
)
from knowledge_flow_backend.security.weaver_admission import delegated_person

logger = logging.getLogger(__name__)


class ExtractController:
    """On-demand extraction for delegated callers in a readable space."""

    def __init__(self, router: APIRouter):
        self.service = ExtractService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/documents/{document_uid}/extract",
            tags=["Documents"],
            summary="Extract information from a document",
            response_model=ExtractDocumentResponse,
            operation_id="extract_document",
            description="""
        Extracts items matching an instruction from authorized published markdown,
        using bounded map calls and deduplication. Input above 2,000,000 characters
        is reduced to its first and last 1,000,000 characters and flagged truncated.
        Individual model-call failures are logged and contribute no items; they
        do not set truncated or necessarily fail the HTTP request. A successful
        response is therefore not proof of exhaustive extraction. Use a verbatim
        read when the exact source text is required.
        """,
        )
        async def extract_document(
            document_uid: str,
            request: ExtractDocumentRequest,
            context: DocumentAccessContext = Depends(document_access_context),
            user: AssertedUser = Depends(delegated_person),
        ):
            return await self.service.extract_document(user, document_uid, request, context)
