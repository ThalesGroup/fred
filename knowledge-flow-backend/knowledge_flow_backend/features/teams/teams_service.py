import logging

from fred_core import KeycloackDisabled, KeycloakUser, RebacDisabledResult, TeamPermission, create_keycloak_admin
from keycloak import KeycloakAdmin

from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.features.teams.teams_structures import Team

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

        # Map to Team with id and name from Keycloak, metadata from store
        team = Team(
            id=group_id,
            name=_sanitize_name(group_name, fallback=group_id),
            description=description,
            banner_image_url=banner_image_url,
            owners=[],  # TODO: to get from Keycloak or ReBAC
            member_count=0,  # TODO: to get from Keycloak
            is_private=is_private,
        )
        teams.append(team)

    return teams


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
