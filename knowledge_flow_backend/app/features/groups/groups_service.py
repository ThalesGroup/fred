import logging

from keycloak import KeycloakAdmin
from pydantic import BaseModel, Field

from app.security.keycloack_admin_client import create_keycloak_admin

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200


class GroupSummary(BaseModel):
    id: str
    name: str
    member_count: int
    total_member_count: int
    sub_groups: list["GroupSummary"] = Field(default_factory=list)


GroupSummary.model_rebuild()  # to support self-referencing models


async def list_groups() -> list[GroupSummary]:
    admin = create_keycloak_admin()
    if not admin:
        logger.info("Keycloak admin client not configured; returning empty group list.")
        return []

    root_groups = await _fetch_root_groups(admin)
    groups: list[GroupSummary] = []

    for raw_group in root_groups:
        group, _ = await _build_group_tree(admin, raw_group)
        if group:
            groups.append(group)

    return groups


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


async def _build_group_tree(admin: KeycloakAdmin, raw_group: dict) -> tuple[GroupSummary | None, set[str]]:
    group_id = raw_group.get("id")
    if not group_id:
        logger.debug("Skipping Keycloak group without identifier: %s", raw_group)
        return None, set()

    detailed_group = await admin.a_get_group(group_id)
    subgroups_payload = detailed_group.get("subGroups") or []

    sub_groups: list[GroupSummary] = []
    aggregated_members: set[str] = set()
    for subgroup in subgroups_payload:
        child_summary, child_members = await _build_group_tree(admin, subgroup)
        if child_summary:
            sub_groups.append(child_summary)
            aggregated_members.update(child_members)

    direct_members = await _fetch_group_member_ids(admin, group_id)
    aggregated_members.update(direct_members)

    summary = GroupSummary(
        id=group_id,
        name=_sanitize_name(detailed_group.get("name") or raw_group.get("name"), fallback=group_id),
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
