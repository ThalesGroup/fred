# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0

from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import aliased

from fred_core.common.team_id import TeamId, personal_team_id
from fred_core.sql.async_session import make_session_factory, use_session
from fred_core.teams.space_models import SpaceContext, SpaceKind, SpaceRow, TeamKind
from fred_core.users.user_models import UserRow


class SpaceStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = make_session_factory(engine)

    async def resolve_for_user(
        self,
        user_id: UUID,
        space_id: str | None,
        session: AsyncSession | None = None,
    ) -> SpaceContext | None:
        """Resolve a space, or the user's organization when no space ID is supplied."""
        parent, grandparent = aliased(SpaceRow), aliased(SpaceRow)
        organization_id = func.coalesce(grandparent.id, parent.id, SpaceRow.id)
        team_id = case(
            (SpaceRow.kind == SpaceKind.TEAM, SpaceRow.id),
            (SpaceRow.kind == SpaceKind.PROJECT, parent.id),
        )
        statement = (
            select(SpaceRow.id, SpaceRow.kind, organization_id, team_id)
            .outerjoin(parent, parent.id == SpaceRow.parent_id)
            .outerjoin(grandparent, grandparent.id == parent.parent_id)
            .join(UserRow, UserRow.id == user_id)
            .where(
                SpaceRow.id
                == (space_id if space_id is not None else UserRow.organization_id),
                UserRow.organization_id == organization_id,
                or_(
                    SpaceRow.personal_owner_id.is_(None),
                    SpaceRow.personal_owner_id == user_id,
                ),
            )
        )
        async with use_session(self._sessions, session) as s:
            row = (await s.execute(statement)).one_or_none()
        if row is None:
            return None
        return SpaceContext(row[0], SpaceKind(row[1]), row[2], row[3])

    async def create_organization(
        self,
        organization_id: str,
        name: str,
        session: AsyncSession | None = None,
    ) -> bool:
        """Create a root or recognize the exact same declaration on re-import."""
        async with use_session(self._sessions, session) as s:
            existing = await s.get(SpaceRow, organization_id)
            if existing is not None:
                if existing.kind != SpaceKind.ORGANIZATION or existing.name != name:
                    raise ValueError(
                        "Organization declaration conflicts with an existing space"
                    )
                return False
            s.add(SpaceRow(id=organization_id, name=name, kind=SpaceKind.ORGANIZATION))
            await s.flush()
            return True

    async def create_personal_team(
        self,
        owner_id: UUID,
        organization_id: str,
        session: AsyncSession | None = None,
    ) -> TeamId:
        identifier = personal_team_id(str(owner_id))
        async with use_session(self._sessions, session) as s:
            owner_organization = await s.scalar(
                select(UserRow.organization_id).where(UserRow.id == owner_id)
            )
            if owner_organization != organization_id:
                raise ValueError(
                    "Personal team must belong to its owner's organization"
                )
            existing = await s.get(SpaceRow, str(identifier))
            if existing is not None:
                if (
                    existing.kind != SpaceKind.TEAM
                    or existing.team_kind != TeamKind.PERSONAL
                    or existing.personal_owner_id != owner_id
                    or existing.parent_id != organization_id
                ):
                    raise ValueError(
                        "Personal team declaration conflicts with an existing space"
                    )
            else:
                s.add(
                    SpaceRow(
                        id=str(identifier),
                        name=str(identifier),
                        kind=SpaceKind.TEAM,
                        parent_id=organization_id,
                        parent_kind=SpaceKind.ORGANIZATION,
                        team_kind=TeamKind.PERSONAL,
                        personal_owner_id=owner_id,
                    )
                )
                await s.flush()
        return identifier
