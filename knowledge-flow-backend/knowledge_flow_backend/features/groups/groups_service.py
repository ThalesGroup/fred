import asyncio
import logging
from collections.abc import Iterable
from typing import cast

from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakGetError

from knowledge_flow_backend.features.groups.groups_structures import GroupSummary
from knowledge_flow_backend.security.keycloack_admin_client import create_keycloak_admin

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200


async def list_groups() -> list[GroupSummary]:
    admin = create_keycloak_admin()
    if not admin:
        logger.info("Keycloak admin client not configured; returning empty group list.")
        return []

    root_groups = await _fetch_root_groups(admin)
    groups: list[GroupSummary] = []

    for raw_group in root_groups:
        group_id = raw_group.get("id")
        if not group_id:
            logger.debug("Skipping Keycloak group without identifier: %s", raw_group)
            continue
        group, _ = await _build_group_tree(admin, group_id)
        if group:
            groups.append(group)

    return groups


async def get_groups_by_ids(group_ids: Iterable[str]) -> dict[str, GroupSummary]:
    """
    Fetch hierarchical summaries for the provided group ids.
    Falls back to id-only summaries when Keycloak data cannot be retrieved.
    """
    unique_ids = {group_id for group_id in group_ids if group_id}
    if not unique_ids:
        return {}

    admin = create_keycloak_admin()
    if not admin:
        logger.info("Keycloak admin client not configured; returning fallback group profiles.")
        return {}

    ordered_ids = sorted(unique_ids)

    coroutines = {group_id: _build_group_tree(admin, group_id) for group_id in ordered_ids}
    results = await asyncio.gather(*coroutines.values(), return_exceptions=True)

    summaries: dict[str, GroupSummary] = {}
    for group_id, result in zip(coroutines.keys(), results):
        if isinstance(result, BaseException):
            if isinstance(result, KeycloakGetError) and result.response_code == 404:
                logger.debug("Group %s not found in Keycloak.", group_id)
                continue
            raise result

        summary, _ = cast(tuple[GroupSummary | None, set[str]], result)
        if summary:
            summaries[group_id] = summary
    return summaries


async def _fetch_root_groups(admin: KeycloakAdmin) -> list[dict]:
    groups: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _GROUP_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        groups.extend(batch)
        if len(batch) < _GROUP_PAGE_SIZE:
            break

        offset += _GROUP_PAGE_SIZE

    return groups


async def _build_group_tree(admin: KeycloakAdmin, group_id: str) -> tuple[GroupSummary | None, set[str]]:
    detailed_group = await admin.a_get_group(group_id)
    if not detailed_group:
        logger.debug("Keycloak returned empty group payload for id %s", group_id)
        return None, set()
    subgroups_payload = detailed_group.get("subGroups") or []

    sub_groups: list[GroupSummary] = []
    aggregated_members: set[str] = set()
    for subgroup in subgroups_payload:
        child_id = subgroup.get("id")
        if not child_id:
            logger.debug("Skipping Keycloak subgroup without identifier under group %s: %s", group_id, subgroup)
            continue
        child_summary, child_members = await _build_group_tree(admin, child_id)
        if child_summary:
            sub_groups.append(child_summary)
            aggregated_members.update(child_members)

    direct_members = await _fetch_group_member_ids(admin, group_id)
    aggregated_members.update(direct_members)

    summary = GroupSummary(
        id=group_id,
        name=_sanitize_name(detailed_group.get("name"), fallback=group_id),
        member_count=len(direct_members),
        total_member_count=len(aggregated_members),
        sub_groups=sub_groups,
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
