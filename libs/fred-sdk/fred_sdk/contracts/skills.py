# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Platform-owned skill metadata, explicit selection and read-only runtime port."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class SkillSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str


class SkillCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supported: bool = True
    revision: str = ""
    skills: tuple[SkillSummary, ...] = ()


class SkillInvocation(BaseModel):
    """A name only: clients cannot supply procedural instructions or paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)


class SkillLoadAttribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    origin: Literal["user", "agent"]
    revision: str
    load_id: str
    agent_id: str
    child: bool = False
    child_id: str | None = None


class SkillsPort(Protocol):
    """One immutable pod snapshot; no execution or permission provisioning."""

    @property
    def catalog(self) -> SkillCatalog: ...

    @property
    def prompt(self) -> str: ...

    def read(self, name: str, path: str = "SKILL.md") -> str: ...
