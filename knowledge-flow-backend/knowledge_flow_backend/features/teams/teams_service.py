import asyncio
import logging

from fred_core import ORGANIZATION_ID, KeycloackDisabled, KeycloakUser, RebacDisabledResult, RebacEngine, RebacReference, Relation, RelationType, Resource, TeamPermission, create_keycloak_admin
from keycloak import KeycloakAdmin

from knowledge_flow_backend.application_context import ApplicationContext, get_configuration
from knowledge_flow_backend.core.stores.team_metadata.team_metadata_structures import TeamMetadata
from knowledge_flow_backend.features.teams.teams_structures import KeycloakGroupSummary, Team, TeamNotFoundError, TeamUpdate
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
    consistency_token = await _ensure_team_organization_relations(rebac, [g.id for g in root_groups])
    authorized_teams_refs = await rebac.lookup_user_resources(user, TeamPermission.CAN_READ, consistency_token=consistency_token)
    if not isinstance(authorized_teams_refs, RebacDisabledResult):
        authorized_tags_ids = [t.id for t in authorized_teams_refs]
        root_groups = [t for t in root_groups if t.id in authorized_tags_ids]

    # Enrich groups with full team data
    return await _enrich_groups_with_team_data(admin, rebac, metadata_store, user, root_groups)


async def get_team_by_id(user: KeycloakUser, team_id: str) -> Team:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()
    metadata_store = app_context.get_team_metadata_store()

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; cannot retrieve team.")
        raise TeamNotFoundError(team_id)

    # Fetch the specific group from Keycloak
    try:
        raw_group = await admin.a_get_group(team_id)
    except Exception as e:
        logger.warning(f"Failed to fetch group {team_id} from Keycloak: {e}")
        raise TeamNotFoundError(team_id) from e

    if not raw_group:
        raise TeamNotFoundError(team_id)

    # Ensure team has organization relation for ReBAC
    consistency_token = await _ensure_team_organization_relations(rebac, [team_id])

    # Check user authorization for this specific team
    await rebac.check_user_permission_or_raise(user, TeamPermission.CAN_READ, team_id, consistency_token=consistency_token)

    # Create group summary from raw Keycloak data
    group_id = raw_group.get("id")
    if not group_id:
        raise TeamNotFoundError(team_id)

    group_summary = KeycloakGroupSummary(
        id=group_id,
        name=raw_group.get("name"),
        member_count=0,  # Will be populated by enrichment
    )

    # Enrich with full team data
    teams = await _enrich_groups_with_team_data(admin, rebac, metadata_store, user, [group_summary])
    return teams[0]


async def update_team(user: KeycloakUser, team_id: str, update_data: TeamUpdate) -> Team:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()
    metadata_store = app_context.get_team_metadata_store()

    admin = create_keycloak_admin(get_configuration().security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; cannot update team.")
        raise TeamNotFoundError(team_id)

    # Ensure team exists in Keycloak
    try:
        raw_group = await admin.a_get_group(team_id)
    except Exception as e:
        logger.warning(f"Failed to fetch group {team_id} from Keycloak: {e}")
        raise TeamNotFoundError(team_id) from e

    if not raw_group:
        raise TeamNotFoundError(team_id)

    # Ensure team has organization relation for ReBAC
    consistency_token = await _ensure_team_organization_relations(rebac, [team_id])

    # Check user has permission to update team info
    await rebac.check_user_permission_or_raise(user, TeamPermission.CAN_UPDATE_INFO, team_id, consistency_token=consistency_token)

    # Update metadata
    metadata_store.upsert(team_id, update_data)

    # Handle public tuple if is_private was set (leveraging idempotency)
    if update_data.is_private is not None:
        if update_data.is_private:
            # Team is private, ensure public tuple is removed
            await rebac.delete_relation(
                Relation(
                    subject=RebacReference(Resource.USER, "*"),
                    relation=RelationType.PUBLIC,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
            )
        else:
            # Team is public, ensure public tuple exists
            await rebac.add_relation(
                Relation(
                    subject=RebacReference(Resource.USER, "*"),
                    relation=RelationType.PUBLIC,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
            )

    # Return updated team
    return await get_team_by_id(user, team_id)


async def _enrich_groups_with_team_data(admin: KeycloakAdmin, rebac: RebacEngine, metadata_store, user: KeycloakUser, groups: list[KeycloakGroupSummary]) -> list[Team]:
    """Shared logic to enrich Keycloak groups with metadata, owners, and member information."""
    if not groups:
        return []

    # Batch fetch metadata for all teams
    team_ids: list[str] = [g.id for g in groups]
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
    for group_summary in groups:
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
            is_private = True

        # Check if current user is a member of this team
        member_ids = member_counts_list[team_ids.index(group_id)]
        is_member = user.uid in member_ids

        # Map to Team with id and name from Keycloak, metadata from store, owners from OpenFGA
        team = Team(
            id=group_id,
            name=_sanitize_name(group_name, fallback=group_id),
            description=description,
            banner_image_url=banner_image_url,
            owners=[user_summaries.get(owner_id) or UserSummary(id=owner_id) for owner_id in team_owners_map.get(group_id, [])],
            member_count=member_counts_map.get(group_id, 0),
            is_private=is_private,
            is_member=is_member,
        )
        teams.append(team)

    return teams


# todo: Remove when our API handle team creation/deletion and not Keycloak
async def _ensure_team_organization_relations(rebac: RebacEngine, team_ids: list[str]) -> str | None:
    """Ensure all teams have organization relation tuples in OpenFGA. This tuples are needed for all rules
    referencing orgnaization wide role (like org admin writes).

    ## Why like this ?

    As our teams are based on Keycloak, we can't always know when a new team is created and create the
    team->organization tuple at the right time. It would be great to pass thses relations as contextual tuples
    (like we do for user-(member)->team and user-(role)->organization tuples) but there is a limit of 100
    contextual tuples by request. To be able to have more that 100 teams, we were forced to do it that way.

    If in the future we don't rely on Keycloak for team creation, we can remove this.

    Returns:
        The consistency token from the write operation, to be used in subsequent reads.
    """
    if not team_ids:
        return None

    # Create relations for all teams - duplicates will be ignored by OpenFGA
    relations_to_add = [
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            relation=RelationType.ORGANIZATION,
            resource=RebacReference(Resource.TEAM, team_id),
        )
        for team_id in team_ids
    ]

    return await rebac.add_relations(relations_to_add)


async def _get_team_owners(rebac: RebacEngine, team_id: str) -> list[str]:
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
