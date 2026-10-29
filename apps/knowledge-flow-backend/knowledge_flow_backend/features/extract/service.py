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

"""On-demand extraction over published markdown using Swift map-reduce."""

import logging
import time

from fred_core.documents.transport import DocumentAccessContext
from fred_core.security.delegation import AssertedUser
from pydantic import BaseModel, ConfigDict, Field

from knowledge_flow_backend.features.content.published_markdown import published_markdown
from knowledge_flow_backend.features.extract.extractor import DocumentExtractor

logger = logging.getLogger(__name__)


class ExtractDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(
        min_length=1,
        description="What to extract exhaustively, e.g. 'every functional requirement', 'all deadlines and their context'.",
    )


class ExtractDocumentResponse(BaseModel):
    document_uid: str
    extraction: str = Field(description="Consolidated, de-duplicated list of every extracted item (markdown bullets), in document order.")
    item_count: int
    chunks_processed: int = Field(description="Number of map windows attempted, not the number of successful model calls or source chunks.")
    truncated: bool = Field(description="True only when input exceeded the 2,000,000-character cap and was head/tail-windowed. Does not report individual model-call failures.")


class ExtractService:
    def _build_extractor(self) -> DocumentExtractor:
        return DocumentExtractor()

    async def extract_document(self, user: AssertedUser, document_uid: str, request: ExtractDocumentRequest, context: DocumentAccessContext) -> ExtractDocumentResponse:
        started = time.monotonic()
        text = await published_markdown(user, context.space_id, document_uid, context.document_scope)
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
