from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import UploadFile
from fred_core import (
    KeycloackDisabled,
    KeycloakUser,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    SessionSchema,
    TeamPermission,
    create_keycloak_admin,
)
from fred_core.common import TeamId
from fred_core.scheduler import SchedulerBackend
from keycloak import KeycloakAdmin
from keycloak.exceptions import KeycloakDeleteError, KeycloakPutError

from control_plane_backend.application_context import ApplicationContext
from control_plane_backend.scheduler.memory import run_lifecycle_manager_once_in_memory
from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyResolutionRequest,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.team_metadata_store import TeamMetadataPatch
from control_plane_backend.teams_structures import (
    AddTeamMemberRequest,
    BannerUploadError,
    KeycloakGroupSummary,
    KeycloakM2MDisabledError,
    RemoveTeamMemberResponse,
    Team,
    TeamMember,
    TeamMembershipSyncError,
    TeamNotFoundError,
    TeamOwnerConstraintError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
    UserTeamRelation,
)
from control_plane_backend.users_service import get_users_by_ids
from control_plane_backend.users_structures import UserSummary

logger = logging.getLogger(__name__)

_GROUP_PAGE_SIZE = 200
_MEMBER_PAGE_SIZE = 200
_MAX_BANNER_FILE_SIZE_BYTES = 5 * 1024 * 1024
_ALLOWED_BANNER_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_BANNER_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


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


async def update_team(
    user: KeycloakUser,
    team_id: TeamId,
    request: UpdateTeamRequest,
) -> TeamWithPermissions:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    admin, raw_group, consistency_token = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_UPDATE_INFO],
    )

    # PATCH with no fields is a no-op.
    if request.model_fields_set:
        patch = TeamMetadataPatch.model_validate(request.model_dump(exclude_unset=True))
        await app_context.get_team_metadata_store().upsert(team_id, patch)

        if "is_private" in request.model_fields_set:
            public_relation = Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=RebacReference(Resource.TEAM, team_id),
            )
            if request.is_private:
                await rebac.delete_relations([public_relation])
            else:
                await rebac.add_relation(public_relation)

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


async def upload_team_banner(
    user: KeycloakUser,
    team_id: TeamId,
    file: UploadFile,
) -> None:
    app_context = ApplicationContext.get_instance()
    rebac = app_context.get_rebac_engine()

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_UPDATE_INFO],
    )

    try:
        payload = await file.read(_MAX_BANNER_FILE_SIZE_BYTES + 1)
        if len(payload) > _MAX_BANNER_FILE_SIZE_BYTES:
            raise BannerUploadError(
                f"File too large: {len(payload)} bytes (max: {_MAX_BANNER_FILE_SIZE_BYTES})"
            )
        if not payload:
            raise BannerUploadError("Empty file upload is not allowed")

        declared_content_type = (
            file.content_type or "application/octet-stream"
        ).lower()
        if declared_content_type not in _ALLOWED_BANNER_MIME_TYPES:
            raise BannerUploadError(f"Invalid content type: {declared_content_type}")

        detected_content_type = _detect_image_content_type(payload)
        if detected_content_type not in _ALLOWED_BANNER_MIME_TYPES:
            raise BannerUploadError(
                f"File content doesn't match allowed image formats: {detected_content_type or 'unknown'}"
            )
        if detected_content_type != declared_content_type:
            raise BannerUploadError(
                f"File content doesn't match declared content type: {detected_content_type}"
            )

        file_ext = Path(file.filename or "").suffix.lower()
        if not file_ext:
            file_ext = _BANNER_EXTENSION_BY_MIME[detected_content_type]

        object_storage_key = f"teams/{team_id}/banner-{uuid4().hex}{file_ext}"
        app_context.get_content_store().put_object(
            object_storage_key,
            BytesIO(payload),
            content_type=detected_content_type,
        )

        await app_context.get_team_metadata_store().upsert(
            team_id,
            TeamMetadataPatch(banner_object_storage_key=object_storage_key),
        )
        logger.info("Uploaded banner for team %s: %s", team_id, object_storage_key)
    finally:
        await file.close()


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

    permission_to_check = _get_administer_permission_for_team_role_relation(
        request.relation
    )
    admin, _, _ = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [permission_to_check],
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
    await _ensure_team_keeps_at_least_one_owner(
        rebac=rebac,
        team_id=team_id,
        user_id=user_id,
        current_role=target_role,
        wanted_role=None,
    )
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
    sessions: list[SessionSchema] = await session_store.get_for_user(user_id, team_id)

    sessions_enqueued = 0
    for session in sessions:
        await queue_store.enqueue(
            session_id=session.id,
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
    if sessions_enqueued > 0:
        await _run_lifecycle_if_in_memory_scheduler(app_context)

    return RemoveTeamMemberResponse(
        team_id=team_id,
        user_id=user_id,
        sessions_enqueued=sessions_enqueued,
        scheduled_delete_at=scheduled_delete_at,
        policy_mode=policy.mode.value,
        retention_seconds=policy.retention_seconds,
        matched_rule_id=policy.matched_rule_id,
    )


async def _run_lifecycle_if_in_memory_scheduler(
    app_context: ApplicationContext,
) -> None:
    if not app_context.configuration.scheduler.enabled:
        return
    if app_context.get_scheduler_backend() != SchedulerBackend.MEMORY:
        return

    result = await run_lifecycle_manager_once_in_memory(LifecycleManagerInput())
    logger.info(
        "[LIFECYCLE][IN_MEMORY] post-member-removal pass scanned=%s deleted=%s dry_run_actions=%s",
        result.scanned,
        result.deleted,
        result.dry_run_actions,
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
    await _ensure_team_keeps_at_least_one_owner(
        rebac=rebac,
        team_id=team_id,
        user_id=user_id,
        current_role=target_current_role,
        wanted_role=target_wanted_role,
    )
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

    app_context = ApplicationContext.get_instance()
    content_store = app_context.get_content_store()
    team_ids: list[TeamId] = [group.id for group in groups]
    team_metadata_by_id = await app_context.get_team_metadata_store().get_by_team_ids(
        team_ids
    )
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
        metadata = team_metadata_by_id.get(group_summary.id)
        banner_image_url: str | None = None
        if metadata and metadata.banner_object_storage_key:
            if _is_absolute_url(metadata.banner_object_storage_key):
                banner_image_url = metadata.banner_object_storage_key
            else:
                try:
                    banner_image_url = content_store.get_presigned_url(
                        metadata.banner_object_storage_key,
                        expires=timedelta(hours=1),
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to generate presigned URL for team %s banner: %s",
                        group_summary.id,
                        exc,
                    )

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
                description=metadata.description if metadata else None,
                is_private=metadata.is_private if metadata else True,
                banner_image_url=banner_image_url,
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


def _detect_image_content_type(payload: bytes) -> str | None:
    if payload.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(payload) >= 12 and payload[0:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "image/webp"
    return None


def _is_absolute_url(value: str) -> bool:
    candidate = value.lower()
    return candidate.startswith("http://") or candidate.startswith("https://")


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


async def _ensure_team_keeps_at_least_one_owner(
    *,
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
    current_role: UserTeamRelation,
    wanted_role: UserTeamRelation | None,
) -> None:
    is_owner_demotion_or_removal = current_role == UserTeamRelation.OWNER and (
        wanted_role is None or wanted_role != UserTeamRelation.OWNER
    )
    if not is_owner_demotion_or_removal:
        return

    owner_ids = await _get_team_users_by_relation(rebac, team_id, RelationType.OWNER)
    if user_id in owner_ids and len(owner_ids) <= 1:
        raise TeamOwnerConstraintError(
            "Operation denied: a team must keep at least one owner."
        )


async def _add_keycloak_user_to_group(
    admin: KeycloakAdmin,
    user_id: str,
    group_id: TeamId,
) -> None:
    try:
        await admin.a_group_user_add(user_id, group_id)
    except KeycloakPutError as exc:
        raise _map_keycloak_membership_error(
            exc=exc,
            operation="add",
            user_id=user_id,
            group_id=group_id,
        ) from exc


async def _remove_keycloak_user_from_group(
    admin: KeycloakAdmin,
    user_id: str,
    group_id: TeamId,
) -> None:
    try:
        await admin.a_group_user_remove(user_id, group_id)
    except KeycloakDeleteError as exc:
        raise _map_keycloak_membership_error(
            exc=exc,
            operation="remove",
            user_id=user_id,
            group_id=group_id,
        ) from exc


def _map_keycloak_membership_error(
    *,
    exc: KeycloakPutError | KeycloakDeleteError,
    operation: str,
    user_id: str,
    group_id: TeamId,
) -> TeamMembershipSyncError:
    status_code = exc.response_code or 502

    if status_code == 403:
        return TeamMembershipSyncError(
            status_code=403,
            detail=(
                "Control Plane is not allowed to manage team membership in Keycloak. "
                "Ask platform admin to grant realm-management/manage-users "
                "to the 'control-plane' client service account."
            ),
        )

    if status_code == 404:
        return TeamMembershipSyncError(
            status_code=404,
            detail=(
                f"Cannot {operation} team membership: user '{user_id}' or team "
                f"'{group_id}' does not exist in Keycloak."
            ),
        )

    logger.warning(
        "Keycloak membership %s failed for user=%s team=%s status=%s body=%r",
        operation,
        user_id,
        group_id,
        status_code,
        exc.response_body,
    )
    return TeamMembershipSyncError(
        status_code=502,
        detail=(
            "Keycloak rejected the team membership update. "
            "Check control-plane service-account permissions and Keycloak logs."
        ),
    )
