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

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from langchain_core.tools import BaseTool, tool

from agentic_backend.common.kf_base_client import KnowledgeFlowAgentContext
from agentic_backend.core.chatbot.chat_schema import WritableDocumentPart
from agentic_backend.core.session.stores.base_writable_document_store import (
    WritableDocumentAuthor,
    WritableDocumentRecord,
)

logger = logging.getLogger(__name__)

WRITABLE_DOCUMENTS_PROVIDER = "writable_documents"


def build_writable_document_tools(agent: KnowledgeFlowAgentContext) -> list[BaseTool]:
    """In-process tool letting an agent create/update a collaborative document.

    The document is persisted (WritableDocumentStore) and surfaced in the editor
    pane via a ``WritableDocumentPart`` carried under ``fred_parts`` in the tool
    result content (the transcoder hydrates it onto the assistant message).
    """

    @tool("write_document")
    async def write_document(
        title: str,
        content_markdown: str,
        document_id: Optional[str] = None,
    ) -> str:
        """Create or update a collaborative document shown to the user in the editor panel.

        Use this whenever you are producing a deliverable document (report, email, memo,
        meeting notes) so the document is separated from the conversation and the user can
        edit it and export it to various formats (Word and Markdown).

        IMPORTANT - revise in place, never duplicate: to modify, correct, extend, shorten,
        reformat, or otherwise change a document that ALREADY exists, you MUST pass its
        existing document_id (returned as "saved (id=...)" by the previous call, and listed
        in the session's open-documents reminder). Omit document_id ONLY when the user
        clearly wants a brand-new, separate document.

        Provide the full document each time as Markdown in content_markdown (it replaces the
        previous content, it is not appended).
        """
        # Imported lazily to avoid import cycles and to read the configured singleton.
        from agentic_backend.application_context import get_writable_document_store

        store = get_writable_document_store()
        if store is None:
            return (
                "Writable documents are not enabled in this environment; "
                "the document could not be saved."
            )

        session_id = getattr(
            getattr(agent, "runtime_context", None), "session_id", None
        )
        if not session_id:
            return "Cannot save the document: no active session."

        doc_id = document_id
        if doc_id is None:
            # Deterministic de-dup safety net: if a document with the same title
            # already exists in this session, revise it instead of creating a
            # duplicate. Agents reliably reuse the title when revising but sometimes
            # omit document_id; without this they would spawn a second editor tab.
            try:
                existing = await store.list_for_session(session_id)
            except Exception:
                logger.exception(
                    "[WRITABLE_DOC][TOOL] failed to list documents for session=%s",
                    session_id,
                )
                existing = []
            match = next(
                (d for d in existing if (d.title or "").strip() == title.strip()),
                None,
            )
            if match is not None:
                doc_id = match.document_id
                logger.info(
                    "[WRITABLE_DOC][TOOL] reusing existing document_id=%s by title match (session=%s)",
                    doc_id,
                    session_id,
                )
        if doc_id is None:
            doc_id = str(uuid.uuid4())
        stored = await store.upsert(
            WritableDocumentRecord(
                session_id=session_id,
                document_id=doc_id,
                title=title,
                content_md=content_markdown,
                updated_by=WritableDocumentAuthor.agent,
            )
        )

        part = WritableDocumentPart(
            document_id=stored.document_id,
            title=stored.title,
            content_md=stored.content_md,
            updated_at=stored.updated_at or datetime.now(timezone.utc),
            updated_by=WritableDocumentAuthor.agent,
        )
        logger.info(
            "[WRITABLE_DOC][TOOL] session=%s document_id=%s title=%r len=%d",
            session_id,
            doc_id,
            title[:80],
            len(content_markdown),
        )
        # The transcoder parses `fred_parts` from the tool content to hydrate the part.
        return json.dumps(
            {
                "message": f"Document '{title}' saved (id={doc_id}).",
                "fred_parts": [part.model_dump(mode="json")],
            },
            ensure_ascii=False,
        )

    return [write_document]
