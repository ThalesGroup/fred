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

import asyncio
import logging
from typing import List, Optional

from fred_core import KeycloakUser
from langchain_core.documents import Document
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.core.processors.output.summarizer.smart_llm_summarizer import SmartDocSummarizer

logger = logging.getLogger(__name__)


class SummarizeDocumentRequest(BaseModel):
    instruction: Optional[str] = Field(
        default=None,
        description="Free-text instruction steering the summary: focus area, audience, what to look for, desired length/tone.",
    )
    max_chars: int = Field(
        default=2000,
        ge=200,
        le=20_000,
        description="Target ceiling for the returned summary length, in characters.",
    )


class SummarizeDocumentResponse(BaseModel):
    document_uid: str
    summary: str
    shrunk_for_budget: bool = Field(description="True if a corrective pass had to shrink the summary to fit max_chars.")
    keywords: List[str] = Field(default_factory=list)


class SummarizeService:
    """
    On-demand, steerable document summarization.

    Fred rationale:
    - Reuses the same size-aware map-reduce summarizer used at ingestion time
      (SmartDocSummarizer), so there is exactly one summarization implementation,
      now instruction-aware. The persisted ingestion-time abstract stays fixed
      and generic; this path is for callers (agents) who need a deep, targeted
      summary on demand.
    """

    def __init__(self):
        from knowledge_flow_backend.features.content.content_service import ContentService

        self.content_service = ContentService()
        self.context = ApplicationContext.get_instance()

    def _build_summarizer(self) -> SmartDocSummarizer:
        return SmartDocSummarizer(
            model_config=self.context.configuration.chat_model,
            splitter=self.context.get_text_splitter(),
        )

    async def summarize_document(self, user: KeycloakUser, document_uid: str, request: SummarizeDocumentRequest) -> SummarizeDocumentResponse:
        markdown = await self.content_service.get_markdown_preview(user, document_uid)
        document = Document(page_content=markdown, metadata={})

        summarizer = self._build_summarizer()
        # SmartDocSummarizer is synchronous (LLM calls via .invoke()); offload so it
        # doesn't block the event loop, matching vector_search_service.py's pattern.
        abstract, keywords = await asyncio.to_thread(summarizer.summarize_document, document, instruction=request.instruction)
        abstract = abstract or ""

        shrunk = False
        if len(abstract) > request.max_chars:
            shrink_instruction = f"This summary is currently ~{len(abstract)} characters; rewrite it to fit within ~{request.max_chars} characters while preserving the key points."
            try:
                abstract = await asyncio.to_thread(summarizer.summarize_abstract, abstract, instruction=shrink_instruction)
                shrunk = True
            except Exception:
                logger.warning("Shrink-to-fit pass failed for document %s (returning as-is).", document_uid)

        return SummarizeDocumentResponse(
            document_uid=document_uid,
            summary=abstract,
            shrunk_for_budget=shrunk,
            keywords=keywords or [],
        )
