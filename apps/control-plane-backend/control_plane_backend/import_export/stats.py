"""Platform data summary — admin overview of teams, members, agents, prompts.

A lightweight relational aggregation (distinct from the OpenSearch KPI subsystem)
that answers "what is currently in this swift instance?". Used as a permanent
reassurance panel on the Platform data admin page, alongside import/export/reset.

Counts are sourced authoritatively:
- agents / prompts → grouped by ``team_id`` straight from the DB (one query each),
  which captures every team including per-user personal spaces (``personal-*``).
- teams + members  → teams.service (Keycloak + ReBAC); members bucketed by role
  (TEAM_ADMIN / TEAM_EDITOR / TEAM_ANALYST / TEAM_MEMBER).

Personal spaces are per-user (one ``personal-{uid}`` team each), so they are NOT
real teams. ``list_all_teams_unfiltered`` only surfaces the caller's own personal
team (system teams are always caller-scoped), which is not representative — so
personal spaces are excluded from the real-team rows and folded into a single
aggregate "Espaces personnels" row instead.
"""

from __future__ import annotations

import logging

from fred_core import KeycloakUser
from fred_core.sql.async_session import make_session_factory
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.prompt_models import PromptRow
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import (
    list_all_teams_unfiltered,
    list_team_members_unfiltered,
)

logger = logging.getLogger(__name__)

_PERSONAL_ROW_NAME = "Espaces personnels"


class TeamStats(BaseModel):
    team_id: str
    name: str
    admins: int
    editors: int
    analysts: int
    members: int
    total_members: int
    agents: int
    prompts: int


class PlatformStats(BaseModel):
    teams: int
    distinct_users: int
    total_agents: int
    total_prompts: int
    per_team: list[TeamStats]


def _is_personal(team_id: str) -> bool:
    """Personal spaces are scoped to ``personal`` / ``personal-{uid}`` team ids."""
    return team_id == "personal" or team_id.startswith("personal-")


async def _counts_by_team(engine: AsyncEngine) -> tuple[dict[str, int], dict[str, int]]:
    """Return (agents_by_team_id, prompts_by_team_id) in two grouped queries."""
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        agent_rows = await session.execute(
            select(AgentInstanceRow.team_id, func.count()).group_by(
                AgentInstanceRow.team_id
            )
        )
        agents_by_team = {tid: n for tid, n in agent_rows.all()}
        prompt_rows = await session.execute(
            select(PromptRow.team_id, func.count()).group_by(PromptRow.team_id)
        )
        prompts_by_team = {tid: n for tid, n in prompt_rows.all()}
    return agents_by_team, prompts_by_team


async def compute_platform_stats(
    *,
    user: KeycloakUser,
    team_deps: TeamServiceDependencies,
    engine: AsyncEngine,
) -> PlatformStats:
    agents_by_team, prompts_by_team = await _counts_by_team(engine)

    # SECURITY: the caller (`platform_stats`) already checked CAN_MANAGE_PLATFORM,
    # so this intentionally lists every real team, not just the ones the
    # caller could personally read.
    teams = await list_all_teams_unfiltered(user, team_deps)
    real_teams = [t for t in teams if not _is_personal(str(t.id))]

    per_team: list[TeamStats] = []
    distinct_users: set[str] = set()

    for team in real_teams:
        try:
            # `_unfiltered`: the caller already verified `CAN_MANAGE_PLATFORM`
            # above `compute_platform_stats`. The per-team `CAN_READ_MEMEBERS`
            # check would 403 on every real team the admin isn't personally a
            # member of — the common case, since platform_admin carries no
            # standing team relation (AUTHZ-05 review item 14).
            members = await list_team_members_unfiltered(user, team.id, team_deps)
        except Exception as exc:
            # A genuinely broken team (e.g. deleted mid-computation) must not
            # break the whole summary — degrade that row's counts to zero.
            logger.warning(
                "[import-export] stats: cannot read members of team %s: %s",
                team.id,
                exc,
            )
            members = []

        admins = sum(1 for m in members if m.relation == UserTeamRelation.TEAM_ADMIN)
        editors = sum(1 for m in members if m.relation == UserTeamRelation.TEAM_EDITOR)
        analysts = sum(
            1 for m in members if m.relation == UserTeamRelation.TEAM_ANALYST
        )
        plain = sum(1 for m in members if m.relation == UserTeamRelation.TEAM_MEMBER)
        for m in members:
            distinct_users.add(m.user.id)

        tid = str(team.id)
        per_team.append(
            TeamStats(
                team_id=tid,
                name=team.name,
                admins=admins,
                editors=editors,
                analysts=analysts,
                members=plain,
                total_members=len(members),
                agents=agents_by_team.get(tid, 0),
                prompts=prompts_by_team.get(tid, 0),
            )
        )

    # Aggregate every personal space (one per user) into a single row. The number
    # of distinct personal team ids = number of users with personal data, shown in
    # the Admins column (each user administers their own personal space).
    personal_ids = {
        tid for tid in set(agents_by_team) | set(prompts_by_team) if _is_personal(tid)
    }
    personal_agents = sum(agents_by_team.get(tid, 0) for tid in personal_ids)
    personal_prompts = sum(prompts_by_team.get(tid, 0) for tid in personal_ids)
    if personal_ids:
        per_team.append(
            TeamStats(
                team_id="personal",
                name=_PERSONAL_ROW_NAME,
                admins=len(personal_ids),
                editors=0,
                analysts=0,
                members=0,
                total_members=len(personal_ids),
                agents=personal_agents,
                prompts=personal_prompts,
            )
        )

    return PlatformStats(
        teams=len(real_teams),
        distinct_users=len(distinct_users),
        total_agents=sum(agents_by_team.values()),
        total_prompts=sum(prompts_by_team.values()),
        per_team=per_team,
    )
