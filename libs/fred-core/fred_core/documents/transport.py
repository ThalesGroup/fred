# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Server-bound document context carried outside MCP tool arguments."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from fred_core.documents.selection import DocumentScope

DOCUMENT_CONTEXT_HEADER = "x-fred-document-context"


class DocumentAccessContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    space_id: UUID
    document_scope: DocumentScope
