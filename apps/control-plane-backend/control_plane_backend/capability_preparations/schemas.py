# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Bounded public and worker payloads for capability preparation."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fred_sdk.contracts.capability.preparation import (
    PreparationAsset,
    PreparationResult,
    PreparationWork,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PreparationStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    preparation_id: str
    state: Literal["pending", "running", "succeeded", "failed"]
    input_revision: str
    attempts: int
    max_attempts: int
    gates_readiness: bool
    created_at: datetime
    completed_at: datetime | None = None
    summary: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    result_reference: str | None = None
    assets: list[PreparationAsset] = Field(default_factory=list, max_length=32)
    public_config: dict[str, Any] = Field(default_factory=dict)


class PreparationStatusPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PreparationStatus] = Field(max_length=100)
    has_more: bool = False


class PlatformPreparationSelection(BaseModel):
    active: PreparationStatus | None = None
    candidate: PreparationStatus | None = None
    settings: dict[str, Any] = Field(default_factory=dict)


class WorkerPreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_revision: str = Field(min_length=1, max_length=128)
    attempt: int = Field(ge=1, le=10)
    state: Literal["succeeded", "failed"]
    result: PreparationResult | None = None
    error_code: str | None = Field(default=None, max_length=64)
    error_detail: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _matching_payload(self) -> "WorkerPreparationResult":
        if self.state == "succeeded" and self.result is None:
            raise ValueError("A successful preparation requires a result")
        if self.state == "failed" and self.error_code is None:
            raise ValueError("A failed preparation requires an error code")
        return self


class WorkerResultAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool


class CleanupLease(BaseModel):
    preparation_id: UUID
    claim_id: UUID


class CleanupBatch(BaseModel):
    items: list[CleanupLease] = Field(default_factory=list, max_length=20)


class CleanupCompletion(BaseModel):
    claim_id: UUID


class WorkerAttemptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work: PreparationWork | None = None
