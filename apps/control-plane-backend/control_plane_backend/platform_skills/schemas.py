# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Feature-management views of the packaged platform skill catalog."""

from fred_sdk.contracts.skills import SkillSummary
from pydantic import BaseModel, ConfigDict, Field


class PlatformSkillEntry(BaseModel):
    """One packaged skill and the runtime sources that currently advertise it."""

    model_config = ConfigDict(extra="forbid")

    skill: SkillSummary
    enabled: bool = True
    runtime_ids: list[str] = Field(default_factory=list)


class PlatformSkillInventory(BaseModel):
    """Live metadata and explicit diagnostics, never an invented empty catalog."""

    model_config = ConfigDict(extra="forbid")

    skills: list[PlatformSkillEntry] = Field(default_factory=list)
    disabled_skill_names: list[str] = Field(default_factory=list)
    unavailable_runtime_ids: list[str] = Field(default_factory=list)
    unsupported_runtime_ids: list[str] = Field(default_factory=list)


class PlatformSkillPolicy(BaseModel):
    """Fresh global restrictions for a configured runtime's direct execution."""

    model_config = ConfigDict(extra="forbid")

    disabled_skill_names: list[str] = Field(default_factory=list)


class SetPlatformSkillEnabledRequest(BaseModel):
    """Replace one skill's global state without overwriting other skills."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool


class PlatformSkillEnabled(BaseModel):
    """Committed state, including when an unavailable source prevents metadata reads."""

    model_config = ConfigDict(extra="forbid")

    name: str
    enabled: bool
