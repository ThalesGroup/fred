from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fred_core import (
    KeycloackDisabled,
    KeycloakUser,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    TeamPermission,
    create_keycloak_admin,
)
from keycloak import KeycloakAdmin
from pydantic import BaseModel, Field, ValidationError

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyResolutionRequest,
)
from control_plane_backend.team_id import TeamId
from control_plane_backend.teams_structures import (
    AddTeamMemberRequest,
    KeycloakGroupSummary,
    KeycloakM2MDisabledError,
    RemoveTeamMemberResponse,
    Team,
    TeamMember,
    TeamNotFoundError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UserTeamRelation,
)
from control_plane_backend.users_service import get_users_by_ids
from control_plane_backend.users_structures import UserSummary

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200


class _SessionPayload(BaseModel):
    id: str = Field(..., min_length=1)
    team_id: str | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


async def list_teams(user: KeycloakUser) -> list[Team]:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    admin = create_keycloak_admin(app_context.configuration.security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; returning empty team list.")
        return []

    root_groups = await _fetch_root_keycloak_groups(admin)
    consistency_token = await rebac.ensure_team_organization_relations(
        [group.id for group in root_groups]
    )

    authorized_teams_refs = await rebac.lookup_user_resources(
        user,
        TeamPermission.CAN_READ,
        consistency_token=consistency_token,
    )
    if not isinstance(authorized_teams_refs, RebacDisabledResult):
        authorized_team_ids = {ref.id for ref in authorized_teams_refs}
        root_groups = [
            group for group in root_groups if group.id in authorized_team_ids
        ]

    return await _enrich_groups_with_team_data(admin, rebac, user, root_groups)


async def get_team_by_id(user: KeycloakUser, team_id: TeamId) -> TeamWithPermissions:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    admin, raw_group, consistency_token = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_READ],
    )
    group_summary = KeycloakGroupSummary(
        id=team_id,
        name=raw_group.get("name"),
        member_count=0,
    )

    teams = await _enrich_groups_with_team_data(admin, rebac, user, [group_summary])
    if not teams:
        raise TeamNotFoundError(team_id)

    permissions = await _get_team_permissions_for_user(
        rebac,
        user,
        team_id,
        consistency_token,
    )
    return TeamWithPermissions(**teams[0].model_dump(), permissions=permissions)


async def list_team_members(user: KeycloakUser, team_id: TeamId) -> list[TeamMember]:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    admin, _, _ = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_READ_MEMEBERS],
    )
    owner_ids, manager_ids, member_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.OWNER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MANAGER),
        _fetch_group_member_ids(admin, team_id),
    )
    user_summaries = await get_users_by_ids(member_ids)

    team_members: list[TeamMember] = []
    for member_id in member_ids:
        user_summary = user_summaries.get(member_id) or UserSummary(id=member_id)
        if member_id in owner_ids:
            relation = UserTeamRelation.OWNER
        elif member_id in manager_ids:
            relation = UserTeamRelation.MANAGER
        else:
            relation = UserTeamRelation.MEMBER
        team_members.append(TeamMember(user=user_summary, relation=relation))

    return team_members


async def add_team_member(
    user: KeycloakUser,
    team_id: TeamId,
    request: AddTeamMemberRequest,
) -> None:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    admin, _, _ = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_ADMINISTER_MEMBERS],
    )
    await _add_keycloak_user_to_group(admin, request.user_id, team_id)
    await _add_team_member_relation(rebac, team_id, request.user_id, request.relation)

    logger.info(
        "Added user %s as %s to team %s",
        request.user_id,
        request.relation.value,
        team_id,
    )


async def remove_team_member(
    user: KeycloakUser,
    team_id: TeamId,
    user_id: str,
) -> RemoveTeamMemberResponse:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    target_role = await _get_user_role_in_team(rebac, team_id, user_id)
    permission_to_check = _get_administer_permission_for_team_role_relation(target_role)

    admin, _, _ = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [permission_to_check],
    )
    await _remove_keycloak_user_from_group(admin, user_id, team_id)
    await _remove_all_team_member_relations(rebac, team_id, user_id)

    policy = evaluate_policy_for_request(
        PolicyResolutionRequest(
            team_id=team_id,
            trigger=LifecycleTrigger.MEMBER_REMOVED,
        ),
        app_context.get_policy_catalog(),
    )
    scheduled_delete_at = _utcnow() + timedelta(seconds=policy.retention_seconds)

    session_store = app_context.get_session_store()
    queue_store = app_context.get_purge_queue_store()
    payloads = await session_store.get_payloads_for_user(user_id)

    sessions_enqueued = 0
    for payload in payloads:
        try:
            session_payload = _SessionPayload.model_validate(payload)
        except ValidationError:
            logger.debug(
                "Skipping invalid session payload for user %s: %r", user_id, payload
            )
            continue

        if session_payload.team_id != team_id:
            continue

        await queue_store.enqueue(
            session_id=session_payload.id,
            team_id=team_id,
            user_id=user_id,
            due_at=scheduled_delete_at,
        )
        sessions_enqueued += 1

    logger.info(
        "Removed user %s from team %s and enqueued %d sessions for purge",
        user_id,
        team_id,
        sessions_enqueued,
    )

    return RemoveTeamMemberResponse(
        team_id=team_id,
        user_id=user_id,
        sessions_enqueued=sessions_enqueued,
        scheduled_delete_at=scheduled_delete_at,
        policy_mode=policy.mode.value,
        retention_seconds=policy.retention_seconds,
        matched_rule_id=policy.matched_rule_id,
    )


async def update_team_member(
    user: KeycloakUser,
    team_id: TeamId,
    user_id: str,
    request: UpdateTeamMemberRequest,
) -> None:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    target_current_role = await _get_user_role_in_team(rebac, team_id, user_id)
    target_wanted_role = request.relation
    permissions_to_check = [
        _get_administer_permission_for_team_role_relation(target_current_role),
        _get_administer_permission_for_team_role_relation(target_wanted_role),
    ]

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        permissions_to_check,
    )
    await _remove_all_team_member_relations(rebac, team_id, user_id)
    await _add_team_member_relation(rebac, team_id, user_id, request.relation)

    logger.info(
        "Updated user %s relation to %s in team %s",
        user_id,
        request.relation.value,
        team_id,
    )


async def _enrich_groups_with_team_data(
    admin: KeycloakAdmin,
    rebac: RebacEngine,
    user: KeycloakUser,
    groups: list[KeycloakGroupSummary],
) -> list[Team]:
    if not groups:
        return []

    team_ids: list[TeamId] = [group.id for group in groups]
    owner_ids_list, member_ids_list = await asyncio.gather(
        asyncio.gather(
            *[
                _get_team_users_by_relation(rebac, team_id, RelationType.OWNER)
                for team_id in team_ids
            ]
        ),
        asyncio.gather(
            *[_fetch_group_member_ids(admin, team_id) for team_id in team_ids]
        ),
    )

    team_owner_ids_map = {
        team_id: owner_ids for team_id, owner_ids in zip(team_ids, owner_ids_list)
    }
    team_member_ids_map = {
        team_id: member_ids for team_id, member_ids in zip(team_ids, member_ids_list)
    }
    all_owner_ids: set[str] = set().union(*owner_ids_list)
    user_summaries = await get_users_by_ids(all_owner_ids)

    teams: list[Team] = []
    for group_summary in groups:
        member_ids = team_member_ids_map.get(group_summary.id, set())
        owners = [
            user_summaries.get(owner_id) or UserSummary(id=owner_id)
            for owner_id in team_owner_ids_map.get(group_summary.id, set())
        ]
        teams.append(
            Team(
                id=group_summary.id,
                name=_sanitize_name(group_summary.name, fallback=group_summary.id),
                member_count=len(member_ids),
                owners=owners,
                is_member=user.uid in member_ids,
            )
        )

    return teams


async def _get_team_permissions_for_user(
    rebac: RebacEngine,
    user: KeycloakUser,
    team_id: TeamId,
    consistency_token: str | None = None,
) -> list[TeamPermission]:
    permissions_to_check = list(TeamPermission)
    group_relations, org_relations = await asyncio.gather(
        rebac.groups_list_to_relations(user),
        rebac.user_role_to_organization_relation(user),
    )
    contextual_relations = group_relations | org_relations

    checks = await asyncio.gather(
        *[
            rebac.has_permission(
                RebacReference(Resource.USER, user.uid),
                permission,
                RebacReference(Resource.TEAM, team_id),
                contextual_relations=contextual_relations,
                consistency_token=consistency_token,
            )
            for permission in permissions_to_check
        ]
    )
    return [
        permission
        for permission, has_permission in zip(permissions_to_check, checks)
        if has_permission
    ]


async def _get_team_users_by_relation(
    rebac: RebacEngine,
    team_id: TeamId,
    relation: RelationType,
) -> set[str]:
    subjects = await rebac.lookup_subjects(
        RebacReference(type=Resource.TEAM, id=team_id),
        relation,
        Resource.USER,
    )
    if isinstance(subjects, RebacDisabledResult):
        return set()
    return {subject.id for subject in subjects}


async def _fetch_root_keycloak_groups(
    admin: KeycloakAdmin,
) -> list[KeycloakGroupSummary]:
    groups: list[KeycloakGroupSummary] = []
    offset = 0

    while True:
        batch = await admin.a_get_groups(
            {"first": offset, "max": _GROUP_PAGE_SIZE, "briefRepresentation": True}
        )
        if not batch:
            break

        for raw_group in batch:
            if not isinstance(raw_group, dict):
                continue
            group_id = raw_group.get("id")
            if not isinstance(group_id, str) or not group_id.strip():
                continue

            groups.append(
                KeycloakGroupSummary(
                    id=TeamId(group_id),
                    name=str(raw_group.get("name")) if raw_group.get("name") else None,
                    member_count=0,
                )
            )

        if len(batch) < _GROUP_PAGE_SIZE:
            break
        offset += _GROUP_PAGE_SIZE

    return groups


async def _fetch_group_member_ids(admin: KeycloakAdmin, group_id: TeamId) -> set[str]:
    member_ids: set[str] = set()
    offset = 0

    while True:
        batch = await admin.a_get_group_members(
            group_id,
            {"first": offset, "max": _MEMBER_PAGE_SIZE, "briefRepresentation": True},
        )
        if not batch:
            break

        for member in batch:
            if not isinstance(member, dict):
                continue
            member_id = member.get("id")
            if isinstance(member_id, str) and member_id.strip():
                member_ids.add(member_id)

        if len(batch) < _MEMBER_PAGE_SIZE:
            break
        offset += _MEMBER_PAGE_SIZE

    return member_ids


def _sanitize_name(value: object, fallback: str) -> str:
    name = str(value or "").strip()
    return name or fallback


async def _validate_team_and_check_permission(
    user: KeycloakUser,
    team_id: TeamId,
    rebac: RebacEngine,
    permissions: list[TeamPermission],
) -> tuple[KeycloakAdmin, dict[str, Any], str | None]:
    app_context = ApplicationContext.get_instance()
    admin = create_keycloak_admin(app_context.configuration.security.m2m)
    if isinstance(admin, KeycloackDisabled):
        logger.info("Keycloak admin client not configured; cannot validate team.")
        raise KeycloakM2MDisabledError()

    try:
        raw_group = await admin.a_get_group(team_id)
    except Exception as exc:
        logger.warning("Failed to fetch group %s from Keycloak: %s", team_id, exc)
        raise TeamNotFoundError(team_id) from exc

    if not isinstance(raw_group, dict):
        raise TeamNotFoundError(team_id)

    consistency_token = await rebac.check_user_team_permissions_or_raise(
        user=user,
        team_id=team_id,
        permissions=permissions,
    )

    return admin, raw_group, consistency_token


async def _add_team_member_relation(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
    relation: UserTeamRelation,
) -> None:
    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, user_id),
            relation=relation.to_relation(),
            resource=RebacReference(Resource.TEAM, team_id),
        )
    )


def _get_administer_permission_for_team_role_relation(
    target: UserTeamRelation,
) -> TeamPermission:
    if target == UserTeamRelation.MANAGER:
        return TeamPermission.CAN_ADMINISTER_MANAGERS
    if target == UserTeamRelation.OWNER:
        return TeamPermission.CAN_ADMINISTER_OWNERS
    return TeamPermission.CAN_ADMINISTER_MEMBERS


async def _get_user_role_in_team(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
) -> UserTeamRelation:
    owner_ids, manager_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.OWNER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MANAGER),
    )
    if user_id in owner_ids:
        return UserTeamRelation.OWNER
    if user_id in manager_ids:
        return UserTeamRelation.MANAGER
    return UserTeamRelation.MEMBER


async def _remove_all_team_member_relations(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
) -> None:
    await rebac.delete_relations(
        [
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.OWNER,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.MANAGER,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.MEMBER,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
        ]
    )


async def _add_keycloak_user_to_group(
    admin: KeycloakAdmin,
    user_id: str,
    group_id: TeamId,
) -> None:
    await admin.a_group_user_add(user_id, group_id)


async def _remove_keycloak_user_from_group(
    admin: KeycloakAdmin,
    user_id: str,
    group_id: TeamId,
) -> None:
    await admin.a_group_user_remove(user_id, group_id)
