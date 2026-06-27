"""Platform data summary — admin overview of teams, members, agents, prompts.

A lightweight relational aggregation (distinct from the OpenSearch KPI subsystem)
that answers "what is currently in this swift instance?". Used as a permanent
reassurance panel on the Platform data admin page, alongside import/export/reset.

Composed entirely from existing list primitives — no new store methods:
- teams           → teams.service.list_teams (Keycloak + ReBAC CAN_READ filtered)
- members by role → teams.service.list_team_members (OWNER / MANAGER / MEMBER)
- agents per team → AgentInstanceStore.list_by_team
- prompts per team→ PromptStore.list_by_team (team-scoped)
"""

from __future__ import annotations

import logging

from fred_core import KeycloakUser
from pydantic import BaseModel

from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.prompts.store import PromptStore
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import UserTeamRelation
from control_plane_backend.teams.service import list_team_members, list_teams

logger = logging.getLogger(__name__)

# High enough to count every prompt of a team in one page (list_by_team paginates).
_PROMPT_COUNT_LIMIT = 10_000


class TeamStats(BaseModel):
    team_id: str
    name: str
    owners: int
    managers: int
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


async def compute_platform_stats(
    *,
    user: KeycloakUser,
    team_deps: TeamServiceDependencies,
    agent_store: AgentInstanceStore,
    prompt_store: PromptStore,
) -> PlatformStats:
    teams = await list_teams(user, team_deps)

    per_team: list[TeamStats] = []
    distinct_users: set[str] = set()
    total_prompts = 0

    for team in teams:
        try:
            members = await list_team_members(user, team.id, team_deps)
        except Exception as exc:
            # A team the operator cannot read members of must not break the whole
            # summary — degrade that row's member counts to zero and carry on.
            logger.warning(
                "[import-export] stats: cannot read members of team %s: %s",
                team.id,
                exc,
            )
            members = []

        owners = sum(1 for m in members if m.relation == UserTeamRelation.OWNER)
        managers = sum(1 for m in members if m.relation == UserTeamRelation.MANAGER)
        plain = sum(1 for m in members if m.relation == UserTeamRelation.MEMBER)
        for m in members:
            distinct_users.add(m.user.id)

        agents = len(await agent_store.list_by_team(team.id))
        prompts = len(
            await prompt_store.list_by_team(team.id, limit=_PROMPT_COUNT_LIMIT)
        )
        total_prompts += prompts

        per_team.append(
            TeamStats(
                team_id=str(team.id),
                name=team.name,
                owners=owners,
                managers=managers,
                members=plain,
                total_members=len(members),
                agents=agents,
                prompts=prompts,
            )
        )

    return PlatformStats(
        teams=len(teams),
        distinct_users=len(distinct_users),
        total_agents=await agent_store.count_all(),
        total_prompts=total_prompts,
        per_team=per_team,
    )
