# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SandboxSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idle_minutes: int = Field(ge=1, le=120)
    max_active_sessions: int = Field(ge=1, le=1000)


class SandboxSettingsView(SandboxSettingsUpdate):
    profile_id: str = "unconfigured"
    updated_by: str | None = None
    updated_at: datetime | None = None
