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
             `PLATFORM-IMPORT-RFC.md` §6, reconciliation fix AUTHZ-07 Step 2)
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
             Fail-closed by design (AUTHZ-07 Step 2): ReBAC disabled (the
             engine is `NoopRebacEngine`, so no relation write would persist
             anything), an unknown team-role or platform-role name, a
             username still unresolved after the identity phase, or a team
             that cannot be created or resolved, each raise
             `BundleProvisioningError` and abort the users phase — a
             declared-valid bundle never ends in a silently incomplete
             `succeeded` task.
- MCP servers      → SKIP (re-seeded by deployment on swift)
- Resources → kea `chat-context` resources become swift prompt-library rows in
             the author's personal space (`personal-{author}`), front-matter
             stripped; other kea resource kinds (`prompt`, `template`) are
             skipped with a warning (kea path only)
- OpenFGA tuples → restored with role transformation (MIGR-05.04, kea path
             only): kea team roles map to the swift model
             (owner → team_admin + team_editor, manager → team_editor,
             member → team_member — mapping approved 2026-07-24), the kea
             shared personal team (`team:personal`) is dropped (swift
             self-heals per-user `personal-{uid}` spaces), `resource#parent`
             tuples are dropped (resources become prompt rows, which have no
             OpenFGA object), and agent/tag/document/organization tuples
             replay 1:1. Assumes UUID-keyed subjects (MIGR-04 preserves subs);
             non-UUID user subjects are dropped and counted.

Pre-conditions handled outside this module (MIGR-04 / MIGR-06):
- Keycloak users already present with the same UUIDs
- MinIO binaries and embeddings already mirrored
"""

from __future__ import annotations

import logging
import re
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
from fred_core.documents.document_structures import ProcessingStage, ProcessingStatus
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
from sqlalchemy import select
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
from control_plane_backend.models.prompt_models import PromptRow
from control_plane_backend.product.dependencies import ProductServiceDependencies
from control_plane_backend.product.service import (
    grant_existing_teams_served_templates,
    materialize_default_capability_selections,
)
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

# Canonical contract — swift-native baseline (PLATFORM-IMPORT-RFC.md):
# vectors/SQL indexes are never transported by this import (products are
# rebuilt on the target, MIGR-07), so a restored document must not carry
# forward the source's stale DONE claim for them. PREVIEW_READY is left
# alone — the data-before-metadata ordering (MIGR-06 before MIGR-05) is a
# documented precondition, so preview content is trusted to already be there.
_STAGES_RESET_ON_IMPORT = (
    ProcessingStage.VECTORIZED.value,
    ProcessingStage.SQL_INDEXED.value,
)


def _reset_transported_stages(doc: dict[str, Any] | None) -> dict[str, Any] | None:
    """Reset VECTORIZED/SQL_INDEXED to NOT_STARTED on a restored metadata `doc`
    blob so the platform never reports a document as searchable when its
    embeddings/index were never restored."""
    if not doc:
        return doc
    stages = (doc.get("processing") or {}).get("stages")
    if isinstance(stages, dict):
        for stage in _STAGES_RESET_ON_IMPORT:
            if stage in stages:
                stages[stage] = ProcessingStatus.NOT_STARTED.value
    return doc


class BundleProvisioningError(Exception):
    """A `users.json` bundle cannot be fully reconciled (AUTHZ-07 Step 2).

    Why this type exists:
    - `PLATFORM-IMPORT-RFC.md` §6's fail-closed rule: a declared-valid
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
    # Kea-path counters (MIGR-05.04 / chat-context prompts). Internal-only for
    # now: surfaced through the summary line and `warnings`, deliberately NOT
    # projected onto `MigrationResult` (fred_core.tasks.models) — extending
    # that public contract means an OpenAPI + generated-client regeneration,
    # tracked as a follow-up rather than smuggled into this change.
    prompts_imported: int = 0
    prompts_skipped: int = 0
    tuples_written: int = 0
    tuples_dropped: int = 0
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


def _build_agent_creator_index(tuples: list[dict[str, Any]]) -> dict[str, str]:
    """Return agent_id → creating user's uid, from user-owner tuples.

    Only personal agents carry a `user:UID owner agent:AID` tuple; team-owned
    agents have a team subject and keep `created_by=None` (kea does not record
    which member created them).
    """
    index: dict[str, str] = {}
    for t in tuples:
        obj: str = t.get("object", "")
        user: str = t.get("user", "")
        if t.get("relation") != "owner" or not obj.startswith("agent:"):
            continue
        if user.startswith("user:"):
            index[obj.removeprefix("agent:")] = user.removeprefix("user:")
    return index


# Kea system-prompt tuning keys, in precedence order: v2 agents declare
# `system_prompt_template`; v1 agents declare dotted `prompts.system`.
_KEA_SYSTEM_PROMPT_KEYS = ("system_prompt_template", "prompts.system")


def _extract_kea_prompts(tuning_src: dict[str, Any]) -> tuple[str | None, list[str]]:
    """Return (system prompt text, other customized kea prompt field keys).

    The kea per-agent prompt lives in `payload_json.tuning.fields[].default`.
    Only the system prompt has a swift landing field (`tuning.values
    ["prompts.system"]`); v1 secondary per-node prompts
    (`prompts.generate_answer`, `prompts.self_check`, …) do not — they are
    returned separately so the caller can warn instead of dropping silently.
    """
    system: str | None = None
    secondary: list[str] = []
    for spec in tuning_src.get("fields") or []:
        if not isinstance(spec, dict):
            continue
        key = spec.get("key")
        default = spec.get("default")
        if not (isinstance(default, str) and default.strip()):
            continue
        if key in _KEA_SYSTEM_PROMPT_KEYS:
            if system is None:
                system = default
        elif spec.get("type") == "prompt":
            secondary.append(str(key))
    return system, secondary


# Kea library tags carry prompt/template/chat-context libraries. Their content
# migrates into the swift prompt library (personal spaces), so importing the
# library tags themselves would only create orphaned folders.
_KEA_LIBRARY_TAG_TYPES = frozenset({"chat-context", "prompt", "template"})


def _strip_front_matter(content: str) -> str:
    """Return the body of a kea resource `content` blob.

    Kea stores the raw authored string: a YAML header (`version:`, `kind:`,
    `name:`, …), a `---` separator line, then the actual prompt body. Swift's
    prompt `text` is sent to the model as-is, so only the body is migrated —
    `name`/`description`/`labels` already travel as structured fields.
    """
    _, sep, body = content.partition("\n---\n")
    return body.strip() if sep else content.strip()


# ── Kea → swift OpenFGA tuple transformation (MIGR-05.04) ─────────────────────

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)

# Kea team roles are hierarchical (owner ⊃ manager ⊃ member); swift team_admin
# and team_editor are orthogonal (REBAC.md "hard cross-write rule"), so a kea
# owner must receive BOTH to keep the content authority it had. Mapping
# approved by the developer on 2026-07-24. `team_analyst` has no kea source
# and is never synthesized.
_KEA_TEAM_ROLE_TO_SWIFT: dict[str, tuple[RelationType, ...]] = {
    "owner": (RelationType.TEAM_ADMIN, RelationType.TEAM_EDITOR),
    "manager": (RelationType.TEAM_EDITOR,),
    "member": (RelationType.TEAM_MEMBER,),
}

# The kea shared personal-space team id (`PERSONAL_TEAM_ID` on main). Swift
# personal spaces are per-user (`personal-{uid}`) and their access tuple is
# self-healed on first use, so kea personal-team tuples must be dropped, not
# translated.
_KEA_SHARED_PERSONAL_TEAM_ID = "personal"

_RESOURCE_BY_PREFIX: dict[str, Resource] = {
    "user": Resource.USER,
    "team": Resource.TEAM,
    "organization": Resource.ORGANIZATION,
    "agent": Resource.AGENT,
    "tag": Resource.TAGS,
    "document": Resource.DOCUMENTS,
}


@dataclass
class KeaTupleTransform:
    """Outcome of transforming a kea tuple dump into swift relations."""

    relations: list[Relation] = field(default_factory=list)
    dropped_personal: int = 0
    dropped_non_uuid: int = 0
    dropped_resource_parent: int = 0
    dropped_unknown: int = 0
    unknown_shapes: set[str] = field(default_factory=set)

    @property
    def dropped_total(self) -> int:
        return (
            self.dropped_personal
            + self.dropped_non_uuid
            + self.dropped_resource_parent
            + self.dropped_unknown
        )


def transform_kea_tuples(tuples: list[dict[str, Any]]) -> KeaTupleTransform:
    """Map a kea OpenFGA tuple dump onto the swift authorization model.

    - team `owner`/`manager`/`member` tuples are aggregated per (user, team)
      and re-emitted as swift `team_*` relations; a user with an elevated role
      never also gets a redundant direct `team_member` tuple (schema.fga
      derives it).
    - `agent`/`tag`/`document` ownership and `team#organization`/`team#public`
      tuples replay 1:1 (identical relation names on both models).
    - dropped: anything touching the kea shared personal team, `resource#parent`
      (resources migrate to prompt rows, which have no OpenFGA object),
      non-UUID user subjects (pre-MIGR-04 username tuples), and any shape the
      swift model does not know.
    """
    out = KeaTupleTransform()
    team_roles: dict[tuple[str, str], set[str]] = {}
    seen: set[tuple[str, str, str, str, str]] = set()

    def _emit(
        subject: RebacReference, relation: RelationType, resource: RebacReference
    ) -> None:
        key = (
            subject.type.value,
            str(subject.id),
            relation.value,
            resource.type.value,
            str(resource.id),
        )
        if key in seen:
            return
        seen.add(key)
        out.relations.append(
            Relation(subject=subject, relation=relation, resource=resource)
        )

    def _split(ref: str) -> tuple[str, str]:
        prefix, _, ident = ref.partition(":")
        return prefix, ident

    for t in tuples:
        subj_type, subj_id = _split(t.get("user", ""))
        rel = t.get("relation", "")
        obj_type, obj_id = _split(t.get("object", ""))

        touches_shared_personal = (
            obj_type == "team" and obj_id == _KEA_SHARED_PERSONAL_TEAM_ID
        ) or (subj_type == "team" and subj_id == _KEA_SHARED_PERSONAL_TEAM_ID)
        if touches_shared_personal:
            out.dropped_personal += 1
            continue
        if obj_type == "resource":
            out.dropped_resource_parent += 1
            continue
        if subj_type == "user" and subj_id != "*" and not _UUID_RE.match(subj_id):
            out.dropped_non_uuid += 1
            continue

        if (
            obj_type == "team"
            and subj_type == "user"
            and rel in _KEA_TEAM_ROLE_TO_SWIFT
        ):
            team_roles.setdefault((subj_id, obj_id), set()).add(rel)
            continue

        replayable = (
            (obj_type == "agent" and rel == "owner" and subj_type in ("user", "team"))
            or (
                obj_type == "tag"
                and rel in ("owner", "editor", "viewer")
                and subj_type in ("user", "team")
            )
            or (obj_type == "tag" and rel == "parent" and subj_type == "tag")
            or (obj_type == "document" and rel == "parent" and subj_type == "tag")
            or (
                obj_type == "team"
                and rel == "organization"
                and subj_type == "organization"
            )
            or (obj_type == "team" and rel == "public" and subj_type == "user")
        )
        subject_res = _RESOURCE_BY_PREFIX.get(subj_type)
        object_res = _RESOURCE_BY_PREFIX.get(obj_type)
        if not replayable or subject_res is None or object_res is None:
            out.dropped_unknown += 1
            out.unknown_shapes.add(f"{subj_type} {rel} {obj_type}")
            continue
        _emit(
            RebacReference(subject_res, subj_id),
            RelationType(rel),
            RebacReference(object_res, obj_id),
        )

    for (uid, team_id), kea_roles in sorted(team_roles.items()):
        targets: set[RelationType] = set()
        for role in kea_roles & {"owner", "manager"}:
            targets.update(_KEA_TEAM_ROLE_TO_SWIFT[role])
        if not targets and "member" in kea_roles:
            targets.add(RelationType.TEAM_MEMBER)
        for relation in sorted(targets, key=lambda r: r.value):
            _emit(
                RebacReference(Resource.USER, uid),
                relation,
                RebacReference(Resource.TEAM, team_id),
            )

    return out


_STEP_LABELS: dict[str, str] = {
    "classify": "Classifying agents",
    "agents": "Importing agents",
    "resources": "Importing prompts",
    "tags": "Importing tags",
    "metadata": "Importing documents",
    "team_metadata": "Importing team settings",
    "users": "Provisioning users",
    "tuples": "Restoring permissions",
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
    rebac: RebacEngine,
    user_sub: str,
    relation: RelationType,
    *,
    actor_uid: str | None = None,
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
        ),
        actor_uid=actor_uid,
    )


async def _grant_team_role_via_import(
    rebac: RebacEngine,
    user_sub: str,
    relation: UserTeamRelation,
    team_id: TeamId,
    *,
    actor_uid: str | None = None,
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
        ),
        actor_uid=actor_uid,
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
    requests (AUTHZ-07 Step 2 / `PLATFORM-IMPORT-RFC.md` §6 `teams`/
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
    platform_admin: KeycloakUser,
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
                await _grant_team_role_via_import(
                    rebac, sub, relation, team_id, actor_uid=platform_admin.uid
                )
                report.team_roles_granted += 1

        for role in entry.platform_roles:
            relation = _PLATFORM_ROLE_RELATIONS[role]  # validated upfront
            await _grant_platform_role(
                rebac, sub, relation, actor_uid=platform_admin.uid
            )
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

    Guard 0 — ReBAC must be enabled. With it disabled, `team_deps.rebac` is
    `NoopRebacEngine`: every `add_relation` call below is a silent no-op, so
    `_apply_bundle_user_roles` would still increment `team_roles_granted`/
    `platform_roles_granted` and let the import report `succeeded` with no
    authorization tuple actually written — the same class of gap Step 2 (the
    `BundleProvisioningError` fail-closed rule, above) exists to close.
    Checked before role-name validation, identity creation, username
    resolution, team creation, or any counter increment, so a bundle with
    `users.json` fails before any side effect when ReBAC is off.
    """
    if not team_deps.rebac.enabled:
        raise BundleProvisioningError(
            "users.json declares declarative provisioning but ReBAC is "
            "disabled: no authorization tuple can be written "
            "(team_deps.rebac is the no-op engine), so the users phase "
            "refuses to run rather than report a false success. Enable "
            "ReBAC before importing a bundle that contains users.json."
        )
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
        platform_admin=platform_admin,
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
    product_deps: ProductServiceDependencies | None = None,
    rebac: RebacEngine | None = None,
) -> MigrationReport:
    # The tuple-restore phase (kea path, MIGR-05.04) needs a ReBAC engine even
    # when the bundle has no users.json; fall back to team_deps' engine so
    # existing call sites keep working.
    if rebac is None and team_deps is not None:
        rebac = team_deps.rebac
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
    agent_creator_index = _build_agent_creator_index(tuples)

    # ── Phase 1: classify agents (no DB writes) — kea snapshots only ──────────
    raw_agents = [] if is_swift_native else list(bundle.iter_table("agent"))
    await _emit(
        task_service, task_id, TaskState.running, "classify", 0, len(raw_agents), 0
    )

    to_create_agents: list[AgentInstanceRecord] = []

    for row in raw_agents:
        agent_id: str = row["id"]
        payload: dict[str, Any] = row.get("payload_json") or {}
        if payload.get("type") == "leader":
            # Legacy kea leader rows — kea's own store ignores them on load.
            report.agents_skipped += 1
            continue
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

        # MIGR-05.11 — carry the kea agent's real tuning, not a placeholder.
        tuning_src: dict[str, Any] = payload.get("tuning") or {}
        role = str(tuning_src.get("role") or "").strip() or display_name
        description = str(tuning_src.get("description") or "").strip() or display_name
        tag_list = [t for t in (tuning_src.get("tags") or []) if isinstance(t, str)]
        system_prompt, secondary_prompt_keys = _extract_kea_prompts(tuning_src)
        values: dict[str, Any] = {}
        if system_prompt:
            # `prompts.system` is the tuning key every fred-agents ReAct
            # template declares; the runtime overlays it onto the template's
            # system_prompt_template (fred_runtime/app/agent_app.py). This is
            # what keeps the kea agent's customized behaviour. Deliberately
            # not mirrored into a prompt-library row: `prompt_refs_json` has
            # no consumer today, and kea never had these prompts in a library.
            values["prompts.system"] = system_prompt
        if secondary_prompt_keys:
            report.warnings.append(
                f"agent {agent_id}: kea prompt field(s) "
                f"{', '.join(sorted(secondary_prompt_keys))} have no swift "
                "equivalent — only the system prompt was migrated"
            )
        tuning = ManagedAgentTuning(
            role=role, description=description, tags=tag_list, values=values
        )

        to_create_agents.append(
            AgentInstanceRecord(
                agent_instance_id=agent_id,
                team_id=TeamId(team_id_str),
                template_id=template_id,
                source_runtime_id=runtime_part,
                source_agent_id=agent_part,
                display_name=display_name,
                description=description[:500],
                enabled=bool(payload.get("enabled", True)),
                created_by=agent_creator_index.get(agent_id),
                tuning=tuning,
            )
        )

    # Table file names differ per producer: kea bundles carry main's literal
    # Postgres table names (`migration/snapshot.py::EXPORT_TABLES` on the main
    # branch — the team table is `teammetadata`, one word); swift-native
    # bundles carry `exporter.py`'s names (`team_metadata`).
    team_table = "team_metadata" if is_swift_native else "teammetadata"
    raw_tags = list(bundle.iter_table("tag"))
    if not is_swift_native:
        # Kea library tags (prompt/template/chat-context folders) are not
        # migrated: their content lands in the swift prompt library (personal
        # spaces), so importing them would only create orphaned folders.
        library_tags = [t for t in raw_tags if t.get("type") in _KEA_LIBRARY_TAG_TYPES]
        if library_tags:
            report.warnings.append(
                f"{len(library_tags)} kea library tag(s) "
                "(prompt/template/chat-context) not migrated — their contents "
                "move to personal prompt spaces"
            )
            raw_tags = [
                t for t in raw_tags if t.get("type") not in _KEA_LIBRARY_TAG_TYPES
            ]
    # Kea chat-context resources become personal prompt-library rows; swift
    # bundles never carry a resource table.
    raw_resources = [] if is_swift_native else list(bundle.iter_table("resource"))
    raw_metadata = list(bundle.iter_table("metadata"))
    # Per-team branding + retention (CTRLP-12). Kea's `teammetadata` rows carry
    # `is_private` instead of `joining_mode` and may lack `name` — both handled
    # by `_import_team_metadata`'s fallbacks below.
    raw_team_metadata = list(bundle.iter_table(team_table))

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

            # --- kea chat-context resources → personal prompt rows ---
            async def _import_resource(row: dict[str, Any], s: AsyncSession) -> bool:
                resource_id = row["resource_id"]
                kind = row.get("resource_type")
                doc: dict[str, Any] = row.get("doc") or {}
                if kind != "chat-context":
                    report.warnings.append(
                        f"resource {resource_id}: kea kind '{kind}' has no "
                        "swift equivalent — skipped"
                    )
                    return False
                author = row.get("author") or doc.get("author")
                if not author:
                    report.warnings.append(
                        f"resource {resource_id}: no author — cannot place in "
                        "a personal space, skipped"
                    )
                    return False
                if await s.get(PromptRow, resource_id) is not None:
                    return False
                text = _strip_front_matter(str(doc.get("content") or ""))
                if not text:
                    report.warnings.append(
                        f"resource {resource_id}: empty content — skipped"
                    )
                    return False
                # Chat contexts migrate into the author's personal space only
                # (decision 2026-07-24); kea library sharing is dropped.
                team_id = f"personal-{author}"
                name = str(
                    row.get("resource_name")
                    or doc.get("name")
                    or f"Imported context {resource_id[:8]}"
                )[:255]
                collision = await s.execute(
                    select(PromptRow.prompt_id).where(
                        PromptRow.team_id == team_id, PromptRow.name == name
                    )
                )
                if collision.first() is not None:
                    name = f"{name[:240]} ({resource_id[:8]})"
                description = doc.get("description")
                prompt_row = PromptRow(
                    prompt_id=resource_id,
                    team_id=team_id,
                    name=name,
                    description=str(description)[:500] if description else None,
                    category="other",
                    tags=[t for t in (doc.get("labels") or []) if isinstance(t, str)],
                    text=text,
                    created_by=str(author),
                    version=1,
                )
                created_at = _coerce_dt(row.get("created_at"))
                updated_at = _coerce_dt(row.get("updated_at"))
                if created_at is not None:
                    prompt_row.created_at = created_at
                if updated_at is not None:
                    prompt_row.updated_at = updated_at
                s.add(prompt_row)
                return True

            report.prompts_imported, report.prompts_skipped = await _run_phase(
                task_service=task_service,
                task_id=task_id,
                step_id="resources",
                items=raw_resources,
                import_fn=_import_resource,
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
                        doc=_reset_transported_stages(row.get("doc")),
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
            if bundle.manifest.content_keys:
                # Canonical contract — track, don't embed: this import never
                # carries document binaries, only declares what it assumes is
                # already mirrored (MIGR-06). Not verified here (no
                # cross-backend content-store probe) — surfaced so the
                # operator can check, same as any other partial-reconciliation
                # warning (RFC §11's "with warnings" tell).
                report.warnings.append(
                    f"{len(bundle.manifest.content_keys)} document(s) expect content "
                    "already present in the target's object store (mirrored via "
                    "MIGR-06) — not verified by this import"
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
                        # TEAM-09: pre-migration bundles only ever carry
                        # `is_private`, never `joining_mode` — like the `name`
                        # fallback above, default to the same value every
                        # existing team was migrated to (REQUEST_ONLY)
                        # regardless of the legacy bool, rather than deriving
                        # one from it (see FRED-TEAM-CONFIG-RFC.md §5.1.1).
                        joining_mode=row.get("joining_mode", "request_only"),
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

    # ── Phase 4bis: OpenFGA tuple restore, kea path only (MIGR-05.04) ─────────
    # Outside the DB transaction: OpenFGA is a separate store with its own
    # idempotence (`add_relation` ignores duplicates), so a partial tuple
    # replay is safely re-runnable. Replaces the former "ops bulk-copy" plan,
    # which would have pushed kea relation names (`owner`/`manager`/`member`
    # on team objects) that no longer exist in the swift model.
    if not is_swift_native and tuples:
        transform = transform_kea_tuples(tuples)
        report.tuples_dropped = transform.dropped_total
        if transform.dropped_non_uuid:
            report.warnings.append(
                f"{transform.dropped_non_uuid} OpenFGA tuple(s) with a "
                "non-UUID user subject dropped (pre-MIGR-04 username tuples)"
            )
        if transform.dropped_unknown:
            report.warnings.append(
                f"{transform.dropped_unknown} OpenFGA tuple(s) dropped — no "
                "swift equivalent for: " + ", ".join(sorted(transform.unknown_shapes))
            )
        if not transform.relations:
            pass
        elif rebac is None or not rebac.enabled:
            report.warnings.append(
                f"{len(transform.relations)} OpenFGA relation(s) NOT restored: "
                "ReBAC engine unavailable or disabled — re-run the import "
                "with ReBAC enabled before cutover"
            )
        else:
            total = len(transform.relations)
            await _emit(task_service, task_id, TaskState.running, "tuples", 0, total, 0)
            actor_uid = platform_admin.uid if platform_admin else None
            for i, relation in enumerate(transform.relations, start=1):
                await rebac.add_relation(relation, actor_uid=actor_uid)
                report.tuples_written += 1
                await _emit(
                    task_service, task_id, TaskState.running, "tuples", i, total, 0
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

    # ── Phase 6: capability compatibility sweeps (GitHub #2004 item 3) ────────
    # Imported agent rows are written directly (kea rows via a bare
    # `ManagedAgentTuning(...)`, swift-native rows via the bundle's raw
    # `tuning_json`), never through `enroll_agent_instance` /
    # `_apply_capability_selection`. Both paths can persist
    # `selected_capability_ids=None` — the exact sentinel #1980 already closed
    # for the live enroll/update path, which the runtime still trusts as
    # "activate every template default" with no ReBAC check. Re-running the
    # same two sweeps used at CAPAB-01/CTRLP-14 deploy time, scoped to just the
    # teams this import touched, closes the gap for every import instead of
    # relying on an operator to remember a manual follow-up.
    imported_team_ids: set[TeamId] = {record.team_id for record in to_create_agents} | {
        TeamId(row["team_id"]) for row in raw_native_agents
    }
    if product_deps is not None and imported_team_ids:
        grant_summary = await grant_existing_teams_served_templates(
            product_deps, team_ids=imported_team_ids
        )
        materialize_summary = await materialize_default_capability_selections(
            product_deps, team_ids=imported_team_ids
        )
        logger.info(
            "[import-export] import %s capability sweeps: granted=%d "
            "materialized=%d (teams=%d)",
            import_id,
            grant_summary.grants_written,
            materialize_summary.materialized,
            len(imported_team_ids),
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
                    f"{report.prompts_imported} prompts"
                    if report.prompts_imported
                    else None,
                    f"{report.tags_imported} tags" if report.tags_imported else None,
                    f"{report.docs_imported} docs" if report.docs_imported else None,
                    f"{report.tuples_written} permissions restored"
                    if report.tuples_written
                    else None,
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
