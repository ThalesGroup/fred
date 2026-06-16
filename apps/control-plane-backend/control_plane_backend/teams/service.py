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
    ORGANIZATION_ID,
    KeycloakUser,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    SessionSchema,
    TeamPermission,
)
from fred_core.common import TeamId
from fred_core.scheduler import SchedulerBackend
from fred_core.store import ContentStore
from fred_core.teams.metadata_store import TeamMetadata, TeamMetadataPatch
from sqlalchemy.exc import IntegrityError

from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyResolutionRequest,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    BannerUploadError,
    CreateTeamRequest,
    PersonalTeamDeletionError,
    RemoveTeamMemberResponse,
    Team,
    TeamAlreadyExistsError,
    TeamMember,
    TeamNotFoundError,
    TeamOwnerConstraintError,
    TeamWithPermissions,
    UpdateTeamMemberRequest,
    UpdateTeamRequest,
    UserTeamRelation,
)
from control_plane_backend.teams.system import (
    get_system_team,
    list_system_teams,
    to_team_summary,
)
from control_plane_backend.users.schemas import UserSummary

logger = logging.getLogger(__name__)

_MAX_BANNER_FILE_SIZE_BYTES = 5 * 1024 * 1024
_ALLOWED_BANNER_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
_BANNER_EXTENSION_BY_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


async def list_teams(
    user: KeycloakUser,
    deps: TeamServiceDependencies,
) -> list[Team]:
    personal_limit = deps.configuration.app.personal_max_resources_storage_size
    selectable_teams: dict[str, Team] = {
        str(team.id): to_team_summary(team)
        for team in await list_system_teams(user, personal_limit)
    }

    rebac = deps.rebac
    all_metadata = await deps.get_team_metadata_store().list_all()
    if not all_metadata:
        return list(selectable_teams.values())

    team_ids = [m.id for m in all_metadata]
    consistency_token = await rebac.ensure_team_organization_relations(team_ids)

    authorized_teams_refs = await rebac.lookup_user_resources(
        user,
        TeamPermission.CAN_READ,
        consistency_token=consistency_token,
    )
    if not isinstance(authorized_teams_refs, RebacDisabledResult):
        authorized_team_ids = {ref.id for ref in authorized_teams_refs}
        all_metadata = [m for m in all_metadata if m.id in authorized_team_ids]

    owner_ids_list = await asyncio.gather(
        *[
            _get_team_users_by_relation(rebac, m.id, RelationType.OWNER)
            for m in all_metadata
        ]
    )
    all_owner_ids: set[str] = set().union(*owner_ids_list) if owner_ids_list else set()
    user_summaries = await deps.get_users_by_ids(all_owner_ids)
    content_store = deps.get_content_store()

    for metadata, owner_ids in zip(all_metadata, owner_ids_list):
        owners = _dedupe_user_summaries_by_display_key(
            [user_summaries.get(oid) or UserSummary(id=oid) for oid in owner_ids]
        )
        selectable_teams[str(metadata.id)] = _team_from_metadata(
            metadata, owners, deps.configuration, content_store, is_member=True
        )

    return list(selectable_teams.values())


async def get_team_by_id(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> TeamWithPermissions:
    personal_limit = deps.configuration.app.personal_max_resources_storage_size
    system_team = await get_system_team(user, team_id, personal_limit)
    if system_team is not None:
        return system_team

    rebac = deps.rebac
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    consistency_token = await rebac.check_user_team_permissions_or_raise(
        user=user,
        team_id=team_id,
        permissions=[TeamPermission.CAN_READ],
    )

    owner_ids = await _get_team_users_by_relation(rebac, team_id, RelationType.OWNER)
    user_summaries = await deps.get_users_by_ids(owner_ids)
    owners = _dedupe_user_summaries_by_display_key(
        [user_summaries.get(oid) or UserSummary(id=oid) for oid in owner_ids]
    )
    content_store = deps.get_content_store()
    team = _team_from_metadata(
        metadata, owners, deps.configuration, content_store, is_member=True
    )

    permissions = await _get_team_permissions_for_user(
        rebac, user, team_id, consistency_token
    )
    return TeamWithPermissions(**team.model_dump(), permissions=permissions)


async def update_team(
    user: KeycloakUser,
    team_id: TeamId,
    request: UpdateTeamRequest,
    deps: TeamServiceDependencies,
) -> TeamWithPermissions:
    """
    Update one team metadata document and visibility settings.

    Why this function exists:
    - collaborative teams need a single business path for editable metadata and
      public/private visibility toggles

    How to use it:
    - call it from the team PATCH route after authenticating the current user
    - pass request-scoped team dependencies when available

    Example:
    - `team = await update_team(user, TeamId("fredlab"), request, deps)`
    """
    rebac = deps.rebac

    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    consistency_token = await rebac.check_user_team_permissions_or_raise(
        user=user,
        team_id=team_id,
        permissions=[TeamPermission.CAN_UPDATE_INFO],
    )

    # PATCH with no fields is a no-op.
    if request.model_fields_set:
        patch = TeamMetadataPatch.model_validate(request.model_dump(exclude_unset=True))
        metadata = await deps.get_team_metadata_store().upsert(team_id, patch)

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

    owner_ids = await _get_team_users_by_relation(rebac, team_id, RelationType.OWNER)
    user_summaries = await deps.get_users_by_ids(owner_ids)
    owners = _dedupe_user_summaries_by_display_key(
        [user_summaries.get(oid) or UserSummary(id=oid) for oid in owner_ids]
    )
    team = _team_from_metadata(
        metadata, owners, deps.configuration, deps.get_content_store(), is_member=True
    )

    permissions = await _get_team_permissions_for_user(
        rebac,
        user,
        team_id,
        consistency_token,
    )
    return TeamWithPermissions(**team.model_dump(), permissions=permissions)


async def upload_team_banner(
    user: KeycloakUser,
    team_id: TeamId,
    file: UploadFile,
    deps: TeamServiceDependencies,
) -> None:
    """
    Validate and upload one team banner image to the configured content store.

    Why this function exists:
    - team customization needs one backend-owned upload path with size and MIME
      validation before metadata is persisted

    How to use it:
    - call from the banner upload route with the authenticated user and the raw
      FastAPI `UploadFile`
    - pass request-scoped dependencies when available

    Example:
    - `await upload_team_banner(user, TeamId("fredlab"), file, deps)`
    """
    rebac = deps.rebac

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_UPDATE_INFO],
        deps,
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
        deps.get_content_store().put_object(
            object_storage_key,
            BytesIO(payload),
            content_type=detected_content_type,
        )

        await deps.get_team_metadata_store().upsert(
            team_id,
            TeamMetadataPatch(banner_object_storage_key=object_storage_key),
        )
        logger.info("Uploaded banner for team %s: %s", team_id, object_storage_key)
    finally:
        await file.close()


async def list_team_members(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> list[TeamMember]:
    """
    Resolve one team member list with role decoration for the current operator.

    Why this function exists:
    - the frontend and CLI need one rendered member list driven entirely by
      ReBAC role relations

    How to use it:
    - call from `/teams/{team_id}/members`
    - pass request-scoped dependencies when available

    Example:
    - `members = await list_team_members(user, TeamId("fredlab"), deps)`
    """
    rebac = deps.rebac

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_READ_MEMEBERS],
        deps,
    )
    owner_ids, manager_ids, member_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.OWNER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MANAGER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MEMBER),
    )
    user_summaries = await deps.get_users_by_ids(member_ids)

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
    deps: TeamServiceDependencies,
) -> None:
    """
    Add one user to a team and persist the requested team role relation.

    Why this function exists:
    - team administration needs one business path for ReBAC role relations

    How to use it:
    - call from the team-membership POST route
    - pass request-scoped dependencies when available

    Example:
    - `await add_team_member(user, TeamId("fredlab"), request, deps)`
    """
    rebac = deps.rebac

    permission_to_check = _get_administer_permission_for_team_role_relation(
        request.relation
    )
    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [permission_to_check],
        deps,
    )
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
    deps: TeamServiceDependencies,
) -> RemoveTeamMemberResponse:
    """
    Remove one team member and enqueue any matching session lifecycle cleanup.

    Why this function exists:
    - membership removal must keep ReBAC state consistent and trigger the
      configured session-retention policy for the removed user

    How to use it:
    - call from the team-membership DELETE route
    - pass request-scoped dependencies when available

    Example:
    - `result = await remove_team_member(user, TeamId("swiftpost"), "user-1", deps)`
    """
    rebac = deps.rebac

    target_role = await _get_user_role_in_team(rebac, team_id, user_id)
    await _ensure_team_keeps_at_least_one_owner(
        rebac=rebac,
        team_id=team_id,
        user_id=user_id,
        current_role=target_role,
        wanted_role=None,
    )
    permission_to_check = _get_administer_permission_for_team_role_relation(target_role)

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [permission_to_check],
        deps,
    )
    await _remove_all_team_member_relations(rebac, team_id, user_id)

    policy = evaluate_policy_for_request(
        PolicyResolutionRequest(
            team_id=team_id,
            trigger=LifecycleTrigger.MEMBER_REMOVED,
        ),
        deps.get_policy_catalog(),
    )
    scheduled_delete_at = _utcnow() + timedelta(seconds=policy.retention_seconds)

    session_store = deps.get_session_store()
    queue_store = deps.get_purge_queue_store()
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
        await _run_lifecycle_if_in_memory_scheduler(deps)

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
    deps: TeamServiceDependencies,
) -> None:
    if not deps.configuration.scheduler.enabled:
        return
    if deps.scheduler_backend != SchedulerBackend.MEMORY:
        return

    result = await deps.run_lifecycle_manager_once_in_memory(LifecycleManagerInput())
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
    deps: TeamServiceDependencies,
) -> None:
    """
    Change one team member role while enforcing owner-safety constraints.

    Why this function exists:
    - role updates must check both the current and target permissions while
      preserving the invariant that a team always keeps at least one owner

    How to use it:
    - call from the team-membership PATCH route
    - pass request-scoped dependencies when available

    Example:
    - `await update_team_member(user, TeamId("fredlab"), "user-1", request, deps)`
    """
    rebac = deps.rebac

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
        deps,
    )
    await _remove_all_team_member_relations(rebac, team_id, user_id)
    await _add_team_member_relation(rebac, team_id, user_id, request.relation)

    logger.info(
        "Updated user %s relation to %s in team %s",
        user_id,
        request.relation.value,
        team_id,
    )


async def create_team(
    user: KeycloakUser,
    request: CreateTeamRequest,
    deps: TeamServiceDependencies,
) -> Team:
    """Create a new collaborative team owned by the calling admin.

    Why this function exists:
    - platform admins need a programmatic path to provision teams without
      going through the Keycloak admin console
    - team data is written to ``teammetadata`` (PostgreSQL) and the ownership
      relation is registered in the ReBAC engine so the team is immediately
      visible and permission-checked through the standard read path

    How to use it:
    - call from the ``POST /teams`` route after verifying the caller is admin
    - pass request-scoped team dependencies when available

    Example:
    - ``team = await create_team(user, CreateTeamRequest(name="my-team"), deps)``
    """
    team_id = TeamId(str(uuid4()))
    store = deps.get_team_metadata_store()

    try:
        metadata = await store.insert(
            team_id=team_id,
            name=request.name,
            description=request.description,
            is_private=request.is_private,
        )
    except IntegrityError as exc:
        raise TeamAlreadyExistsError(team_id) from exc

    rebac = deps.rebac
    await rebac.ensure_team_organization_relations([team_id])
    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, user.uid),
            relation=RelationType.OWNER,
            resource=RebacReference(Resource.TEAM, team_id),
        )
    )
    if not request.is_private:
        await rebac.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, "*"),
                relation=RelationType.PUBLIC,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )

    creator = UserSummary(id=user.uid, username=user.username, email=user.email)
    content_store = deps.get_content_store()
    logger.info("Created team %s by admin %s", team_id, user.uid)
    return _team_from_metadata(
        metadata, [creator], deps.configuration, content_store, is_member=True
    )


async def delete_team(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> None:
    """Delete a collaborative team and clean up its ReBAC relations.

    Why this function exists:
    - platform admins need a way to remove teams that are no longer in use
      without requiring Keycloak console access
    - deletion removes the ``teammetadata`` row and all associated ReBAC
      relations (org link, public visibility, owner, manager, and plain
      member roles) so the team immediately disappears from every read path
      and no orphaned tuples are left behind in OpenFGA

    How to use it:
    - call from the ``DELETE /teams/{team_id}`` route after verifying the caller is admin
    - personal teams (``personal-`` prefix) are rejected with ``PersonalTeamDeletionError``

    Example:
    - ``await delete_team(user, TeamId("my-team"), deps)``
    """
    if str(team_id).startswith("personal-"):
        raise PersonalTeamDeletionError(team_id)

    store = deps.get_team_metadata_store()
    metadata = await store.get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    rebac = deps.rebac
    # `member` is the union of {owner, manager, direct member} in the FGA
    # model, so this also returns owners/managers; deleting a MEMBER tuple
    # for those is a safe no-op (their actual tuple is OWNER/MANAGER and is
    # deleted below). Without this, plain members leave a dangling
    # (user, member, team) tuple in OpenFGA after the team row is gone.
    owner_ids, manager_ids, member_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.OWNER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MANAGER),
        _get_team_users_by_relation(rebac, team_id, RelationType.MEMBER),
    )

    relations_to_delete: list[Relation] = [
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
            relation=RelationType.ORGANIZATION,
            resource=RebacReference(Resource.TEAM, team_id),
        ),
        Relation(
            subject=RebacReference(Resource.USER, "*"),
            relation=RelationType.PUBLIC,
            resource=RebacReference(Resource.TEAM, team_id),
        ),
    ]
    for uid in owner_ids:
        relations_to_delete.append(
            Relation(
                subject=RebacReference(Resource.USER, uid),
                relation=RelationType.OWNER,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
    for uid in manager_ids:
        relations_to_delete.append(
            Relation(
                subject=RebacReference(Resource.USER, uid),
                relation=RelationType.MANAGER,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )
    for uid in member_ids:
        relations_to_delete.append(
            Relation(
                subject=RebacReference(Resource.USER, uid),
                relation=RelationType.MEMBER,
                resource=RebacReference(Resource.TEAM, team_id),
            )
        )

    await rebac.delete_relations(relations_to_delete)
    await store.delete_by_id(team_id)
    logger.info("Deleted team %s by admin %s", team_id, user.uid)


def _dedupe_user_summaries_by_display_key(
    users: list[UserSummary],
) -> list[UserSummary]:
    """
    Remove duplicate user summaries that render as the same person.

    Why this function exists:
    - some legacy ReBAC relations may still reference one username while newer
      relations reference the canonical Keycloak user id for that same person
    - team summaries should not expose confusing duplicates such as
      `marc, marc` when both identifiers resolve to the same visible label

    How to use it:
    - pass the small list of user summaries prepared for one rendered team
    - the function keeps the first summary for each visible label and preserves
      the original order

    Example:
    - `owners = _dedupe_user_summaries_by_display_key(owners)`
    """

    deduped_users: list[UserSummary] = []
    seen_display_keys: set[str] = set()

    for user in users:
        display_key = (user.username or user.id).strip().casefold()
        if display_key in seen_display_keys:
            continue
        seen_display_keys.add(display_key)
        deduped_users.append(user)

    return deduped_users


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


def _sanitize_name(value: object, fallback: str) -> str:
    name = str(value or "").strip()
    return name or fallback


def _resolve_banner_url(
    content_store: ContentStore,
    metadata: TeamMetadata,
) -> str | None:
    key = metadata.banner_object_storage_key
    if not key:
        return None
    if _is_absolute_url(key):
        return key
    try:
        return content_store.get_presigned_url(key, expires=timedelta(hours=1))
    except Exception as exc:
        logger.warning(
            "Failed to generate presigned URL for team %s banner: %s", metadata.id, exc
        )
        return None


def _team_from_metadata(
    metadata: TeamMetadata,
    owners: list[UserSummary],
    configuration: Any,
    content_store: ContentStore,
    *,
    is_member: bool = False,
) -> Team:
    max_storage = (
        metadata.max_resources_storage_size
        if metadata.max_resources_storage_size is not None
        else configuration.app.default_team_max_resources_storage_size
    )
    return Team(
        id=metadata.id,
        name=_sanitize_name(metadata.name, str(metadata.id)),
        member_count=None,
        owners=owners,
        is_member=is_member,
        description=metadata.description,
        is_private=metadata.is_private,
        banner_image_url=_resolve_banner_url(content_store, metadata),
        max_resources_storage_size=max_storage,
        current_resources_storage_size=metadata.current_resources_storage_size,
    )


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
    deps: TeamServiceDependencies,
) -> str | None:
    """
    Verify one team exists and the caller has the requested permissions.

    Why this function exists:
    - team write and read operations all need the same validation path for
      team existence plus ReBAC permission enforcement

    How to use it:
    - pass the current user, target team id, required permissions, and the
      explicit team-service dependency bundle
    - expect `TeamNotFoundError` on unknown teams

    Example:
    - `token = await _validate_team_and_check_permission(user, team_id, rebac, permissions, deps)`
    """
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    return await rebac.check_user_team_permissions_or_raise(
        user=user,
        team_id=team_id,
        permissions=permissions,
    )


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
