import asyncio
import logging
from collections.abc import Iterable
from typing import cast

from fred_core import KeycloackDisabled, create_keycloak_admin
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from knowledge_flow_backend.application_context import get_configuration
from knowledge_flow_backend.features.teams.teams_structures import TeamSummary

logger = logging.getLogger(__name__)

_TEAM_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200


async def list_teams() -> list[TeamSummary]:
    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty team list.")
        return []

    keycloak_groups = await _fetch_root_keycloak_groups(admin)
    teams: list[TeamSummary] = []

    for raw_group in keycloak_groups:
        team_id = raw_group.get("id")
        if not team_id:
            logger.debug("Skipping Keycloak group without identifier: %s", raw_group)
            continue
        team, _ = await _build_team_tree(admin, team_id)
        if team:
            teams.append(team)

    return teams


async def get_teams_by_ids(team_ids: Iterable[str]) -> dict[str, TeamSummary]:
    """
    Fetch hierarchical summaries for the provided team ids.
    Falls back to id-only summaries when Keycloak data cannot be retrieved.
    """
    unique_ids = {team_id for team_id in team_ids if team_id}
    if not unique_ids:
        return {}

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning fallback team profiles.")
        return {}

    ordered_ids = sorted(unique_ids)

    coroutines = {team_id: _build_team_tree(admin, team_id) for team_id in ordered_ids}
    results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    summaries: dict[str, TeamSummary] = {}
    for team_id, result in zip(coroutines.keys(), results):
        if isinstance(result, BaseException):
            if isinstance(result, KeycloakGetError) and result.response_code == 404:
                logger.debug("Team %s not found in Keycloak.", team_id)
                continue
            raise result

        summary, _ = cast(tuple[TeamSummary | None, set[str]], result)
        if summary:
            summaries[team_id] = summary
    return summaries


async def _fetch_root_keycloak_groups(admin: KeycloakAdmin) -> list[dict]:
    keycloak_groups: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _TEAM_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        keycloak_groups.extend(batch)
        if len(batch) < _TEAM_PAGE_SIZE:
            break

        offset += _TEAM_PAGE_SIZE

    return keycloak_groups


async def _build_team_tree(admin: KeycloakAdmin, team_id: str) -> tuple[TeamSummary | None, set[str]]:
    detailed_group = await admin.a_get_group(team_id)
    if not detailed_group:
        logger.debug("Keycloak returned empty group payload for id %s", team_id)
        return None, set()
    subteams_payload = detailed_group.get("subGroups") or []

    sub_teams: list[TeamSummary] = []
    aggregated_members: set[str] = set()
    for subteam in subteams_payload:
        child_id = subteam.get("id")
        if not child_id:
            logger.debug("Skipping Keycloak subteam without identifier under team %s: %s", team_id, subteam)
            continue
        child_summary, child_members = await _build_team_tree(admin, child_id)
        if child_summary:
            sub_teams.append(child_summary)
            aggregated_members.update(child_members)

    direct_members = await _fetch_group_member_ids(admin, team_id)
    aggregated_members.update(direct_members)

    summary = TeamSummary(
        id=team_id,
        name=_sanitize_name(detailed_group.get("name"), fallback=team_id),
        member_count=len(direct_members),
        total_member_count=len(aggregated_members),
        sub_teams=sub_teams,
    )
    return summary, aggregated_members


def _sanitize_name(value: object, fallback: str) -> str:
    name = (str(value or "")).strip()
    return name or fallback


async def _fetch_group_member_ids(admin: KeycloakAdmin, group_id: str) -> set[str]:
    member_ids: set[str] = set()
    offset = 0

    while True:
        batch = await admin.a_get_group_members(group_id, {"first": offset, "max": _MEMBER_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        for member in batch:
            member_id = member.get("id")
            if member_id:
                member_ids.add(member_id)
        if len(batch) < _MEMBER_PAGE_SIZE:
            break

        offset += _MEMBER_PAGE_SIZE

    return member_ids
