# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.
"""Platform-owned skill metadata, explicit selection and read-only runtime port."""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class SkillSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    description: str
    argument_hint: str | None = Field(default=None, min_length=1, max_length=256)


class SkillCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    supported: bool = True
    revision: str = ""
    skills: tuple[SkillSummary, ...] = ()


class SkillInvocation(BaseModel):
    """A name only: clients cannot supply procedural instructions or paths."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64)


class SkillDetail(BaseModel):
    """Read-only preview of a skill in the current runtime snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    skill: SkillSummary
    revision: str
    content: str = Field(max_length=262144)


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
    """Web/ReAct snapshot catalog and loading port; no new authority."""

    @property
    def catalog(self) -> SkillCatalog: ...

    @property
    def prompt(self) -> str: ...

    def read(self, name: str, path: str = "SKILL.md") -> str:
        """Return original UTF-8 text; escape reserved tags at model boundaries."""
        ...
