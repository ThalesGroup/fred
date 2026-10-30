# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Internal manager persistence callbacks. Temporal uses the existing scheduler models."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Profile = Literal["fast", "medium", "rich"]
Stage = Literal["preparation", "extraction", "indexing"]


FailureCode = Literal[
    "unsupported_input",
    "access_changed",
    "integrity_failure",
    "extraction_failed",
    "preview_failed",
    "indexing_failed",
    "capacity_exceeded",
    "worker_failed",
    "deadline_exceeded",
    "delivery_unknown",
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Work(Contract):
    contract_version: Literal[1]
    installation_id: UUID
    processing_id: UUID
    document_id: UUID
    original_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile: Profile


class Artifact(Contract):
    path: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Manifest(Contract):
    generation: UUID
    artifacts: list[Artifact]
    chunks: int = Field(ge=0)
    vectors: int = Field(ge=0)
    vector_ordinals: list[int] = Field(default_factory=list)
    rows: int | None = None


class Predecessor(Contract):
    prefix: str
    manifest: Manifest


class Descriptor(Contract):
    work: Work
    organization_id: UUID
    space_id: UUID
    folder_id: UUID | None
    folder_path: str | None
    session_id: UUID | None
    name: str
    mime: str
    size: int
    actor: str
    stage: Stage
    generation: UUID
    expires_at: datetime
    output_prefix: str
    max_output_bytes: int
    max_artifacts: int
    max_chunks: int
    file: dict
    profile_settings: dict
    predecessor: Predecessor | None
    committed: Manifest | None

    @model_validator(mode="after")
    def validate_placement(self) -> Self:
        if (self.folder_id is None) == (self.session_id is None):
            raise ValueError("Exactly one folder or conversation is required")
        if (self.folder_path is None) != (self.folder_id is None):
            raise ValueError("A folder path is required only for a drive document")
        return self


class Claim(Contract):
    work: Work
    stage: Stage
    execution_id: UUID
    activity_id: UUID
    attempt: int = Field(ge=1)


class Commit(Contract):
    work: Work
    stage: Stage
    manifest: Manifest


class Failure(Contract):
    work: Work
    stage: Stage
    generation: UUID | None
    code: FailureCode


class VectorPlan(Contract):
    work: Work
    generation: UUID
    count: int


class Cleaned(Contract):
    work: Work
    generation: UUID
    cursor: int
    next_cursor: int
    objects_empty: bool
    purge_document: bool = False


class RetrievalWork(Contract):
    document_id: UUID
    operation_id: UUID
    manifest: Manifest
    retrievable: bool
    confirmed: bool
    phase: Literal["ready", "writing", "applied"]


class RetrievalConfirmation(Contract):
    step: Literal["claim", "applied", "confirm"]
    operation_id: UUID
    retrievable: bool
