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

"""
On-demand exhaustive document extraction (DOCREAD-01 Phase 2).

The server-side counterpart to the agent's `extract_from_document` tool: instead
of the agent paging the whole document into its own context (many token-heavy
model calls, the original client-side 429 cause), it makes ONE call here and the
map-reduce over every chunk — with bounded concurrency and 429 backoff — runs
server-side. Document text is resolved through `SummarizeService` so the
corpus/session-attachment access rules live in exactly one place.
"""

import logging
import time

from fred_core import KeycloakUser
from pydantic import BaseModel, Field

from knowledge_flow_backend.features.extract.extractor import DocumentExtractor
from knowledge_flow_backend.features.summarize.service import SummarizeService

logger = logging.getLogger(__name__)


class ExtractDocumentRequest(BaseModel):
    instruction: str = Field(
        min_length=1,
        description="What to extract exhaustively, e.g. 'every functional requirement', 'all deadlines and their context'.",
    )


class ExtractDocumentResponse(BaseModel):
    document_uid: str
    extraction: str = Field(description="Consolidated, de-duplicated list of every extracted item (markdown bullets), in document order.")
    item_count: int
    chunks_processed: int
    truncated: bool = Field(description="True if the document exceeded the processing cap and was head/tail-windowed.")


class ExtractService:
    def __init__(self) -> None:
        # Reused purely for its (security-sensitive) document-text resolution.
        self._summarize = SummarizeService()

    def _build_extractor(self) -> DocumentExtractor:
        return DocumentExtractor()

    async def extract_document(self, user: KeycloakUser, document_uid: str, request: ExtractDocumentRequest) -> ExtractDocumentResponse:
        started = time.monotonic()
        text = await self._summarize.get_document_text(user, document_uid)
        extractor = self._build_extractor()
        result = await extractor.extract(text=text, instruction=request.instruction)
        logger.info(
            "[EXTRACT] %s items=%d chunks=%d truncated=%s total_ms=%.0f",
            document_uid,
            result.item_count,
            result.chunks_processed,
            result.truncated,
            (time.monotonic() - started) * 1000,
        )
        return ExtractDocumentResponse(
            document_uid=document_uid,
            extraction=result.text,
            item_count=result.item_count,
            chunks_processed=result.chunks_processed,
            truncated=result.truncated,
        )
