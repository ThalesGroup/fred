# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Server-bound document context carried outside MCP tool arguments."""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fred_core.documents.selection import DocumentScope

DOCUMENT_CONTEXT_HEADER = "x-fred-document-context"


class DocumentAccessContext(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    space_id: UUID
    authorized_space_ids: tuple[UUID, ...] = Field(
        description="Exact corpus authorized by Control Plane at turn admission, carried by the trusted workload. Empty grants no corpus access."
    )
    document_scope: DocumentScope
    conversation_id: UUID | None = Field(
        default=None,
        description="Server-bound conversation UUID; SQL verifies its owner, exact space and live state.",
    )
    attachment_ids: tuple[UUID, ...] = Field(
        default=(),
        description="Explicit attachment UUIDs, independently of corpus selection. Empty grants no attachment access; requires conversation_id. SQL verifies every document.",
    )

    @model_validator(mode="after")
    def validate_bound_sources(self) -> Self:
        if len(set(self.authorized_space_ids)) != len(self.authorized_space_ids):
            raise ValueError("Duplicate authorized spaces")
        if self.attachment_ids and self.conversation_id is None:
            raise ValueError("attachment_ids requires conversation_id")
        return self
