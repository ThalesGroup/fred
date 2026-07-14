"""Kea→Swift import service (MIGR-05).

Reads a KBundle and writes the migrated data into the swift control-plane DB.
Emits MigrationTaskEvent progress events so the frontend SSE stream stays live.

All three write phases (agents, tags, metadata) share a single SQLAlchemy
transaction opened against the same AsyncEngine.  Any failure rolls back
everything atomically — no partial state is left behind.

Scope (current snapshot):
- Agents   → agent_instance rows (MAPPED only; IGNORED silently skipped; GAP warned)
- Tags     → tag rows (preserving tag_id, owner_id, doc JSON)
- Metadata → metadata rows (preserving document_uid and doc JSON;
             content/vectors already in S3+OpenSearch via MIGR-06)
- Team metadata → team_metadata rows (branding + per-team retention, CTRLP-12;
             swift-native snapshots only, idempotent skip-if-present)
- Users    → two-phase declarative provisioning (AUTHZ-07 Part 8 §40.2,
             `PLATFORM-IMPORT-RFC.md` §10, reconciliation fix AUTHZ-07 Step 2)
             from the top-level `users.json` bundle entry, run outside the DB
             transaction above (after it, so role grants may reference teams
             the same bundle just created).
             Phase 1 (identity) creates a Keycloak user for any bundle entry
             that has no existing identity AND carries a `password` — an
             entry with no `password` is assumed to already exist and is
             never force-created. Phase 2 (role) resolves username → sub and
             grants every team/platform role the bundle declares. A
             brand-new team's *initial* `team_admin`(s) is always seeded at
             creation (`teams.service.create_team`'s own bootstrap
             capability). Every other team-scoped grant — `team_editor`,
             `team_analyst`, `team_member`, or any role on a team that
             already existed before this import — is written by a private,
             import-only reconciliation primitive (`_grant_team_role_via_import`)
             that calls `RebacEngine.add_relation` directly, the same way
             `_grant_platform_role` already does for org-level roles. It
             deliberately does NOT go through the ordinary, `team_admin`-gated
             `teams.service.grant_team_member_role` — that would require the
             importing `platform_admin` to already hold `team_admin` on every
             team the bundle touches, which defeats the point of a
             declarative bundle. Team-scoped roles are still never *derived*
             from a platform role (schema.fga's `type team` comment is
             unchanged, and the ordinary team-membership APIs are untouched
             and still team-admin-bounded) — this is a narrow, private write
             path reachable only from this already `CAN_MANAGE_PLATFORM`-gated
             import flow, not a new capability exposed anywhere else.
             Fail-closed by design (AUTHZ-07 Step 2): an unknown team-role or
             platform-role name, a username still unresolved after the
             identity phase, or a team that cannot be created or resolved,
             each raise `BundleProvisioningError` and abort the users phase —
             a declared-valid bundle never ends in a silently incomplete
             `succeeded` task.
- MCP servers      → SKIP (re-seeded by deployment on swift)
- Resources/prompts → SKIP (0 rows in current exports)

Pre-conditions handled outside this module (MIGR-04 / MIGR-06):
- Keycloak users already present with the same UUIDs
- OpenFGA tuples already restored (Option A — ops bulk-copy)
- MinIO binaries and embeddings already mirrored
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, TypeVar

from fred_core import (
    ORGANIZATION_ID,
    KeycloakUser,
    RebacEngine,
    RebacReference,
    Relation,
    RelationType,
    Resource,
)
from fred_core.common import TeamId
from fred_core.documents.document_models import DocumentMetadataRow
from fred_core.documents.tag_models import TagRow
from fred_core.sql.async_session import make_session_factory
from fred_core.tasks.models import (
    MigrationDetail,
    MigrationResult,
    MigrationTaskEvent,
    TaskState,
)
from fred_core.tasks.service import TaskService
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.import_export.agent_map import (
    AgentMapOutcome,
    classify_agent,
)
from control_plane_backend.import_export.bundle import KBundle
from control_plane_backend.import_export.schemas import BundleUserEntry
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.teams.dependencies import TeamServiceDependencies
from control_plane_backend.teams.schemas import (
    CreateTeamRequest,
    TeamAlreadyExistsError,
    UserTeamRelation,
)
from control_plane_backend.teams.service import create_team
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.schemas import CreateUserRequest
from control_plane_backend.users.service import create_user, find_user_sub_by_username

logger = logging.getLogger(__name__)

T = TypeVar("T")

# AUTHZ-07 Part 8 §40.2: bundle `platform_roles` values → org-level relations.
# Kept private and narrow on purpose — see `_grant_platform_role` below.
_PLATFORM_ROLE_RELATIONS: dict[str, RelationType] = {
    "admin": RelationType.PLATFORM_ADMIN,
    "observer": RelationType.PLATFORM_OBSERVER,
}


class BundleProvisioningError(Exception):
    """A `users.json` bundle cannot be fully reconciled (AUTHZ-07 Step 2).

    Why this type exists:
    - `PLATFORM-IMPORT-RFC.md` §10's fail-closed rule: a declared-valid
      bundle must never produce a silently incomplete `succeeded` import.
      Every one of the conditions below now aborts the whole users phase
      (and thus the import — `import_export/api.py`'s background-task
      wrapper turns any exception raised here into `task_service.fail_task`)
      instead of being downgraded to a warning: an unknown team-role or
      platform-role name, a username still unresolved after the identity
      phase, or a team referenced by the bundle that cannot be created or
      resolved.

    How to use it:
    - raise it with a message naming every offending entry/team/role so the
      operator can fix the bundle in one pass, not one failed re-run at a
      time.
    """


@dataclass
class MigrationReport:
    import_id: str
    source_platform: str
    agents_imported: int = 0
    agents_skipped: int = 0
    agents_gap: int = 0
    tags_imported: int = 0
    tags_skipped: int = 0
    docs_imported: int = 0
    docs_skipped: int = 0
    teams_imported: int = 0
    teams_skipped: int = 0
    # users.json phase (AUTHZ-07 Part 8 §40.2) — deliberately distinct names
    # from teams_imported/teams_skipped above (the team_metadata Postgres-row
    # phase): teams_provisioned counts *new* teams created via
    # `teams.service.create_team` from bundle team_roles/teams data.
    # identities_created counts Keycloak users created by the identity phase
    # (`_provision_bundle_identities`) — distinct from users_processed, which
    # counts entries resolved and role-granted by the (pre-existing) role phase.
    identities_created: int = 0
    users_processed: int = 0
    # AUTHZ-07 Step 2: an unresolved username / unreconcilable team-role grant
    # is now fail-closed (`BundleProvisioningError`, users-phase aborts)
    # rather than skipped-and-reported, so `users_skipped`/`team_roles_skipped`
    # only ever reach 0 on a report that made it back to the caller — they
    # stay on the dataclass for API stability and for any future step (e.g.
    # AUTHZ-07 Step 3's UI surfacing) that wants a structured "why it failed"
    # rather than parsing the exception message.
    users_skipped: list[str] = field(default_factory=list)
    teams_provisioned: int = 0
    team_roles_granted: int = 0
    team_roles_skipped: int = 0
    platform_roles_granted: int = 0
    warnings: list[str] = field(default_factory=list)


def to_migration_result(report: MigrationReport) -> MigrationResult:
    """Project the internal `MigrationReport` onto the public `MigrationResult`
    contract (AUTHZ-07 Step 3) — a field-for-field mapping, never a re-derivation:
    `MigrationReport` stays the single place that computes these counters.
    """
    return MigrationResult(
        import_id=report.import_id,
        source_platform=report.source_platform,
        identities_created=report.identities_created,
        users_processed=report.users_processed,
        users_skipped=list(report.users_skipped),
        teams_imported=report.teams_imported,
        teams_skipped=report.teams_skipped,
        teams_provisioned=report.teams_provisioned,
        team_roles_granted=report.team_roles_granted,
        team_roles_skipped=report.team_roles_skipped,
        platform_roles_granted=report.platform_roles_granted,
        agents_imported=report.agents_imported,
        agents_skipped=report.agents_skipped,
        agents_gap=report.agents_gap,
        tags_imported=report.tags_imported,
        tags_skipped=report.tags_skipped,
        docs_imported=report.docs_imported,
        docs_skipped=report.docs_skipped,
        warnings=list(report.warnings),
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_dt(value: Any) -> datetime | None:
    """Accept an ISO-8601 string, a datetime, or None — return a datetime/None.

    Swift-native snapshots serialize timestamps as ISO strings; kea snapshots may
    already carry datetimes or None. This normalises both for ORM TIMESTAMP columns.
    """
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def _build_agent_team_index(tuples: list[dict[str, Any]]) -> dict[str, str]:
    """Return agent_id → team_id from OpenFGA owner tuples.

    user:UID  owner agent:AID  →  personal-{UID}
    team:TID  owner agent:AID  →  {TID}
    """
    index: dict[str, str] = {}
    for t in tuples:
        obj: str = t.get("object", "")
        user: str = t.get("user", "")
        if t.get("relation") != "owner" or not obj.startswith("agent:"):
            continue
        agent_id = obj.removeprefix("agent:")
        if user.startswith("team:"):
            index[agent_id] = user.removeprefix("team:")
        elif user.startswith("user:"):
            index[agent_id] = f"personal-{user.removeprefix('user:')}"
    return index


_STEP_LABELS: dict[str, str] = {
    "classify": "Classifying agents",
    "agents": "Importing agents",
    "tags": "Importing tags",
    "metadata": "Importing documents",
    "team_metadata": "Importing team settings",
    "users": "Provisioning users",
}


async def _emit(
    task_service: TaskService,
    task_id: str,
    state: TaskState,
    step_id: str,
    processed: int,
    total: int,
    failed: int,
    step_override: str | None = None,
) -> None:
    label = step_override or _STEP_LABELS.get(step_id, step_id)
    step_str = f"{label} ({processed}/{total})" if total > 0 else label
    progress = processed / total if total > 0 else None
    await task_service.record(
        MigrationTaskEvent(
            task_id=task_id,
            state=state,
            seq=0,
            timestamp=_utcnow(),
            step=step_str,
            progress=progress,
            detail=MigrationDetail(
                step_id=step_id,
                processed=processed,
                total=total,
                failed=failed,
            ),
        )
    )


async def _run_phase(
    *,
    task_service: TaskService,
    task_id: str,
    step_id: str,
    items: list[T],
    import_fn: Callable[[T, AsyncSession], Awaitable[bool]],
    session: AsyncSession,
) -> tuple[int, int]:
    """Generic import loop — emits SSE progress, returns (imported, skipped).

    import_fn(item, session) must return True if the item was written,
    False if it was skipped (already present or intentionally excluded).
    Any exception propagates and the caller's transaction rolls back.
    """
    total = len(items)
    await _emit(task_service, task_id, TaskState.running, step_id, 0, total, 0)
    imported = skipped = 0
    for item in items:
        written = await import_fn(item, session)
        if written:
            imported += 1
        else:
            skipped += 1
        await _emit(
            task_service,
            task_id,
            TaskState.running,
            step_id,
            imported + skipped,
            total,
            0,
        )
    return imported, skipped


async def _grant_platform_role(
    rebac: RebacEngine, user_sub: str, relation: RelationType
) -> None:
    """Grant one org-level platform role to a third party (AUTHZ-07 Part 8 §40.2).

    Deliberately NOT a public service function or a new endpoint — this is the
    one genuinely new capability this phase adds (granting `platform_admin`/
    `platform_observer` to a named third party), so its surface is kept to this
    one private call site, reachable only through the already
    `CAN_MANAGE_PLATFORM`-gated `POST /import-export/import` route. Mirrors
    `bootstrap/service.py::bootstrap_platform_admin`'s own direct `add_relation`
    call. `add_relation` is idempotent (`on_duplicate_writes=IGNORE`), so
    re-running the same bundle never errors on an already-granted role.
    """
    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, user_sub),
            relation=relation,
            resource=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
        )
    )


async def _grant_team_role_via_import(
    rebac: RebacEngine,
    user_sub: str,
    relation: UserTeamRelation,
    team_id: TeamId,
) -> None:
    """Grant one team-scoped role directly (AUTHZ-07 Step 2 — the fix).

    This is the private reconciliation primitive that closes AUTHZ-07 Step
    2's finding: the ordinary, `team_admin`-gated
    `teams.service.grant_team_member_role` cannot be the write path for
    bundle-declared team roles, because the importing `platform_admin`
    deliberately holds no standing team relation (RFC Part 8 §24.2/§24.7 —
    "zero implicit access"). Routing through it meant every non-admin
    team-scoped grant in a bundle was refused and silently downgraded to a
    warning, which is exactly the bug this function fixes.

    Deliberately NOT a public service function, a new endpoint, or a
    schema.fga change granting `platform_admin` team-scoped rights — the
    permission boundary on the *ordinary* team APIs is completely unchanged
    (`grant_team_member_role`/`add_team_member`/etc. still require
    `team_admin`, see `teams/service.py`). This function instead mirrors
    `_grant_platform_role` above and `teams/service.py::_add_team_member_relation`
    (whose one-line body it duplicates on purpose rather than importing a
    private helper across modules): it calls `RebacEngine.add_relation`
    directly, with no permission check of any kind, so it must stay private
    and reachable only from this already `CAN_MANAGE_PLATFORM`-gated import
    flow (`POST /import-export/import`) — never exposed as a second public
    team-membership service. `add_relation` is idempotent
    (`on_duplicate_writes=IGNORE`), so re-running the same bundle against an
    already-provisioned team/role never errors and never duplicates a tuple.
    """
    await rebac.add_relation(
        Relation(
            subject=RebacReference(Resource.USER, user_sub),
            relation=relation.to_relation(),
            resource=RebacReference(Resource.TEAM, team_id),
        )
    )


async def _provision_bundle_identities(
    bundle_users: list[BundleUserEntry],
    user_deps: UserServiceDependencies,
    platform_admin: KeycloakUser,
    report: MigrationReport,
) -> None:
    """Create a Keycloak identity for each bundle entry that needs one.

    Runs before username resolution so the role phase below can then resolve
    every entry, including the ones just created here. An entry is only
    created when it has no existing Keycloak identity (`find_user_sub_by_username`
    → `None`) AND carries a `password` — an entry with no `password` is assumed
    to already exist and is never force-created. Uses the write-gated
    `users/service.py::create_user` (already Keycloak-Admin-M2M-gated); if M2M
    credentials are not configured, `create_user` raises
    `KeycloakM2MUserOperationDisabledError`, which is left to propagate rather
    than swallowed — this makes Keycloak Admin M2M configuration an explicit
    precondition of importing a bundle that creates identities.
    """
    for entry in bundle_users:
        if await find_user_sub_by_username(entry.username, user_deps) is not None:
            continue  # already exists — identity phase never overwrites
        if entry.password is None:
            continue  # no password supplied — cannot create, role phase will report it missing
        await create_user(
            platform_admin,
            CreateUserRequest(
                username=entry.username,
                email=entry.email or f"{entry.username}@example.com",
                password=entry.password,
                first_name=entry.first_name,
                last_name=entry.last_name,
            ),
            user_deps,
        )
        report.identities_created += 1


def _validate_bundle_role_names(bundle_users: list[BundleUserEntry]) -> None:
    """Fail closed on any unknown role name before any bundle write happens
    (AUTHZ-07 Step 2).

    Pure validation, no I/O: runs before identity creation so a bundle with a
    typo'd role name never creates a single Keycloak user or writes a single
    relation before being rejected. An unknown `team_roles` key or
    `platform_roles` value is a bundle-authoring error, not a per-entry
    warning — see `BundleProvisioningError`.
    """
    problems: list[str] = []
    for entry in bundle_users:
        for relation_value in entry.team_roles:
            try:
                UserTeamRelation(relation_value)
            except ValueError:
                problems.append(
                    f"user {entry.username}: unknown team role '{relation_value}'"
                )
        for role in entry.platform_roles:
            if role not in _PLATFORM_ROLE_RELATIONS:
                problems.append(
                    f"user {entry.username}: unknown platform role '{role}'"
                )
    if problems:
        raise BundleProvisioningError(
            "users.json failed validation: " + "; ".join(problems)
        )


async def _resolve_bundle_usernames(
    bundle_users: list[BundleUserEntry],
    user_deps: UserServiceDependencies,
) -> dict[str, str]:
    """Resolve each unique `username` in the bundle to a Keycloak `sub` once.

    Read-only (`find_user_sub_by_username` never creates a user). AUTHZ-07
    Step 2: a username still unresolved after the identity phase is now a
    fail-closed condition — raises `BundleProvisioningError` naming every
    unresolved username, aborting the users phase, instead of being skipped
    and reported while the rest of the import continues to a `succeeded`
    state.
    """
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    attempted: set[str] = set()
    for entry in bundle_users:
        username = entry.username
        if username in attempted:
            continue
        attempted.add(username)
        sub = await find_user_sub_by_username(username, user_deps)
        if sub is None:
            unresolved.append(username)
            continue
        resolved[username] = sub
    if unresolved:
        raise BundleProvisioningError(
            "users.json cannot be fully reconciled: no matching Keycloak "
            f"identity for {', '.join(unresolved)} after the identity phase "
            "(the identity phase only creates a user when the bundle entry "
            "carries a password; without one, this importer never creates "
            "identities, only Fred-side authorization state)."
        )
    return resolved


def _collect_team_admin_seeds(
    bundle_users: list[BundleUserEntry],
    resolved: dict[str, str],
) -> tuple[set[str], dict[str, list[str]]]:
    """Return (every team name referenced, team name → subs to seed as team_admin).

    A brand-new team's initial `team_admin`(s) can only be set at creation time
    (`create_team`'s own one-shot bootstrap capability — schema.fga's `type
    team` comment: team-scoped relations are never derived from a platform
    role). This collects, for each team not yet known to exist, which resolved
    users declared `team_admin` for it anywhere in the bundle, so `create_team`
    can seed all of them in the same call.
    """
    referenced_team_names: set[str] = set()
    team_admin_seed_subs: dict[str, list[str]] = {}
    for entry in bundle_users:
        # `resolved` is guaranteed to carry every bundle username by the time
        # this runs — `_resolve_bundle_usernames` raises otherwise (AUTHZ-07
        # Step 2, fail-closed).
        sub = resolved[entry.username]
        for team_name in entry.teams:
            referenced_team_names.add(team_name)
        for relation, team_names in entry.team_roles.items():
            for team_name in team_names:
                referenced_team_names.add(team_name)
                if relation == UserTeamRelation.TEAM_ADMIN.value:
                    seeds = team_admin_seed_subs.setdefault(team_name, [])
                    if sub not in seeds:
                        seeds.append(sub)
    return referenced_team_names, team_admin_seed_subs


def _effective_team_relations(
    entry: BundleUserEntry,
) -> dict[str, set[UserTeamRelation]]:
    """Resolve the exact set of direct team-role tuples one bundle entry
    requests (AUTHZ-07 Step 2 / `PLATFORM-IMPORT-RFC.md` §10 `teams`/
    `team_roles` semantics).

    - A team name in `entry.team_roles` requests exactly the named
      relation(s) on that team — multiple roles for the same team are
      cumulative (e.g. priya: `team_admin` + `team_editor` + `team_analyst`
      on `fredlab`, all three persisted).
    - A team name in `entry.teams` that never appears as a key's value in
      `entry.team_roles` for this same entry requests a single direct
      `team_member` tuple — the only fallback. `schema.fga` already derives
      `team_member` from `team_admin`/`team_editor`/`team_analyst` (a union
      relation), so a team with an explicit role must never also get a
      redundant direct `team_member` tuple.
    """
    relations_by_team: dict[str, set[UserTeamRelation]] = {}
    for relation_value, team_names in entry.team_roles.items():
        relation = UserTeamRelation(relation_value)  # validated upfront
        for team_name in team_names:
            relations_by_team.setdefault(team_name, set()).add(relation)
    for team_name in entry.teams:
        # `setdefault` only inserts the team_member fallback when this team
        # has no explicit role for this entry yet.
        relations_by_team.setdefault(team_name, {UserTeamRelation.TEAM_MEMBER})
    return relations_by_team


async def _provision_bundle_teams(
    *,
    referenced_team_names: set[str],
    team_admin_seed_subs: dict[str, list[str]],
    platform_admin: KeycloakUser,
    team_deps: TeamServiceDependencies,
    report: MigrationReport,
) -> dict[str, TeamId]:
    """Ensure every referenced team exists, creating brand-new ones.

    A new team can only be created here if the bundle declares at least one
    `team_admin` for it (`CreateTeamRequest.initial_team_admin_ids` requires
    `min_length=1` — an adminless team cannot be created). AUTHZ-07 Step 2:
    a team referenced only via `teams`/a non-admin role, with no
    `team_admin` declared anywhere in the bundle for it, is now a
    fail-closed condition — checked in a first pass over every team that
    doesn't already exist, before any team is actually created, so a bundle
    that can only partially provision its teams raises
    `BundleProvisioningError` (naming every offending team) rather than
    silently creating some teams and skipping others.
    """
    team_ids_by_name: dict[str, TeamId] = {}
    metadata_store = team_deps.get_team_metadata_store()
    to_create: list[str] = []
    for team_name in sorted(referenced_team_names):
        existing = await metadata_store.get_by_name(team_name)
        if existing is not None:
            team_ids_by_name[team_name] = existing.id
        else:
            to_create.append(team_name)

    unprovisionable = [
        team_name for team_name in to_create if not team_admin_seed_subs.get(team_name)
    ]
    if unprovisionable:
        raise BundleProvisioningError(
            "users.json cannot be fully reconciled: team(s) "
            f"{', '.join(unprovisionable)} are referenced but do not exist "
            "yet and no team_admin is declared for them anywhere in the "
            "bundle (create_team requires at least one initial team_admin — "
            "declare one for each of these teams, or drop the reference)."
        )

    for team_name in to_create:
        admin_subs = team_admin_seed_subs[team_name]
        try:
            created = await create_team(
                platform_admin,
                CreateTeamRequest(name=team_name, initial_team_admin_ids=admin_subs),
                team_deps,
            )
        except TeamAlreadyExistsError:
            # Concurrent creator between the pre-check above and this call.
            existing = await metadata_store.get_by_name(team_name)
            if existing is None:
                raise
            team_ids_by_name[team_name] = existing.id
            continue

        team_ids_by_name[team_name] = created.id
        report.teams_provisioned += 1

    return team_ids_by_name


async def _apply_bundle_user_roles(
    *,
    bundle_users: list[BundleUserEntry],
    resolved: dict[str, str],
    team_ids_by_name: dict[str, TeamId],
    team_deps: TeamServiceDependencies,
    task_service: TaskService,
    task_id: str,
    report: MigrationReport,
) -> None:
    """Grant each resolved user's declared team roles and platform roles.

    AUTHZ-07 Step 2 (the fix): every team-scoped grant is written through
    `_grant_team_role_via_import` — the private, import-only reconciliation
    primitive — not through the ordinary `team_admin`-gated
    `teams.service.grant_team_member_role`. The importing `platform_admin`
    is never required to already hold `team_admin` on the target team, so a
    declared-valid bundle's grants are never skipped for that reason
    anymore. Role names and team resolvability were already validated by
    the time this runs (`_validate_bundle_role_names`,
    `_resolve_bundle_usernames`, `_provision_bundle_teams` all raise
    `BundleProvisioningError` otherwise), so every write here is expected to
    succeed; `add_relation`'s idempotence (`on_duplicate_writes=IGNORE`)
    means a role already granted (including one seeded via
    `initial_team_admin_ids` at team-creation time) is safely re-written,
    not specially skipped.
    """
    rebac = team_deps.rebac
    total = len(bundle_users)
    await _emit(task_service, task_id, TaskState.running, "users", 0, total, 0)

    processed = 0
    for entry in bundle_users:
        sub = resolved[entry.username]
        report.users_processed += 1

        for team_name, relations in _effective_team_relations(entry).items():
            team_id = team_ids_by_name[team_name]
            for relation in relations:
                await _grant_team_role_via_import(rebac, sub, relation, team_id)
                report.team_roles_granted += 1

        for role in entry.platform_roles:
            relation = _PLATFORM_ROLE_RELATIONS[role]  # validated upfront
            await _grant_platform_role(rebac, sub, relation)
            report.platform_roles_granted += 1

        processed += 1
        await _emit(
            task_service, task_id, TaskState.running, "users", processed, total, 0
        )


async def _run_users_phase(
    *,
    bundle_users: list[BundleUserEntry],
    platform_admin: KeycloakUser,
    user_deps: UserServiceDependencies,
    team_deps: TeamServiceDependencies,
    task_service: TaskService,
    task_id: str,
    report: MigrationReport,
) -> None:
    """Apply the bundle's `users.json` declarative provisioning (AUTHZ-07 §40.2,
    reconciliation fix AUTHZ-07 Step 2).

    Runs after the atomic DB-transaction phases above (agents/tags/metadata/
    team_metadata) so team-role grants may reference teams the same bundle
    also creates in this run. Ordered sub-phases, each fail-closed
    (`BundleProvisioningError` on the first unrecoverable problem, aborting
    everything below it in this call):
    1. `_validate_bundle_role_names` — pure validation, no I/O.
    2. `_provision_bundle_identities` — creates missing Keycloak identities.
    3. `_resolve_bundle_usernames` — username → sub, raises on any miss.
    4. `_provision_bundle_teams` — creates missing teams, raises if any
       referenced team cannot be created or resolved.
    5. `_apply_bundle_user_roles` — writes every declared team/platform role
       via the private `_grant_team_role_via_import`/`_grant_platform_role`
       primitives, not the ordinary team-admin-gated APIs.
    Each step is individually idempotent (`create_user` is only called for a
    still-unresolved username, `create_team` fails closed on a name
    collision, `add_relation` is idempotent) — see the module docstring and
    each helper for the exact safety properties.
    """
    _validate_bundle_role_names(bundle_users)
    await _provision_bundle_identities(bundle_users, user_deps, platform_admin, report)
    resolved = await _resolve_bundle_usernames(bundle_users, user_deps)
    referenced_team_names, team_admin_seed_subs = _collect_team_admin_seeds(
        bundle_users, resolved
    )
    team_ids_by_name = await _provision_bundle_teams(
        referenced_team_names=referenced_team_names,
        team_admin_seed_subs=team_admin_seed_subs,
        platform_admin=platform_admin,
        team_deps=team_deps,
        report=report,
    )
    await _apply_bundle_user_roles(
        bundle_users=bundle_users,
        resolved=resolved,
        team_ids_by_name=team_ids_by_name,
        team_deps=team_deps,
        task_service=task_service,
        task_id=task_id,
        report=report,
    )


async def run_import(
    *,
    bundle: KBundle,
    import_id: str,
    task_id: str,
    task_service: TaskService,
    engine: AsyncEngine,
    agent_instance_store: AgentInstanceStore,
    platform_admin: KeycloakUser | None = None,
    user_deps: UserServiceDependencies | None = None,
    team_deps: TeamServiceDependencies | None = None,
) -> MigrationReport:
    source_platform = bundle.manifest.source_platform
    report = MigrationReport(
        import_id=import_id,
        source_platform=source_platform,
    )
    is_swift_native = source_platform == "swift"

    # Swift-native snapshots carry full agent_instance rows and team_id directly,
    # so they bypass the kea classification / agent_map translation entirely.
    raw_native_agents: list[dict[str, Any]] = (
        list(bundle.iter_table("agent_instance")) if is_swift_native else []
    )

    tuples = bundle.openfga_tuples()
    agent_team_index = _build_agent_team_index(tuples)

    # ── Phase 1: classify agents (no DB writes) — kea snapshots only ──────────
    raw_agents = [] if is_swift_native else list(bundle.iter_table("agent"))
    await _emit(
        task_service, task_id, TaskState.running, "classify", 0, len(raw_agents), 0
    )

    to_create_agents: list[AgentInstanceRecord] = []

    for row in raw_agents:
        agent_id: str = row["id"]
        payload: dict[str, Any] = row.get("payload_json") or {}
        result = classify_agent(payload)

        if result.outcome == AgentMapOutcome.IGNORED:
            report.agents_skipped += 1
            continue

        if result.outcome == AgentMapOutcome.GAP:
            kea_ref = result.kea_template or "<unknown>"
            report.agents_gap += 1
            report.warnings.append(
                f"agent {agent_id}: no swift template for '{kea_ref}' (GAP — "
                "add to KEA_TO_SWIFT_TEMPLATE in agent_map.py before cutover)"
            )
            continue

        team_id_str = agent_team_index.get(agent_id)
        if team_id_str is None:
            report.warnings.append(
                f"agent {agent_id}: no OpenFGA owner tuple found — skipped"
            )
            report.agents_skipped += 1
            continue

        template_id = result.swift_template_id or ""
        runtime_part, _, agent_part = template_id.partition(":")
        display_name: str = row.get("name") or payload.get("name") or agent_id
        tuning = ManagedAgentTuning(role=display_name, description=display_name)

        to_create_agents.append(
            AgentInstanceRecord(
                agent_instance_id=agent_id,
                team_id=TeamId(team_id_str),
                template_id=template_id,
                source_runtime_id=runtime_part,
                source_agent_id=agent_part,
                display_name=display_name,
                description=None,
                enabled=bool(payload.get("enabled", True)),
                created_by=None,
                tuning=tuning,
            )
        )

    raw_tags = list(bundle.iter_table("tag"))
    raw_metadata = list(bundle.iter_table("metadata"))
    # team_metadata carries per-team branding + retention (CTRLP-12); swift-native
    # snapshots only — kea snapshots omit the table and iter_table yields nothing.
    raw_team_metadata = list(bundle.iter_table("team_metadata"))

    # ── Phases 2–4: all writes in a single atomic transaction ─────────────────
    session_factory = make_session_factory(engine)
    async with session_factory() as session:
        async with session.begin():
            # --- agents (kea: mapped records / swift: native rows) ---
            async def _import_agent(
                record: AgentInstanceRecord, s: AsyncSession
            ) -> bool:
                if (
                    await agent_instance_store.get(record.agent_instance_id, session=s)
                    is not None
                ):
                    return False
                await agent_instance_store.create(record, session=s)
                return True

            async def _import_agent_native(
                row: dict[str, Any], s: AsyncSession
            ) -> bool:
                aid = row["agent_instance_id"]
                if await s.get(AgentInstanceRow, aid) is not None:
                    return False
                s.add(
                    AgentInstanceRow(
                        agent_instance_id=aid,
                        team_id=row["team_id"],
                        template_id=row["template_id"],
                        source_runtime_id=row["source_runtime_id"],
                        source_agent_id=row["source_agent_id"],
                        display_name=row["display_name"],
                        description=row.get("description"),
                        enabled=bool(row.get("enabled", True)),
                        created_by=row.get("created_by"),
                        tuning_json=row.get("tuning_json"),
                        prompt_refs_json=row.get("prompt_refs_json"),
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                    )
                )
                return True

            if is_swift_native:
                ai, as_ = await _run_phase(
                    task_service=task_service,
                    task_id=task_id,
                    step_id="agents",
                    items=raw_native_agents,
                    import_fn=_import_agent_native,
                    session=session,
                )
            else:
                ai, as_ = await _run_phase(
                    task_service=task_service,
                    task_id=task_id,
                    step_id="agents",
                    items=to_create_agents,
                    import_fn=_import_agent,
                    session=session,
                )
            report.agents_imported += ai
            report.agents_skipped += as_

            # --- tags ---
            async def _import_tag(row: dict[str, Any], s: AsyncSession) -> bool:
                tag_id = row["tag_id"]
                if await s.get(TagRow, tag_id) is not None:
                    return False
                s.add(
                    TagRow(
                        tag_id=tag_id,
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                        owner_id=row.get("owner_id"),
                        name=row.get("name"),
                        path=row.get("path"),
                        description=row.get("description"),
                        type=row.get("type"),
                        doc=row.get("doc"),
                    )
                )
                return True

            report.tags_imported, report.tags_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="tags",
                items=raw_tags,
                import_fn=_import_tag,
                session=session,
            )

            # --- document metadata ---
            async def _import_metadata(row: dict[str, Any], s: AsyncSession) -> bool:
                uid = row["document_uid"]
                if await s.get(DocumentMetadataRow, uid) is not None:
                    return False
                s.add(
                    DocumentMetadataRow(
                        document_uid=uid,
                        source_tag=row.get("source_tag"),
                        date_added_to_kb=_coerce_dt(row.get("date_added_to_kb")),
                        tag_ids=row.get("tag_ids") or [],
                        doc=row.get("doc"),
                    )
                )
                return True

            report.docs_imported, report.docs_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="metadata",
                items=raw_metadata,
                import_fn=_import_metadata,
                session=session,
            )

            # --- team metadata (branding + retention) ---
            async def _import_team_metadata(
                row: dict[str, Any], s: AsyncSession
            ) -> bool:
                team_id = row["id"]
                # Idempotent, consistent with other phases: skip if the team row
                # already exists so re-importing never clobbers live settings.
                if await s.get(TeamMetadataRow, team_id) is not None:
                    return False
                s.add(
                    TeamMetadataRow(
                        id=team_id,
                        # AUTHZ-05 review item 9: `name` was added after this
                        # bundle format existed. Fall back to the id so an
                        # older export (pre-item-9) still imports cleanly
                        # instead of violating the NOT NULL constraint.
                        name=row.get("name") or team_id,
                        description=row.get("description"),
                        is_private=bool(row.get("is_private", True)),
                        banner_object_storage_key=row.get("banner_object_storage_key"),
                        max_resources_storage_size=row.get(
                            "max_resources_storage_size"
                        ),
                        current_resources_storage_size=row.get(
                            "current_resources_storage_size"
                        )
                        or 0,
                        team_delete_grace=row.get("team_delete_grace"),
                        max_idle=row.get("max_idle"),
                        retention_updated_by=row.get("retention_updated_by"),
                        created_at=_coerce_dt(row.get("created_at")),
                        updated_at=_coerce_dt(row.get("updated_at")),
                    )
                )
                return True

            report.teams_imported, report.teams_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="team_metadata",
                items=raw_team_metadata,
                import_fn=_import_team_metadata,
                session=session,
            )

    # ── Phase 5: users.json declarative provisioning (AUTHZ-07 §40.2) ─────────
    # Outside the atomic transaction above: this phase calls full team/ReBAC
    # service functions (their own transactions/OpenFGA writes), not raw ORM
    # inserts on `session`. Runs last so team-role grants may reference teams
    # the team_metadata phase or this same phase just created.
    demo_users = bundle.demo_users()
    if demo_users:
        if platform_admin is None or user_deps is None or team_deps is None:
            raise ValueError(
                "bundle contains users.json but run_import was not given "
                "platform_admin/user_deps/team_deps"
            )
        await _run_users_phase(
            bundle_users=demo_users,
            platform_admin=platform_admin,
            user_deps=user_deps,
            team_deps=team_deps,
            task_service=task_service,
            task_id=task_id,
            report=report,
        )

    # ── Non-DB warnings ───────────────────────────────────────────────────────
    if report.warnings:
        logger.warning(
            "[import-export] import %s completed with %d warning(s):\n%s",
            import_id,
            len(report.warnings),
            "\n".join(f"  • {w}" for w in report.warnings),
        )

    summary = (
        ", ".join(
            filter(
                None,
                [
                    f"{report.agents_imported} agents imported"
                    if report.agents_imported
                    else None,
                    f"{report.agents_skipped} agents skipped"
                    if report.agents_skipped
                    else None,
                    f"{report.agents_gap} gaps" if report.agents_gap else None,
                    f"{report.tags_imported} tags" if report.tags_imported else None,
                    f"{report.docs_imported} docs" if report.docs_imported else None,
                    f"{report.teams_imported} teams" if report.teams_imported else None,
                    f"{report.identities_created} identities created"
                    if report.identities_created
                    else None,
                    f"{report.users_processed} users provisioned"
                    if report.users_processed
                    else None,
                    f"{len(report.users_skipped)} users skipped"
                    if report.users_skipped
                    else None,
                    f"{report.teams_provisioned} teams created"
                    if report.teams_provisioned
                    else None,
                    f"{report.team_roles_granted} team roles granted"
                    if report.team_roles_granted
                    else None,
                    f"{report.team_roles_skipped} team roles skipped"
                    if report.team_roles_skipped
                    else None,
                    f"{report.platform_roles_granted} platform roles granted"
                    if report.platform_roles_granted
                    else None,
                ],
            )
        )
        or "nothing imported"
    )

    await _emit(
        task_service,
        task_id,
        TaskState.running,
        "metadata",
        report.docs_imported,
        report.docs_imported,
        0,
        step_override=summary,
    )

    bundle.close()
    return report
