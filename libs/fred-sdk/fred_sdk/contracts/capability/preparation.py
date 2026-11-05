# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Durable preparation of an installed capability, outside agent execution."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncEngine


class PreparationWork(BaseModel):
    """Canonical CP response; never accepted from the browser or Temporal input."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    preparation_id: UUID
    installation_id: UUID
    runtime_id: str
    capability_id: str
    space_id: UUID
    agent_instance_id: UUID | None
    configuration_revision: int | None
    file_id: UUID
    sha256: str
    filename: str
    size: int = Field(ge=0, le=64 * 1024 * 1024)
    config: dict[str, Any]
    state: Literal["pending", "ready", "failed", "obsolete"]


class PreparationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reference: str | None = Field(default=None, max_length=256)
    error: str | None = Field(default=None, max_length=2000)


@dataclass(frozen=True)
class PreparationContext:
    work: PreparationWork
    database: "AsyncEngine"
    content: bytes
