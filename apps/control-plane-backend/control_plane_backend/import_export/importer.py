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
             `PLATFORM-IMPORT-RFC.md` §10) from the top-level `users.json`
             bundle entry, run outside the DB transaction above (after it, so
             role grants may reference teams the same bundle just created).
             Phase 1 (identity) creates a Keycloak user for any bundle entry
             that has no existing identity AND carries a `password` — an
             entry with no `password` is assumed to already exist and is
             never force-created. Phase 2 (role) resolves username → sub and
             grants team/platform roles exactly as before; an unresolved
             username is skipped and reported, never created by phase 2.
             A brand-new team's *initial* `team_admin`(s) can always be seeded
             at creation (`teams.service.create_team`'s own bootstrap
             capability). Any other team-scoped grant (`team_editor`,
             `team_analyst`, a later `team_admin`, or any role at all on a
             team that already existed before this import) requires the
             importing `platform_admin` to already hold `team_admin` on that
             team — team-scoped roles are never derived from a platform role,
             by design (see `libs/fred-core/fred_core/security/rebac/schema.fga`
             `type team` comment). Such grants are skipped and reported, never
             silently dropped and never forced through a bypass.
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
    AuthorizationError,
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
from fred_core.tasks.models import MigrationDetail, MigrationTaskEvent, TaskState
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
    GrantTeamMemberRoleRequest,
    TeamAlreadyExistsError,
    UserTeamRelation,
)
from control_plane_backend.teams.service import create_team, grant_team_member_role
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
    users_skipped: list[str] = field(default_factory=list)
    teams_provisioned: int = 0
    team_roles_granted: int = 0
    team_roles_skipped: int = 0
    platform_roles_granted: int = 0
    warnings: list[str] = field(default_factory=list)


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


async def _resolve_bundle_usernames(
    bundle_users: list[BundleUserEntry],
    user_deps: UserServiceDependencies,
    report: MigrationReport,
) -> dict[str, str]:
    """Resolve each unique `username` in the bundle to a Keycloak `sub` once.

    Read-only (`find_user_sub_by_username` never creates a user). An
    unresolved username is recorded on `report.users_skipped` and in
    `report.warnings` — the rest of the import continues; one missing
    identity never fails the whole run.
    """
    resolved: dict[str, str] = {}
    attempted: set[str] = set()
    for entry in bundle_users:
        username = entry.username
        if not username:
            report.warnings.append("users.json entry missing 'username' — skipped")
            continue
        if username in attempted:
            continue
        attempted.add(username)
        sub = await find_user_sub_by_username(username, user_deps)
        if sub is None:
            report.users_skipped.append(username)
            report.warnings.append(
                f"user {username}: no matching Keycloak identity — skipped "
                "(the identity phase only creates a user when the bundle "
                "entry carries a password; without one, this importer never "
                "creates identities, only Fred-side authorization state)"
            )
            continue
        resolved[username] = sub
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
        username = entry.username
        sub = resolved.get(username) if username else None
        for team_name in entry.teams:
            referenced_team_names.add(team_name)
        for relation, team_names in entry.team_roles.items():
            for team_name in team_names:
                referenced_team_names.add(team_name)
                if sub is not None and relation == UserTeamRelation.TEAM_ADMIN.value:
                    seeds = team_admin_seed_subs.setdefault(team_name, [])
                    if sub not in seeds:
                        seeds.append(sub)
    return referenced_team_names, team_admin_seed_subs


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
    `min_length=1` — an adminless team cannot be created). A team referenced
    only via `teams`/a non-admin role, with no `team_admin` declared anywhere
    in the bundle, is skipped and reported rather than created adminless.
    """
    team_ids_by_name: dict[str, TeamId] = {}
    metadata_store = team_deps.get_team_metadata_store()
    for team_name in sorted(referenced_team_names):
        existing = await metadata_store.get_by_name(team_name)
        if existing is not None:
            team_ids_by_name[team_name] = existing.id
            continue

        admin_subs = team_admin_seed_subs.get(team_name, [])
        if not admin_subs:
            report.warnings.append(
                f"team {team_name}: not created — no team_admin declared for "
                "it in team_roles (create_team requires at least one initial "
                "team_admin; declare one for this team in the bundle)"
            )
            continue

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
    team_admin_seed_subs: dict[str, list[str]],
    platform_admin: KeycloakUser,
    team_deps: TeamServiceDependencies,
    task_service: TaskService,
    task_id: str,
    report: MigrationReport,
) -> None:
    """Grant each resolved user's declared team roles and platform roles.

    Team-scoped grants (`grant_team_member_role`) require the importing
    `platform_admin` to already hold `team_admin` on the target team — a
    role never derived from a platform role, by design (schema.fga's `type
    team` comment). This holds even for a `team_admin` grant repeated on a
    team this same run just created, UNLESS that exact sub was already seeded
    via `initial_team_admin_ids` at creation time — that case is counted as
    granted without a redundant call. Anything the platform_admin genuinely
    cannot grant (any role on a pre-existing team, or a non-admin role on a
    brand-new team) is skipped and reported, never silently dropped and never
    forced through a bypass of the team permission check.
    """
    rebac = team_deps.rebac
    total = len(bundle_users)
    await _emit(task_service, task_id, TaskState.running, "users", 0, total, 0)

    processed = 0
    for entry in bundle_users:
        username = entry.username
        sub = resolved.get(username) if username else None
        if sub is not None:
            report.users_processed += 1

            for relation_value, team_names in entry.team_roles.items():
                try:
                    relation = UserTeamRelation(relation_value)
                except ValueError:
                    report.warnings.append(
                        f"user {username}: unknown team role "
                        f"'{relation_value}' — skipped"
                    )
                    continue
                for team_name in team_names:
                    team_id = team_ids_by_name.get(team_name)
                    if team_id is None:
                        # Team wasn't provisioned — already warned in
                        # `_provision_bundle_teams`.
                        report.team_roles_skipped += 1
                        continue
                    if (
                        sub in team_admin_seed_subs.get(team_name, [])
                        and relation == UserTeamRelation.TEAM_ADMIN
                    ):
                        # Already granted via `initial_team_admin_ids` at
                        # team-creation time.
                        report.team_roles_granted += 1
                        continue
                    try:
                        await grant_team_member_role(
                            platform_admin,
                            team_id,
                            sub,
                            GrantTeamMemberRoleRequest(relation=relation),
                            team_deps,
                        )
                        report.team_roles_granted += 1
                    except AuthorizationError:
                        report.team_roles_skipped += 1
                        report.warnings.append(
                            f"user {username}: role '{relation_value}' on "
                            f"team {team_name} skipped — platform_admin has "
                            "no team_admin on that team (team-scoped roles "
                            "are never derived from a platform role, by "
                            "design; grant team_admin to an existing member "
                            "first, or declare a team_admin for this team in "
                            "the same bundle if it is being created now)"
                        )

            for role in entry.platform_roles:
                relation = _PLATFORM_ROLE_RELATIONS.get(role)
                if relation is None:
                    report.warnings.append(
                        f"user {username}: unknown platform role '{role}' — skipped"
                    )
                    continue
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
    """Apply the bundle's `users.json` declarative provisioning (AUTHZ-07 §40.2).

    Runs after the atomic DB-transaction phases above (agents/tags/metadata/
    team_metadata) so team-role grants may reference teams the same bundle
    also creates in this run. Two sub-phases, in order: identity creation
    (`_provision_bundle_identities`) then role provisioning (unchanged from
    this session's earlier work) — the latter can then resolve usernames the
    former just created. Each step is individually idempotent (`create_user`
    is only called for a still-unresolved username, `create_team` fails
    closed on a name collision, `add_relation` is idempotent) — see the
    module docstring and each helper for the exact safety properties.
    """
    await _provision_bundle_identities(bundle_users, user_deps, platform_admin, report)
    resolved = await _resolve_bundle_usernames(bundle_users, user_deps, report)
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
        team_admin_seed_subs=team_admin_seed_subs,
        platform_admin=platform_admin,
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
