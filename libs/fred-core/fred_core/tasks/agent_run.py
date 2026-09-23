# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");

"""Durable, credential-free contracts for scheduled agent runs."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentRunScope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_ids: tuple[str, ...] = ()
    library_ids: tuple[str, ...] = ()


class AgentRunBudget(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wall_clock_seconds: float = Field(gt=0)
    max_concurrent_children: int = Field(ge=1)

    @field_validator("wall_clock_seconds")
    @classmethod
    def _finite_wall_clock(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("wall_clock_seconds must be finite")
        return value


class AgentRunAdmissionRecord(BaseModel):
    """Server-derived durable input. It deliberately contains no credential."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    person_id: str = Field(min_length=1)
    roles: tuple[str, ...] = ()
    team_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)
    agent_instance_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    scope: AgentRunScope = Field(default_factory=AgentRunScope)
    mode: Literal["background"] = "background"
    created_by: str = Field(min_length=1)
    created_at: datetime
    run_id: str = Field(min_length=1)
    budget: AgentRunBudget

    @field_validator("created_at")
    @classmethod
    def _utc_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)


class AgentRunWorkflowInputV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    task_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    record: AgentRunAdmissionRecord


class ScheduledAgentRunInputV1(BaseModel):
    """A schedule template; every tick receives a fresh record from control-plane."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    schedule_id: str = Field(min_length=1)
    runtime_id: str = Field(min_length=1)


class ScheduledAgentRunOccurrenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)


class ScheduledAgentRunOccurrence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    workflow_id: str = Field(min_length=1)
    record: AgentRunAdmissionRecord
