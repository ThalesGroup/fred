import asyncio
import logging

from fred_core import KeycloackDisabled, KeycloakUser, RebacDisabledResult, TeamPermission, create_keycloak_admin
from fred_core.security.rebac.rebac_engine import RebacReference, RelationType, Resource
from keycloak import KeycloakAdmin

from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.features.teams.teams_structures import Team
from knowledge_flow_backend.features.users.users_service import get_users_by_ids
from knowledge_flow_backend.features.users.users_structures import UserSummary

logger = logging.getLogger(__name__)

_TEAM_PAGE_SIZE = 200


async def list_teams(user: KeycloakUser) -> list[Team]:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()
    metadata_store = app_context.get_team_metadata_store()

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty team list.")
        return []

    # List groups in Keycloak
    root_groups = await _fetch_root_groups(admin)

    # Filter groups with ReBAC
    authorized_teams_refs = await rebac.lookup_user_resources(user, TeamPermission.CAN_READ)
    if not isinstance(authorized_teams_refs, RebacDisabledResult):
        authorized_tags_ids = [t.id for t in authorized_teams_refs]
        root_groups = [t for t in root_groups if t.get("id") in authorized_tags_ids]

    # Batch fetch metadata for all teams (single query)
    team_ids: list[str] = [g["id"] for g in root_groups if g.get("id") is not None]
    metadata_map = metadata_store.get_by_team_ids(team_ids)

    # Batch query OpenFGA for all team owners
    team_owners_list = await asyncio.gather(*[
        _get_team_owners(rebac, team_id)
        for team_id in team_ids
    ])

    # Build mapping and collect all unique owner IDs
    all_owner_ids = set()
    team_owners_map = {}

    for team_id, owner_ids in zip(team_ids, team_owners_list):
        team_owners_map[team_id] = owner_ids
        all_owner_ids.update(owner_ids)

    # Batch fetch user details from Keycloak
    user_summaries = await get_users_by_ids(all_owner_ids)

    # Transform Keycloak group in Fred Team
    teams: list[Team] = []
    for raw_group in root_groups:
        group_id = raw_group.get("id")
        group_name = raw_group.get("name")

        if not group_id:
            logger.debug("Skipping Keycloak group without identifier: %s", raw_group)
            continue

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
            owners=[
                user_summaries.get(owner_id) or UserSummary(id=owner_id)
                for owner_id in team_owners_map.get(group_id, [])
            ],
            member_count=0,  # TODO: Query from Keycloak (membership is contextual)
            is_private=is_private,
        )
        teams.append(team)

    return teams


async def _get_team_owners(rebac, team_id: str) -> list[str]:
    """Get all user IDs with owner relation to this team from OpenFGA."""
    team_reference = RebacReference(type=Resource.TEAM, id=team_id)

    owners = await rebac.lookup_subjects(
        team_reference,
        RelationType.OWNER,
        Resource.USER
    )

    if isinstance(owners, RebacDisabledResult):
        return []

    return [subject.id for subject in owners]


async def _fetch_root_groups(admin: KeycloakAdmin) -> list[dict]:
    groups: list[dict] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups({"first": offset, "max": _TEAM_PAGE_SIZE, "briefRepresentation": True})
        if not batch:
            break

        groups.extend(batch)
        if len(batch) < _TEAM_PAGE_SIZE:
            break

        offset += _TEAM_PAGE_SIZE

    return groups


def _sanitize_name(value: object, fallback: str) -> str:
    name = (str(value or "")).strip()
    return name or fallback
