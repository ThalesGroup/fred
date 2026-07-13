from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from fred_core import (
    ORGANIZATION_ID,
    SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS,
    KeycloakUser,
    OrganizationPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
    SessionSchema,
    TeamPermission,
    is_service_agent,
)
from fred_core.common import TeamId, is_personal_team_id
from fred_core.scheduler import SchedulerBackend
from fred_core.teams.metadata_store import TeamMetadata, TeamMetadataPatch
from sqlalchemy.exc import IntegrityError

from control_plane_backend.scheduler.policies.policy_engine import (
    evaluate_policy_for_request,
)
from control_plane_backend.scheduler.policies.policy_models import (
    LifecycleTrigger,
    PolicyResolutionRequest,
)
from control_plane_backend.scheduler.policies.retention_resolver import (
    FieldRetentionResolution,
    resolve_team_retention_view,
)
from control_plane_backend.scheduler.temporal.structures import LifecycleManagerInput
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import (
    AddTeamMemberRequest,
    BannerUploadError,
    CreateTeamRequest,
    GrantTeamMemberRoleRequest,
    RemoveTeamMemberResponse,
    RetentionFieldView,
    RetentionUpdateError,
    Team,
    TeamAdminConstraintError,
    TeamAlreadyExistsError,
    TeamMember,
    TeamMemberLastRoleError,
    TeamMemberRoleNotHeldError,
    TeamNotFoundError,
    TeamRescueNotOrphanedError,
    TeamRetentionView,
    TeamWithPermissions,
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


def _to_retention_field_view(
    resolution: FieldRetentionResolution,
) -> RetentionFieldView:
    """Map one resolver ``FieldRetentionResolution`` to its API view."""
    return RetentionFieldView(
        platform_max=resolution.platform_max,
        team_value=resolution.team_value,
        effective=resolution.effective,
        source=resolution.source,
        would_exceed=resolution.would_exceed,
    )


async def _resolve_team_retention_view(
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> TeamRetentionView:
    """Resolve the per-team retention view off the fetched team metadata record.

    CTRLP-12 (RFC §3.B): the per-team values live on ``team_metadata`` — no
    separate override store. The clamp ("platform caps, team may only tighten")
    stays in the pure retention resolver; here we only read the stored values and
    the platform caps (policy catalog) and hand them to it.
    """
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    resolution = resolve_team_retention_view(
        policy=deps.get_policy_catalog().conversation_policies.purge,
        team_id=team_id,
        team_delete_grace_override=metadata.team_delete_grace if metadata else None,
        max_idle_override=metadata.max_idle if metadata else None,
    )
    return TeamRetentionView(
        team_delete_grace=_to_retention_field_view(resolution.team_delete_grace),
        max_idle=_to_retention_field_view(resolution.max_idle),
    )


async def _reject_retention_overflow(
    team_id: TeamId,
    request: UpdateTeamRequest,
    deps: TeamServiceDependencies,
) -> None:
    """Raise 422 if a PATCH's retention values exceed the platform cap.

    Partial semantics: overlay only the *provided* retention fields over the
    current stored values, then resolve. ``would_exceed`` (over the cap, or no
    cap configured at all) is rejected server-side — the client value is never
    trusted. Called only when a retention field is in the PATCH set, so a lowered
    platform cap never spuriously fails an unrelated metadata edit.
    """
    existing = await deps.get_team_metadata_store().get_by_team_id(team_id)
    provided = request.model_dump(exclude_unset=True)
    grace = provided.get(
        "team_delete_grace",
        existing.team_delete_grace if existing else None,
    )
    idle = provided.get("max_idle", existing.max_idle if existing else None)
    resolution = resolve_team_retention_view(
        policy=deps.get_policy_catalog().conversation_policies.purge,
        team_id=team_id,
        team_delete_grace_override=grace,
        max_idle_override=idle,
    )
    exceeded = [
        name
        for name, field in (
            ("team_delete_grace", resolution.team_delete_grace),
            ("max_idle", resolution.max_idle),
        )
        if field.would_exceed
    ]
    if exceeded:
        raise RetentionUpdateError(
            "Retention value exceeds the platform cap for: "
            + ", ".join(exceeded)
            + " (team may only tighten below the platform cap)."
        )


async def list_teams(
    user: KeycloakUser,
    deps: TeamServiceDependencies,
) -> list[Team]:
    """List all teams the caller may read, including reserved system teams.

    Why this function exists:
    - frontend team discovery should treat `personal` as a normal selectable
      team instead of relying on bootstrap-only special casing

    How to use it:
    - call from `/teams` or any backend flow that needs the user-visible team
      list

    Example:
    - `teams = await list_teams(user, deps)`
    """
    return await _list_teams(user, deps, filter_by_can_read=True)


async def list_all_teams_unfiltered(
    user: KeycloakUser,
    deps: TeamServiceDependencies,
) -> list[Team]:
    """Same as `list_teams` but without the per-caller `CAN_READ` filter — callers MUST already have verified `OrganizationPermission.CAN_MANAGE_PLATFORM` (e.g. `compute_platform_stats`)."""
    return await _list_teams(user, deps, filter_by_can_read=False)


async def list_all_teams_for_registry(
    user: KeycloakUser,
    deps: TeamServiceDependencies,
) -> list[Team]:
    """List every team in the registry (RFC §32, `GET /teams/all`).

    Why this function exists:
    - platform_admin needs a registry-governance view of every team that is
      gated on `can_list_all_teams`, distinct from `can_manage_platform`
      (`compute_platform_stats`'s caller) — narrower intent, own capability

    How to use it:
    - call from the platform-admin-gated `GET /teams/all` route

    Example:
    - `teams = await list_all_teams_for_registry(user, deps)`
    """
    await deps.rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_LIST_ALL_TEAMS, ORGANIZATION_ID
    )
    teams = await list_all_teams_unfiltered(user, deps)
    # `list_all_teams_unfiltered` mixes in the caller's own personal space
    # (see `_list_teams` below — `stats.py` filters the same way for the same
    # reason). The registry is `team_metadata_store` rows only (RFC §32);
    # a personal space never had a row there, so it isn't "in the registry".
    return [team for team in teams if not is_personal_team_id(str(team.id))]


async def delete_team(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> None:
    """Delete one team's registry entry and every relation referencing it (RFC §32).

    Why this function exists:
    - `platform_admin` needs a way to remove a team from the registry without
      ever touching that team's data through any other surface

    How to use it:
    - call from the platform-admin-gated `DELETE /teams/{team_id}` route

    Example:
    - `await delete_team(user, TeamId("swiftpost"), deps)`
    """
    rebac = deps.rebac
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_DELETE_TEAM, ORGANIZATION_ID
    )

    store = deps.get_team_metadata_store()
    metadata = await store.get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    await rebac.delete_all_relations_of_reference(
        RebacReference(Resource.TEAM, team_id)
    )
    await store.delete(team_id)

    logger.info(
        "Deleted team %s (%s) via platform-admin registry action",
        team_id,
        metadata.name,
    )


async def rescue_team_admin(
    user: KeycloakUser,
    team_id: TeamId,
    user_id: str,
    deps: TeamServiceDependencies,
) -> None:
    """Grant `team_admin` to a user on an orphaned team (RFC §32).

    Why this function exists:
    - a team can end up with zero `team_admin` (e.g. its last admin's account
      was removed) with no other path to recover it, since ordinary membership
      endpoints all require an existing `team_admin` to call them

    Safety property (do not relax): only ever writes the relation when the
    team currently has zero `team_admin` — this is what makes the action
    structurally different from the `§24.7` escalation that was tried and
    reverted (a standing grant reachable on every team, forever). A team with
    an active admin always rejects with `TeamRescueNotOrphanedError`.

    AUTHZ-05 post-implementation review finding: the zero-admin check and the
    relation write are two separate OpenFGA calls — OpenFGA cannot express a
    conditional write, so without serializing concurrent callers, two
    simultaneous rescues of the same orphaned team could both pass the check
    before either writes, granting two admins instead of the intended one.
    Held under `TeamMetadataStore.advisory_lock`, keyed by this team, so only
    one caller at a time can be inside the check-then-write window.

    How to use it:
    - call from the platform-admin-gated `POST /teams/{team_id}/rescue-admin` route

    Example:
    - `await rescue_team_admin(user, TeamId("swiftpost"), "alice-sub", deps)`
    """
    rebac = deps.rebac
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_RESCUE_TEAM_ADMIN, ORGANIZATION_ID
    )

    store = deps.get_team_metadata_store()
    metadata = await store.get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    async with store.advisory_lock(f"rescue_team_admin:{team_id}"):
        existing_admin_ids = await _get_team_users_by_relation(
            rebac, team_id, RelationType.TEAM_ADMIN
        )
        if existing_admin_ids:
            raise TeamRescueNotOrphanedError(team_id, existing_admin_ids)

        await _add_team_member_relation(
            rebac, team_id, user_id, UserTeamRelation.TEAM_ADMIN
        )

    logger.info(
        "Rescued team %s (%s): granted team_admin to %s via platform-admin "
        "registry action (team had zero team_admin)",
        team_id,
        metadata.name,
        user_id,
    )


async def _list_teams(
    user: KeycloakUser,
    deps: TeamServiceDependencies,
    *,
    filter_by_can_read: bool,
) -> list[Team]:
    personal_limit = deps.configuration.app.personal_max_resources_storage_size
    selectable_teams: dict[str, Team] = {
        str(team.id): to_team_summary(team)
        for team in await list_system_teams(user, personal_limit)
    }

    rebac = deps.rebac

    # AUTHZ-05 review item 9 (RFC Part 6 §29-32): the registry lives in
    # `team_metadata_store`, not Keycloak root groups.
    all_teams = await deps.get_team_metadata_store().list_all()
    consistency_token = await rebac.ensure_team_organization_relations(
        [metadata.id for metadata in all_teams]
    )

    if filter_by_can_read:
        authorized_teams_refs = await rebac.lookup_user_resources(
            user,
            TeamPermission.CAN_READ,
            consistency_token=consistency_token,
        )
        if not isinstance(authorized_teams_refs, RebacDisabledResult):
            authorized_team_ids = {ref.id for ref in authorized_teams_refs}
            all_teams = [
                metadata for metadata in all_teams if metadata.id in authorized_team_ids
            ]

    collaborative_teams = await _enrich_teams_with_membership(
        rebac,
        user,
        all_teams,
        deps,
    )
    for team in collaborative_teams:
        selectable_teams[str(team.id)] = team
    return list(selectable_teams.values())


async def create_team(
    user: KeycloakUser,
    request: CreateTeamRequest,
    deps: TeamServiceDependencies,
) -> TeamWithPermissions:
    """Bootstrap a brand-new team with its first `team_admin`(s) (RFC §28).

    Why this function exists:
    - there was previously no team-creation flow at all: a "team" is a
      Keycloak root group, discovered lazily, and every membership endpoint
      requires the group (and a `team_admin`) to already exist — a freshly
      created Keycloak group was unreachable by any of them
    - `platform_admin` must not gain a standing team relation from creating a
      team (RFC §24.2/§24.7); this action writes explicit `team_admin` tuples
      only for the subjects named in the request

    How to use it:
    - call from the platform-admin-gated `POST /teams` route
    - one-shot by construction: `team_metadata.name`'s DB-level unique
      constraint (migration a8b9c0d1e2f3) makes a second call for the same
      name fail with `TeamAlreadyExistsError` (409) rather than silently
      reassigning an existing team's admins

    Example:
    - `team = await create_team(user, CreateTeamRequest(name="swiftpost", initial_team_admin_ids=["alice-sub"]), deps)`
    """
    rebac = deps.rebac
    await rebac.check_user_permission_or_raise(
        user, OrganizationPermission.CAN_CREATE_TEAM, ORGANIZATION_ID
    )

    store = deps.get_team_metadata_store()
    # AUTHZ-05 post-implementation review finding: this pre-check is a
    # fast-path only (fails fast on the common case without a wasted insert
    # attempt) — it does NOT by itself close the race between two concurrent
    # `POST /teams` calls for the same name, since both could pass it before
    # either writes. The actual guarantee is `team_metadata.name`'s DB-level
    # unique constraint below.
    if await store.get_by_name(request.name) is not None:
        raise TeamAlreadyExistsError(request.name)

    team_id = TeamId(uuid4().hex)
    try:
        metadata = await store.create(team_id, request.name)
    except IntegrityError as exc:
        raise TeamAlreadyExistsError(request.name) from exc

    try:
        await rebac.add_relations(
            [
                Relation(
                    subject=RebacReference(Resource.USER, admin_user_id),
                    relation=RelationType.TEAM_ADMIN,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
                for admin_user_id in request.initial_team_admin_ids
            ]
        )
    except Exception:
        logger.warning(
            "Rolling back team %s (%s): failed to bootstrap initial team_admin(s)",
            team_id,
            request.name,
        )
        await store.delete(team_id)
        raise

    logger.info(
        "Bootstrapped team %s (%s) with initial team_admin(s): %s",
        team_id,
        request.name,
        ", ".join(request.initial_team_admin_ids),
    )

    # Build the response directly rather than through the permission-gated
    # `get_team_by_id` path: the calling platform_admin is not necessarily a
    # team_member of the team they just created (by design, RFC §24.2/§24.7),
    # so a CAN_READ-gated lookup would deny their own creation response.
    consistency_token = await rebac.ensure_team_organization_relations([team_id])
    teams = await _enrich_teams_with_membership(rebac, user, [metadata], deps)
    permissions = await _get_team_permissions_for_user(
        rebac, user, team_id, consistency_token
    )
    retention = await _resolve_team_retention_view(team_id, deps)
    return TeamWithPermissions(
        **teams[0].model_dump(), permissions=permissions, retention=retention
    )


async def get_team_by_id(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
    required_permissions: list[TeamPermission] | None = None,
) -> TeamWithPermissions:
    """Resolve one selectable team, including reserved system teams.

    `required_permissions` (default `[CAN_READ]`) is the ReBAC permission the caller
    must hold on a COLLABORATIVE team. Mutating callers (agent-instance enroll/patch/
    delete) pass `[CAN_UPDATE_AGENTS]` so a plain `team_member` is refused while
    `team_editor`/`team_admin` pass. Reserved system teams (personal) short-circuit
    below and are intentionally not gated — a user owns their personal space
    (RUNTIME-07 finding).

    Why this function exists:
    - product-facing team routes should expose `personal` through the same team
      contract as collaborative teams

    How to use it:
    - call from `/teams/{team_id}` and bootstrap flows that need one
      `TeamWithPermissions`

    Example:
    - `team = await get_team_by_id(user, TeamId("personal"), deps)`
    """
    personal_limit = deps.configuration.app.personal_max_resources_storage_size
    system_team = await get_system_team(user, team_id, personal_limit)
    if system_team is not None:
        return system_team

    rebac = deps.rebac

    metadata, consistency_token = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        required_permissions or [TeamPermission.CAN_READ],
        deps,
    )

    teams = await _enrich_teams_with_membership(
        rebac,
        user,
        [metadata],
        deps,
    )
    if not teams:
        raise TeamNotFoundError(team_id)

    permissions = await _get_team_permissions_for_user(
        rebac,
        user,
        team_id,
        consistency_token,
    )
    retention = await _resolve_team_retention_view(team_id, deps)
    return TeamWithPermissions(
        **teams[0].model_dump(), permissions=permissions, retention=retention
    )


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

    metadata, consistency_token = await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [TeamPermission.CAN_UPDATE_INFO],
        deps,
    )

    # PATCH with no fields is a no-op.
    if request.model_fields_set:
        patch_data = request.model_dump(exclude_unset=True)
        # CTRLP-12 (RFC §3.B): retention rides the same team PATCH. Validate the
        # cap server-side and stamp the audit column only when a retention field
        # is actually touched.
        if {"team_delete_grace", "max_idle"} & request.model_fields_set:
            await _reject_retention_overflow(team_id, request, deps)
            patch_data["retention_updated_by"] = user.uid
        patch = TeamMetadataPatch.model_validate(patch_data)
        updated = await deps.get_team_metadata_store().upsert(team_id, patch)
        if updated is not None:
            metadata = updated

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

    teams = await _enrich_teams_with_membership(
        rebac,
        user,
        [metadata],
        deps,
    )
    if not teams:
        raise TeamNotFoundError(team_id)

    permissions = await _get_team_permissions_for_user(
        rebac,
        user,
        team_id,
        consistency_token,
    )
    retention = await _resolve_team_retention_view(team_id, deps)
    return TeamWithPermissions(
        **teams[0].model_dump(), permissions=permissions, retention=retention
    )


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
    - the frontend and CLI need one rendered member list resolved entirely
      from persisted ReBAC role relations (AUTHZ-05 review item 9 — no
      Keycloak group involved)

    How to use it:
    - call from `/teams/{team_id}/members`
    - pass request-scoped dependencies when available
    - for a platform-admin-privileged caller that must read every real team's
      members regardless of personal membership, use
      `list_team_members_unfiltered` instead (same list-vs-unfiltered split as
      `list_teams`/`list_all_teams_unfiltered`)

    Example:
    - `members = await list_team_members(user, TeamId("fredlab"), deps)`
    """
    return await _list_team_members(user, team_id, deps, check_permission=True)


async def list_team_members_unfiltered(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
) -> list[TeamMember]:
    """Same as `list_team_members` but without the per-team `CAN_READ_MEMEBERS` check —
    callers MUST already have verified `OrganizationPermission.CAN_MANAGE_PLATFORM`
    (e.g. `compute_platform_stats`). `platform_admin` carries no standing team
    relation (RFC "zero implicit access"), so the normal per-team check 403s on
    every real team the admin isn't personally a member of."""
    return await _list_team_members(user, team_id, deps, check_permission=False)


async def _list_team_members(
    user: KeycloakUser,
    team_id: TeamId,
    deps: TeamServiceDependencies,
    *,
    check_permission: bool,
) -> list[TeamMember]:
    rebac = deps.rebac

    if check_permission:
        await _validate_team_and_check_permission(
            user,
            team_id,
            rebac,
            [TeamPermission.CAN_READ_MEMEBERS],
            deps,
        )
    else:
        metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
        if metadata is None:
            raise TeamNotFoundError(team_id)

    admin_ids, editor_ids, analyst_ids, member_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_ADMIN),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_EDITOR),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_ANALYST),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_MEMBER),
    )
    user_summaries = await deps.get_users_by_ids(member_ids)

    team_members: list[TeamMember] = []
    for member_id in member_ids:
        user_summary = user_summaries.get(member_id) or UserSummary(id=member_id)
        # AUTHZ-06 (RFC Part 7 §37): the full set of roles this member holds,
        # not a single "primary" one — a member may hold several at once.
        relations = [
            relation
            for relation, ids in (
                (UserTeamRelation.TEAM_ADMIN, admin_ids),
                (UserTeamRelation.TEAM_EDITOR, editor_ids),
                (UserTeamRelation.TEAM_ANALYST, analyst_ids),
            )
            if member_id in ids
        ]
        if not relations:
            relations = [UserTeamRelation.TEAM_MEMBER]
        team_members.append(TeamMember(user=user_summary, relations=relations))

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
    - team administration needs one business path that writes the requested
      team role as a persisted ReBAC relation (no Keycloak group involved)

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
    - membership removal must revoke every persisted ReBAC role relation the
      user holds on the team (no Keycloak group involved) and trigger the
      configured session-retention policy for the removed user

    How to use it:
    - call from the team-membership DELETE route
    - pass request-scoped dependencies when available

    Example:
    - `result = await remove_team_member(user, TeamId("swiftpost"), "user-1", deps)`
    """
    rebac = deps.rebac

    # AUTHZ-06 (RFC Part 7 §35): a member may hold several roles at once — a
    # full removal must be checked against every one of them, not just a
    # single "primary" role, and the last-admin guard applies whenever
    # team_admin is among them.
    target_roles = await _get_user_roles_in_team(rebac, team_id, user_id)
    if UserTeamRelation.TEAM_ADMIN in target_roles:
        await _ensure_team_keeps_at_least_one_admin(
            rebac=rebac,
            team_id=team_id,
            user_id=user_id,
            revoked_role=UserTeamRelation.TEAM_ADMIN,
        )
    permissions_to_check = [
        _get_administer_permission_for_team_role_relation(role)
        for role in (target_roles or {UserTeamRelation.TEAM_MEMBER})
    ]

    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        permissions_to_check,
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


async def grant_team_member_role(
    user: KeycloakUser,
    team_id: TeamId,
    user_id: str,
    request: GrantTeamMemberRoleRequest,
    deps: TeamServiceDependencies,
) -> None:
    """
    Grant one additional team role to an existing member (AUTHZ-06, RFC Part 7 §34).

    Why this function exists:
    - a member may hold more than one team role simultaneously (e.g. a small
      team's sole team_admin who is also its team_editor and team_analyst) —
      granting is always one explicit, independently permission-checked role
      at a time, never a bulk role-set replace, so every change stays
      individually auditable

    How to use it:
    - call from the team-membership role-grant route
    - pass request-scoped dependencies when available

    Example:
    - `await grant_team_member_role(user, TeamId("fredlab"), "user-1", request, deps)`
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
    await _add_team_member_relation(rebac, team_id, user_id, request.relation)

    logger.info(
        "Granted role %s to user %s on team %s",
        request.relation.value,
        user_id,
        team_id,
    )


async def revoke_team_member_role(
    user: KeycloakUser,
    team_id: TeamId,
    user_id: str,
    relation: UserTeamRelation,
    deps: TeamServiceDependencies,
) -> None:
    """
    Revoke one team role from an existing member, leaving any other roles they
    hold untouched (AUTHZ-06, RFC Part 7 §34-35).

    Why this function exists:
    - the inverse of `grant_team_member_role`; revoking a member's only
      remaining role is refused (`TeamMemberLastRoleError`) — that is a
      removal, not a role change, and must go through `remove_team_member` so
      the two stay distinct, explicit, auditable actions

    How to use it:
    - call from the team-membership role-revoke route
    - pass request-scoped dependencies when available

    Example:
    - `await revoke_team_member_role(user, TeamId("fredlab"), "user-1", UserTeamRelation.TEAM_EDITOR, deps)`
    """
    rebac = deps.rebac

    current_roles = await _get_user_roles_in_team(rebac, team_id, user_id)
    if relation not in current_roles:
        raise TeamMemberRoleNotHeldError(team_id, user_id, relation)
    if current_roles == {relation}:
        raise TeamMemberLastRoleError(team_id, user_id, relation)

    if relation == UserTeamRelation.TEAM_ADMIN:
        await _ensure_team_keeps_at_least_one_admin(
            rebac=rebac,
            team_id=team_id,
            user_id=user_id,
            revoked_role=relation,
        )
    permission_to_check = _get_administer_permission_for_team_role_relation(relation)
    await _validate_team_and_check_permission(
        user,
        team_id,
        rebac,
        [permission_to_check],
        deps,
    )
    await _remove_team_member_relation(rebac, team_id, user_id, relation)

    logger.info(
        "Revoked role %s from user %s on team %s",
        relation.value,
        user_id,
        team_id,
    )


async def _enrich_teams_with_membership(
    rebac: RebacEngine,
    user: KeycloakUser,
    teams_metadata: list[TeamMetadata],
    deps: TeamServiceDependencies,
) -> list[Team]:
    """Resolve one rendered `Team` per metadata row, decorated with admins/membership.

    AUTHZ-05 review item 9: membership no longer comes from a Keycloak group —
    `team_member` already covers `team_admin`/`team_editor`/`team_analyst`
    through the schema's union relation (RFC §31), so one ReBAC lookup replaces
    the old Keycloak group-member fetch.
    """
    if not teams_metadata:
        return []

    content_store = deps.get_content_store()
    team_ids: list[TeamId] = [metadata.id for metadata in teams_metadata]
    admin_ids_list, member_ids_list = await asyncio.gather(
        asyncio.gather(
            *[
                _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_ADMIN)
                for team_id in team_ids
            ]
        ),
        asyncio.gather(
            *[
                _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_MEMBER)
                for team_id in team_ids
            ]
        ),
    )

    team_admin_ids_map = {
        team_id: admin_ids for team_id, admin_ids in zip(team_ids, admin_ids_list)
    }
    team_member_ids_map = {
        team_id: member_ids for team_id, member_ids in zip(team_ids, member_ids_list)
    }
    all_admin_ids: set[str] = set().union(*admin_ids_list) if admin_ids_list else set()
    user_summaries = await deps.get_users_by_ids(all_admin_ids)

    teams: list[Team] = []
    for metadata in teams_metadata:
        member_ids = team_member_ids_map.get(metadata.id, set())
        banner_image_url: str | None = None
        if metadata.banner_object_storage_key:
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
                        metadata.id,
                        exc,
                    )

        admins = _dedupe_user_summaries_by_display_key(
            [
                user_summaries.get(admin_id) or UserSummary(id=admin_id)
                for admin_id in team_admin_ids_map.get(metadata.id, set())
            ]
        )
        max_storage = (
            metadata.max_resources_storage_size
            if metadata.max_resources_storage_size is not None
            else deps.configuration.app.default_team_max_resources_storage_size
        )
        teams.append(
            Team(
                id=metadata.id,
                name=metadata.name,
                member_count=len(member_ids),
                admins=admins,
                is_member=user.uid in member_ids,
                description=metadata.description,
                is_private=metadata.is_private,
                banner_image_url=banner_image_url,
                max_resources_storage_size=max_storage,
                current_resources_storage_size=metadata.current_resources_storage_size,
            )
        )

    return teams


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
    - `admins = _dedupe_user_summaries_by_display_key(admins)`
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

    checks = await asyncio.gather(
        *[
            rebac.has_permission(
                RebacReference(Resource.USER, user.uid),
                permission,
                RebacReference(Resource.TEAM, team_id),
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
) -> tuple[TeamMetadata, str | None]:
    """
    Load one team's metadata and verify the caller has the requested permissions.

    Why this function exists:
    - team write and read operations all need the same validation path for
      team-existence checks plus ReBAC permission enforcement

    How to use it:
    - pass the current user, target team id, required permissions, and the
      explicit team-service dependency bundle
    - expect `TeamNotFoundError` on an unknown team id

    Example:
    - `metadata, token = await _validate_team_and_check_permission(user, team_id, rebac, permissions, deps)`
    """
    metadata = await deps.get_team_metadata_store().get_by_team_id(team_id)
    if metadata is None:
        raise TeamNotFoundError(team_id)

    permissions_are_read_only = (
        set(permissions) <= SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS
    )
    if is_service_agent(user) and permissions_are_read_only:
        # Solution A (RFC EVAL-AUTH): recognize the evaluation worker's service
        # identity for team read, scoped to the request team_id, without any stored
        # OpenFGA relation. Write permissions are NOT in the allowed set, so mutating
        # routes fall through to the normal ReBAC check below and are denied.
        logger.info("service_agent authorized (read, scoped) for team %s", team_id)
        return metadata, None

    consistency_token = await rebac.check_user_team_permissions_or_raise(
        user=user,
        team_id=team_id,
        permissions=permissions,
    )

    return metadata, consistency_token


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
    if target == UserTeamRelation.TEAM_EDITOR:
        return TeamPermission.CAN_ADMINISTER_EDITORS
    if target == UserTeamRelation.TEAM_ANALYST:
        return TeamPermission.CAN_ADMINISTER_ANALYSTS
    if target == UserTeamRelation.TEAM_ADMIN:
        return TeamPermission.CAN_ADMINISTER_ADMINS
    return TeamPermission.CAN_ADMINISTER_MEMBERS


async def _get_user_roles_in_team(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
) -> set[UserTeamRelation]:
    """AUTHZ-06 (RFC Part 7 §35): the full set of roles `user_id` currently
    holds on `team_id` — a member may hold several simultaneously (e.g.
    `team_admin` and `team_editor` at once). Falls back to `{TEAM_MEMBER}`
    when none of the three elevated roles apply but the user is still a
    team member through the base relation."""
    admin_ids, editor_ids, analyst_ids, member_ids = await asyncio.gather(
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_ADMIN),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_EDITOR),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_ANALYST),
        _get_team_users_by_relation(rebac, team_id, RelationType.TEAM_MEMBER),
    )
    roles = {
        relation
        for relation, ids in (
            (UserTeamRelation.TEAM_ADMIN, admin_ids),
            (UserTeamRelation.TEAM_EDITOR, editor_ids),
            (UserTeamRelation.TEAM_ANALYST, analyst_ids),
        )
        if user_id in ids
    }
    if not roles and user_id in member_ids:
        roles.add(UserTeamRelation.TEAM_MEMBER)
    return roles


async def _remove_team_member_relation(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
    relation: UserTeamRelation,
) -> None:
    """AUTHZ-06 (RFC Part 7 §35): revoke exactly one role, mirroring
    `_add_team_member_relation` — leaves any other role the member holds
    untouched. Unlike `_remove_all_team_member_relations`, this is not a full
    member removal."""
    await rebac.delete_relations(
        [
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=relation.to_relation(),
                resource=RebacReference(Resource.TEAM, team_id),
            )
        ]
    )


async def _remove_all_team_member_relations(
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
) -> None:
    await rebac.delete_relations(
        [
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.TEAM_ADMIN,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.TEAM_EDITOR,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.TEAM_ANALYST,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
            Relation(
                subject=RebacReference(Resource.USER, user_id),
                relation=RelationType.TEAM_MEMBER,
                resource=RebacReference(Resource.TEAM, team_id),
            ),
        ]
    )


async def _ensure_team_keeps_at_least_one_admin(
    *,
    rebac: RebacEngine,
    team_id: TeamId,
    user_id: str,
    revoked_role: UserTeamRelation,
) -> None:
    """AUTHZ-06 (RFC Part 7 §35): checked whenever `revoked_role` is being
    taken away from `user_id`, whether by a full member removal or a single
    -role revoke. A team must never end up with zero `team_admin` — callers
    only need to invoke this when `revoked_role` is `TEAM_ADMIN`."""
    if revoked_role != UserTeamRelation.TEAM_ADMIN:
        return

    admin_ids = await _get_team_users_by_relation(
        rebac, team_id, RelationType.TEAM_ADMIN
    )
    if user_id in admin_ids and len(admin_ids) <= 1:
        raise TeamAdminConstraintError(
            "Operation denied: a team must keep at least one team_admin."
        )
