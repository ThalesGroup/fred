# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

"""Canonical, bounded organization/team/project ancestry."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from fred_core.models import Base


class SpaceKind(StrEnum):
    ORGANIZATION = "organization"
    TEAM = "team"
    PROJECT = "project"


class TeamKind(StrEnum):
    COLLABORATIVE = "collaborative"
    PERSONAL = "personal"


@dataclass(frozen=True)
class SpaceContext:
    id: str
    kind: SpaceKind
    organization_id: str
    team_id: str | None

    @property
    def ancestry(self) -> tuple[tuple[SpaceKind, str], ...]:
        """Current space first, then its parents; never siblings or descendants."""
        if self.kind == SpaceKind.ORGANIZATION:
            return ((self.kind, self.id),)
        if self.kind == SpaceKind.TEAM:
            return (
                (self.kind, self.id),
                (SpaceKind.ORGANIZATION, self.organization_id),
            )
        assert self.team_id is not None
        return (
            (self.kind, self.id),
            (SpaceKind.TEAM, self.team_id),
            (SpaceKind.ORGANIZATION, self.organization_id),
        )


class SpaceRow(Base):
    __tablename__ = "space"
    __table_args__ = (
        CheckConstraint(
            "((kind = 'organization' AND parent_id IS NULL AND parent_kind IS NULL "
            "AND parent_team_kind IS NULL AND team_kind IS NULL AND personal_owner_id IS NULL) OR "
            "(kind = 'team' AND parent_id IS NOT NULL AND parent_kind = 'organization' "
            "AND parent_team_kind IS NULL AND "
            "((team_kind = 'collaborative' AND personal_owner_id IS NULL) OR "
            "(team_kind = 'personal' AND personal_owner_id IS NOT NULL))) OR "
            "(kind = 'project' AND parent_id IS NOT NULL AND parent_kind = 'team' "
            "AND parent_team_kind = 'collaborative' AND team_kind IS NULL "
            "AND personal_owner_id IS NULL)) IS TRUE",
            name="ck_space_shape",
        ),
        CheckConstraint("length(trim(name)) > 0", name="ck_space_name"),
        UniqueConstraint("id", "kind", name="uq_space_id_kind"),
        UniqueConstraint("id", "team_kind", name="uq_space_id_team_kind"),
        UniqueConstraint("parent_id", "name", name="uq_space_parent_name"),
        UniqueConstraint("personal_owner_id", name="uq_space_personal_owner"),
        ForeignKeyConstraint(
            ["parent_id", "parent_kind"],
            ["space.id", "space.kind"],
            name="fk_space_parent",
        ),
        # Only projects carry this second reference; it excludes personal parents.
        ForeignKeyConstraint(
            ["parent_id", "parent_team_kind"],
            ["space.id", "space.team_kind"],
            name="fk_space_collaborative_parent",
        ),
        Index(
            "uq_space_organization_name",
            "name",
            unique=True,
            postgresql_where=text("kind = 'organization'"),
            sqlite_where=text("kind = 'organization'"),
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    parent_id: Mapped[str | None] = mapped_column(String)
    parent_kind: Mapped[str | None] = mapped_column(String(20))
    parent_team_kind: Mapped[str | None] = mapped_column(String(20))
    team_kind: Mapped[str | None] = mapped_column(String(20))
    personal_owner_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", name="fk_space_personal_owner")
    )
