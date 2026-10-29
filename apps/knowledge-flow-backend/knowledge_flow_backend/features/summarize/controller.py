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
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.features.summarize.service import (
    SummarizeDocumentRequest,
    SummarizeDocumentResponse,
    SummarizeService,
)
from knowledge_flow_backend.security.weaver_admission import delegated_person

logger = logging.getLogger(__name__)


class SummarizeController:
    """
    Controller exposing on-demand, steerable document summarization.
    """

    def __init__(self, router: APIRouter):
        self.service = SummarizeService()
        self._register_routes(router)

    def _register_routes(self, router: APIRouter):
        @router.post(
            "/documents/{document_uid}/summarize",
            tags=["Documents"],
            summary="Summarize a document on demand",
            response_model=SummarizeDocumentResponse,
            description="""
        Generates a fresh, steerable summary of an already-ingested document.

        Unlike the abstract persisted at ingestion time (fixed, generic, ~180 words),
        this endpoint accepts an optional `instruction` to focus the summary (e.g.
        "focus on financial risks", "list every action item") and a `max_chars`
        budget. Large documents are summarized via map-reduce; small documents take
        a single pass. If the result still exceeds `max_chars`, one corrective pass
        rewrites it to fit.
        """,
        )
        async def summarize_document(
            document_uid: str,
            request: SummarizeDocumentRequest,
            user: AssertedUser = Depends(delegated_person),
        ):
            return await self.service.summarize_document(user, document_uid, request)
