import asyncio
import logging

from fred_core import KeycloackDisabled, KeycloakUser, RebacDisabledResult, TeamPermission, create_keycloak_admin
from fred_core.security.rebac.rebac_engine import RebacReference, RelationType, Resource
from keycloak import KeycloakAdmin

from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.features.teams.teams_structures import KeycloakGroupSummary, Team
from knowledge_flow_backend.features.users.users_service import get_users_by_ids
from knowledge_flow_backend.features.users.users_structures import UserSummary

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200


async def list_teams(user: KeycloakUser) -> list[Team]:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()
    metadata_store = app_context.get_team_metadata_store()

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty team list.")
        return []

    # List groups in Keycloak
    root_groups = await _fetch_root_keycloak_groups(admin)

    # Filter groups with ReBAC
    authorized_teams_refs = await rebac.lookup_user_resources(user, TeamPermission.CAN_READ)
    if not isinstance(authorized_teams_refs, RebacDisabledResult):
        authorized_tags_ids = [t.id for t in authorized_teams_refs]
        root_groups = [t for t in root_groups if t.id in authorized_tags_ids]

    # Batch fetch metadata for all teams
    team_ids: list[str] = [g.id for g in root_groups]
    metadata_map = metadata_store.get_by_team_ids(team_ids)

    # Batch query OpenFGA for all team owners and Keycloak for member counts in parallel
    team_owners_list, member_counts_list = await asyncio.gather(
        asyncio.gather(*[_get_team_owners(rebac, team_id) for team_id in team_ids]),
        asyncio.gather(*[_fetch_group_member_ids(admin, team_id) for team_id in team_ids]),
    )

    # Build mapping and collect all unique owner IDs
    all_owner_ids = set()
    team_owners_map = {}
    member_counts_map = {}

    for team_id, owner_ids in zip(team_ids, team_owners_list):
        team_owners_map[team_id] = owner_ids
        all_owner_ids.update(owner_ids)

    for team_id, member_ids in zip(team_ids, member_counts_list):
        member_counts_map[team_id] = len(member_ids)

    # Batch fetch user details from Keycloak
    user_summaries = await get_users_by_ids(all_owner_ids)

    # Transform Keycloak group in Fred Team
    teams: list[Team] = []
    for group_summary in root_groups:
        group_id = group_summary.id
        group_name = group_summary.name

        # Get metadata from batch results
        metadata = metadata_map.get(group_id)
        if metadata:
            description = metadata.description
            banner_image_url = metadata.banner_image_url
            is_private = metadata.is_private
        else:
            # Use defaults if metadata not found
            description = None
            banner_image_url = None
            is_private = False

        # Map to Team with id and name from Keycloak, metadata from store, owners from OpenFGA
        team = Team(
            id=group_id,
            name=_sanitize_name(group_name, fallback=group_id),
            description=description,
            banner_image_url=banner_image_url,
            owners=[user_summaries.get(owner_id) or UserSummary(id=owner_id) for owner_id in team_owners_map.get(group_id, [])],
            member_count=member_counts_map.get(group_id, 0),
            is_private=is_private,
        )
        teams.append(team)

    return teams


async def _get_team_owners(rebac, team_id: str) -> list[str]:
    """Get all user IDs with owner relation to this team from OpenFGA."""
    team_reference = RebacReference(type=Resource.TEAM, id=team_id)

    owners = await rebac.lookup_subjects(team_reference, RelationType.OWNER, Resource.USER)

    if isinstance(owners, RebacDisabledResult):
        return []

    return [subject.id for subject in owners]


async def _fetch_root_keycloak_groups(admin: KeycloakAdmin) -> list[KeycloakGroupSummary]:
    groups: list[KeycloakGroupSummary] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _GROUP_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        for raw_group in batch:
            group_id = raw_group.get("id")
            if group_id:
                groups.append(
                    KeycloakGroupSummary(
                        id=group_id,
                        name=raw_group.get("name"),
                        member_count=0,  # Will be populated later in parallel
                    )
                )

        if len(batch) < _GROUP_PAGE_SIZE:
            break

        offset += _GROUP_PAGE_SIZE

    return groups


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


def _sanitize_name(value: object, fallback: str) -> str:
    name = (str(value or "")).strip()
    return name or fallback
