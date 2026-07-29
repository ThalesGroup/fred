# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Iterable, Sequence

from fred_core.common.team_id import is_personal_team_id, personal_team_id
from fred_core.logs.audit_log import emit_audit_log
from fred_core.security.models import AuthorizationError, Resource
from fred_core.security.structure import KeycloakUser

ORGANIZATION_ID = "fred"
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RebacReference:
    """Point to one actor or object in authorization checks.

    Example:
    - `RebacReference(Resource.USER, "alice-id")`
    - `RebacReference(Resource.TEAM, "thales-team-id")`
    """

    type: Resource
    id: str


class RelationType(str, Enum):
    """Named links used to describe who can do what.

    Example:
    - `owner`: full control on a resource (agent/tag ownership — unrelated to
      team roles below).
    - `team_admin`: team governance authority.
    - `team_member`: can access team-scoped reads.
    """

    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"
    PARENT = "parent"
    ORGANIZATION = "organization"
    # Reverse index of team.organization (`organization:fred#team@team:<id>`).
    # Never persisted — injected as a contextual tuple for team-subject checks
    # (capability#can_use), since every team belongs to the singleton org.
    TEAM = "team"
    # Reverse index restricted to PERSONAL spaces
    # (`organization:fred#personal_team@team:<id>`). Never persisted — injected
    # as a contextual tuple only for `personal-{uid}` subjects so the
    # personal-space capability class (CAPAB-01 / #1961, RFC §8.4) applies to
    # every personal team and no regular team.
    PERSONAL_TEAM = "personal_team"

    # Capability team-scoping structural relations (CAPAB-01 / #1980,
    # RFC AGENT-CAPABILITY §8.1). Written only by the enablement API.
    DEFAULT_ON = "default_on"
    ENABLED = "enabled"
    DISABLED = "disabled"
    # Personal-space class position (CAPAB-01 / #1961, RFC §8.4). One
    # platform-wide org-subject tuple each; toggled by writing/deleting them.
    PERSONAL_ON = "personal_on"
    PERSONAL_DISABLED = "personal_disabled"
    PUBLIC = "public"

    # AUTHZ-05 target platform roles (RFC FRED-AUTHORIZATION-TARGET-MODEL §6.1).
    # Stored tuples only, granted by config-seeded bootstrap or explicit admin
    # action — never derived from Keycloak roles or groups.
    PLATFORM_ADMIN = "platform_admin"
    PLATFORM_OBSERVER = "platform_observer"

    # AUTHZ-05 target team roles (RFC §26 — renamed from owner/manager/member
    # during the second implementation pass). team_admin and team_editor are
    # orthogonal, not hierarchical (REBAC.md "hard cross-write rule").
    TEAM_ADMIN = "team_admin"
    TEAM_EDITOR = "team_editor"
    TEAM_ANALYST = "team_analyst"
    TEAM_MEMBER = "team_member"


class TagPermission(str, Enum):
    """Actions allowed on libraries/tags.

    Example:
    - `read`: list/search content.
    - `update`: rename tag, edit metadata, attach resources.
    """

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"

    # Normaly those 3 are "relation" and not "permission"
    # but openfga does not make distinction so we added
    # them here to use lookup_resources on them
    OWNER = RelationType.OWNER.value
    EDITOR = RelationType.EDITOR.value
    VIEWER = RelationType.VIEWER.value


class DocumentPermission(str, Enum):
    """Actions allowed on documents stored in libraries."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    # Process a document for RAG / SQL extraction. The `document#process`
    # relation already exists in schema.fga; this enum value exposes it.
    PROCESS = "process"


class ResourcePermission(str, Enum):
    """Actions allowed on non-document resources (files, templates, etc.)."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    SHARE = "share"


class TeamPermission(str, Enum):
    """Actions allowed at team scope.

    Example:
    - `can_update_resources`: create/update team libraries.
    - `can_administer_members`: add/remove team members.
    """

    CAN_READ = "can_read"
    CAN_UPDATE_INFO = "can_update_info"
    CAN_UPDATE_RESOURCES = "can_update_resources"
    CAN_UPDATE_AGENTS = "can_update_agents"
    CAN_READ_MEMEBERS = "can_read_members"
    CAN_ADMINISTER_MEMBERS = "can_administer_members"
    # AUTHZ-05 (RFC §26): renamed from CAN_ADMINISTER_MANAGERS/CAN_ADMINISTER_OWNERS.
    CAN_ADMINISTER_EDITORS = "can_administer_editors"
    CAN_ADMINISTER_ANALYSTS = "can_administer_analysts"
    CAN_ADMINISTER_ADMINS = "can_administer_admins"
    CAN_READ_CONVERSATIONS = "can_read_conversations"
    # AUTHZ-05 review item 1b: `team_member`-only, unlike CAN_READ (which
    # also admits `public`) — gates seeing/using the team's agents.
    CAN_USE_TEAM_AGENTS = "can_use_team_agents"

    # Team-scoped evaluation capabilities (RFC §6.2/§3.2).
    CAN_RUN_EVALUATIONS = "can_run_evaluations"
    CAN_MANAGE_EVALUATION_CORPUS = "can_manage_evaluation_corpus"
    CAN_READ_CONVERSATIONS_FOR_EVALUATION = "can_read_conversations_for_evaluation"


# Team permissions a `service_agent` caller is allowed to satisfy without an OpenFGA
# relation (RFC EVAL-AUTH, Solution A). Read-only: the evaluation worker executes
# agents and prepares their execution context, never mutates a team. Any write
# permission falls through to the normal ReBAC check and is therefore denied.
#
# CAN_USE_TEAM_AGENTS (2026-07-20, AGENT-EVALUATION-RFC.md §8.6): added after an
# AUTHZ-05 review moved `POST .../agent-instances/{id}/prepare-execution` from
# CAN_READ to CAN_USE_TEAM_AGENTS (real prompt content leak, product/api.py) without
# updating this allowlist to match — the evaluation worker's M2M identity, which
# structurally never holds a team relation, was then unconditionally denied on every
# run case. Safe to include: CAN_USE_TEAM_AGENTS gates read/prepare only, never a
# mutation, and the leak concern that moved prepare-execution off CAN_READ
# (`context_prompt_text`) never applies to the worker's calls — they never pass
# `session_id`, the only way that field is populated.
SERVICE_AGENT_ALLOWED_TEAM_PERMISSIONS = frozenset(
    {TeamPermission.CAN_READ, TeamPermission.CAN_USE_TEAM_AGENTS}
)


class AgentPermission(str, Enum):
    """Actions allowed on agents."""

    READ = "read"
    UPDATE = "update"
    DELETE = "delete"

    # "owner" is a relation in the FGA schema, not a permission,
    # but openfga does not make distinction so we add it here
    # to use lookup_resources on it (for owner-based filtering).
    OWNER = RelationType.OWNER.value


class OrganizationPermission(str, Enum):
    """Actions allowed at global organization scope.

    These gate endpoints that act on global / infrastructure surfaces with no
    resource instance to scope on (observability, platform administration).
    The check target is always the singleton ``organization:fred``. AUTHZ-05
    review item 8a removed the "any connected user" tier entirely (it never
    protected anything specific) — only platform_admin-gated capabilities and
    the raw `platform_observer` relation check remain.
    """

    CAN_EDIT_AGENT_CLASS_PATH = "can_edit_agent_class_path"

    # Already-defined organization relations, now exposed to Python callers.
    CAN_CREATE_TEAM = "can_create_team"

    # AUTHZ-05 review item 9 (RFC Part 6 §32): team-registry governance —
    # existence of teams only, never their data.
    CAN_LIST_ALL_TEAMS = "can_list_all_teams"
    CAN_DELETE_TEAM = "can_delete_team"
    CAN_RESCUE_TEAM_ADMIN = "can_rescue_team_admin"

    # RFC FRED-AUTHORIZATION-TARGET-MODEL §6.1: platform_observer's own named
    # capability (platform_admin included via the platform_observer union) —
    # the one relation for cross-user / platform-wide KPI observation. Gates
    # both the standalone KPI dashboard (`/monitoring/kpis`) and the
    # control-plane Analytics presets (`/admin/analytics`). AUTHZ-05 review
    # item 16: previously split into a second, platform_admin-only
    # `CAN_READ_KPI_GLOBAL` (legacy READ_GLOBAL) for the Analytics presets —
    # retired as a duplicate of this relation the RFC never asked for; today
    # `/admin/analytics` and `/monitoring/kpis` show the same platform-wide
    # recap to both platform_admin and platform_observer. When the Analytics
    # dashboard grows admin-only technical panels, gate those specific
    # widgets on a new, narrower capability — don't resurrect this split.
    CAN_OBSERVE_PLATFORM = "can_observe_platform"

    # Platform administration (platform_admin only).
    CAN_ADMINISTER_USERS = "can_administer_users"
    CAN_MANAGE_PLATFORM = "can_manage_platform"
    CAN_RUN_BENCHMARK = "can_run_benchmark"

    # Direct check against the raw `platform_observer` relation — not a
    # computed capability. Used to derive display-only frontend flags
    # (`PermissionSummary.is_platform_observer`, AUTHZ-05 review item 4/8a)
    # where no gated action exists to piggyback on.
    IS_PLATFORM_OBSERVER = "platform_observer"


class CapabilityPermission(str, Enum):
    """Actions allowed on one agent capability (CAPAB-01 / #1980, RFC §8.1).

    The target is always ``capability:<id>``. Callers check only these computed
    permissions — never the structural relations (`enabled`/`disabled`/
    `default_on`/`organization`), which are written solely by the enablement API.

    - `CAN_USE`: may agents of one team select this capability? The check
      SUBJECT IS THE TEAM (`Check(team:<id>, can_use, capability:<id>)`), never
      a user — a user-subject check would leak a capability enabled for one of
      the user's teams into every team context they browse. Answers the
      tri-state (inherited via default-on / explicitly enabled / disabled).
    - `CAN_MANAGE`: may an actor enable/disable it for a team or toggle its
      default-on marker? Org admin only.
    """

    CAN_USE = "can_use"
    CAN_MANAGE = "can_manage"


RebacPermission = (
    TagPermission
    | DocumentPermission
    | ResourcePermission
    | TeamPermission
    | AgentPermission
    | OrganizationPermission
    | CapabilityPermission
)


def _resource_for_permission(permission: RebacPermission) -> Resource:
    """Map one permission enum value to the resource type it targets.

    Example:
    - `TeamPermission.CAN_READ` -> `Resource.TEAM`
    - `TagPermission.UPDATE` -> `Resource.TAGS`
    """
    if isinstance(permission, TagPermission):
        return Resource.TAGS
    if isinstance(permission, DocumentPermission):
        return Resource.DOCUMENTS
    if isinstance(permission, ResourcePermission):
        return Resource.RESOURCES
    if isinstance(permission, TeamPermission):
        return Resource.TEAM
    if isinstance(permission, AgentPermission):
        return Resource.AGENT
    if isinstance(permission, OrganizationPermission):
        return Resource.ORGANIZATION
    if isinstance(permission, CapabilityPermission):
        return Resource.CAPABILITY
    raise ValueError(f"Unsupported permission type: {permission!r}")


@dataclass(frozen=True)
class Relation:
    """One authorization statement linking an actor to a target.

    Example:
    - `user alice` `owner` of `tag invoices`
    - `team thales` `owner` of `tag cir`
    """

    subject: RebacReference
    relation: RelationType
    resource: RebacReference


def team_organization_relation(team_id: str) -> Relation:
    """Canonical shape of the `organization -> team` structural edge (#2065).

    A module-level pure function, not a method, so it can be imported and
    called directly (e.g. `teams.service.create_team`'s direct bootstrap
    write) without requiring every duck-typed `RebacEngine` test double to
    implement it. `RebacEngine.ensure_team_organization_relations` (the
    cold-path repair primitive, below) is the only other caller — both go
    through this one function, so the tuple's shape has a single owner.
    """
    return Relation(
        subject=RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID),
        relation=RelationType.ORGANIZATION,
        resource=RebacReference(Resource.TEAM, team_id),
    )


class RebacDisabledResult:
    """
    Marker object returned when relationship authorization is disabled.

    Callers can branch on this value and apply fallback behavior.
    """


class RebacEngine(ABC):
    """Core authorization API used by all Fred backends.

    This class provides the common business operations ("can Alice update team
    resources?") while each concrete engine (OpenFGA, noop) handles storage.
    """

    # Opaque, engine-agnostic value a caller can pass as `consistency_token` to
    # force a strongly-consistent read ahead of a write/skip decision — the same
    # value every write already returns (`_persist_relation`/`delete_relation`),
    # so callers never need a real prior write to obtain one.
    HIGHER_CONSISTENCY: ClassVar[str] = "HIGHER_CONSISTENCY"

    @property
    def enabled(self) -> bool:
        """Tell whether relationship authorization checks are active."""
        return True

    async def close(self) -> None:
        """Release any held connections or sessions. No-op by default."""

    async def add_relation(
        self, relation: Relation, *, actor_uid: str | None = None
    ) -> str | None:
        """Persist one authorization statement and audit it.

        Why this is a concrete wrapper, not an abstract method:
        - every ReBAC write changes who can do what — it belongs in the audit
          trail (docs/swift/platform/OBSERVABILITY-AND-AUDIT.md §5). Three
          separate call sites (root bootstrap, team creation, capability
          default-on) were each found emitting no audit event at all, with
          several more callers across both control-plane-backend and
          knowledge-flow-backend never checked. One chokepoint here, instead
          of one `emit_audit_log` call per caller to remember, covers every
          current and future caller across every backend.
        - `actor_uid` is optional: pass it when the calling context knows who
          initiated the write. Never fabricated when absent — the write
          itself is never gated on it.

        Example:
        - Save `team thales owner tag cir`.
        Returns a backend-specific consistency token when available.
        """
        self._reject_unsanctioned_personal_team_write(relation)
        token = await self._persist_relation(relation)
        if self.enabled:
            emit_audit_log(
                "authz.relation.granted",
                actor_uid=actor_uid,
                subject=f"{relation.subject.type.value}:{relation.subject.id}",
                relation=relation.relation.value,
                resource=f"{relation.resource.type.value}:{relation.resource.id}",
            )
        return token

    @staticmethod
    def _reject_unsanctioned_personal_team_write(relation: Relation) -> None:
        """Enforce the personal-team tuple invariant at the one audited write chokepoint.

        A personal team (`personal-<uid>`) is a real ReBAC team object (AUTHZ-08),
        but the *only* tuples ever allowed to name one are:
        - the owner's own `team_editor` grant, self-healed by
          `_ensure_personal_team_editor` on first touch;
        - the structural `organization -> team` edge written by
          `ensure_team_organization_relations` (same shape used for every team).

        Every other shape — a different user, an elevated role, another relation
        type — is refused here, unconditionally, regardless of caller. This is
        what makes writing a real tuple for personal teams safe: no admin API,
        import/export path, or future caller can ever grant (or be tricked into
        granting) access to someone else's personal space, because there is
        exactly one write chokepoint (`add_relation`) and it only recognizes
        these two shapes for personal-team resources.
        """
        if relation.resource.type != Resource.TEAM or not is_personal_team_id(
            relation.resource.id
        ):
            return
        is_owner_editor_grant = (
            relation.subject.type == Resource.USER
            and relation.relation == RelationType.TEAM_EDITOR
            and relation.resource.id == personal_team_id(relation.subject.id)
        )
        is_organization_edge = (
            relation.subject.type == Resource.ORGANIZATION
            and relation.subject.id == ORGANIZATION_ID
            and relation.relation == RelationType.ORGANIZATION
        )
        if is_owner_editor_grant or is_organization_edge:
            return
        raise ValueError(
            f"Refusing to write {relation.relation.value} for "
            f"{relation.subject.type.value}:{relation.subject.id} onto personal "
            f"team {relation.resource.id!r} — only the space's own owner may hold "
            f"team_editor there, and it is provisioned automatically."
        )

    @abstractmethod
    async def _persist_relation(self, relation: Relation) -> str | None:
        """Backend-specific write for one relation.

        Not for direct use — call `add_relation` (this class), the audited
        public entrypoint every caller should go through instead.
        """

    @abstractmethod
    async def delete_relation(self, relation: Relation) -> str | None:
        """Remove one authorization statement.

        Returns a backend-specific consistency token when available.
        """

    @abstractmethod
    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        """Remove every statement touching the given reference.

        Example:
        - deleting an agent can remove all `owner`, `viewer`, or parent links.
        """

    @abstractmethod
    async def delete_all_relations_of_type(self, resource_type: Resource) -> int:
        """Remove every statement touching any reference of the given type.

        Self-healing sweep, deliberately not id-driven: `delete_all_relations_of_reference`
        only clears what a caller already knows to ask for. If the Postgres row a caller
        would otherwise enumerate ids from is already gone (a prior partial reset, a manual
        edit, drift between the two stores), the corresponding tuples never get asked for
        and become permanent orphans. This reads the live authorization store itself, so a
        rehearsal reset (`import_export/teardown.py::run_teardown`) converges to zero
        tuples of that type regardless of any such history. Returns the number deleted.
        """

    async def add_relations(
        self, relations: Iterable[Relation], *, actor_uid: str | None = None
    ) -> str | None:
        """Persist several statements and return the latest consistency token.

        Each one is audited individually through `add_relation` — see there
        for why. `actor_uid` is forwarded unchanged to every one.

        Example:
        - Add owner and viewer links in one call after resource sharing.
        """

        tokens = await asyncio.gather(
            *(
                self.add_relation(relation, actor_uid=actor_uid)
                for relation in relations
            ),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    async def _teams_with_relation(
        self,
        *,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> set[str] | None:
        """Bulk-read every team currently holding `subject -> relation -> team:*`.

        Backs the existence-check `ensure_*`/`revoke_*` team helpers below:
        called on every team listing (#2065), a per-team `add_relation`/
        `delete_relation` fan-out re-writes (and, for grants, re-audits) an
        edge that almost always already has the correct state — one bulk
        `list_relations` read replaces that fan-out with a single round-trip
        (paginated) the caller diffs locally.

        `subject` must be exact (`organization:fred` for the organization
        edge, `user:*` for the public edge) — OpenFGA's Read API rejects a
        relation + object-type-only filter with no `user` to anchor it (see
        `list_relations`'s docstring), so there is no "any subject" bulk-read
        shape here; every caller of this helper already has one exact subject.

        `consistency_token` defaults to the engine's eventually-consistent
        read — fine for the lazy, bulk, self-healing listing call sites this
        was built for. A caller on a direct, single-team write path (a
        visibility toggle, not a bulk backfill) must pass `HIGHER_CONSISTENCY`
        instead: an eventually-consistent read here can still miss a tuple
        this same request-chain just wrote moments earlier, causing the
        caller to wrongly skip a still-required write.

        Returns `None` when relation listing is disabled (`RebacDisabledResult`)
        so callers fall back to their prior unconditional write/delete
        behavior — cheap and side-effect-free on `NoopRebacEngine`, whose
        `_persist_relation` performs no I/O and whose `enabled=False` already
        skips the audit call.
        """
        existing = await self.list_relations(
            resource_type=Resource.TEAM,
            relation=relation,
            subject=subject,
            consistency_token=consistency_token,
        )
        if isinstance(existing, RebacDisabledResult):
            return None
        # `list_relations` already filtered server-side on the exact `subject`
        # — no client-side re-filter needed.
        return {rel.resource.id for rel in existing}

    async def ensure_team_organization_relations(
        self,
        team_ids: Iterable[str],
    ) -> str | None:
        """Cold-path repair: back-fill the `organization -> team` structural
        edge for teams that may pre-date it.

        This is no longer called from any per-request path (#2065) — every
        collaborative team gets this edge once, directly, at creation
        (`teams.service.create_team`, via `team_organization_relation`
        above). The only remaining callers are cold paths that must handle
        teams created before that invariant existed or outside the ordinary
        creation flow: control-plane startup reconciliation (once per
        process, over the full team registry) and platform import (Swift-
        native and kea bundles). `require_team_access`/`get_team_by_id`/
        `_list_teams` and the shared `check_user_team_permission(s)_or_raise`
        helpers below never call this — nothing in schema.fga's computed team
        permissions reads the persisted edge; capability team-scoping instead
        uses a separate, never-persisted *contextual* reverse tuple
        (`RelationType.TEAM`'s docstring above).

        Idempotent, and — since #2065 — only writes (and audits) edges that
        are actually missing: a bulk `_teams_with_relation` read filters out
        every team that already has the edge, so a steady-state call (the
        common case once every team has been backfilled once) issues zero
        writes instead of one per team. Returns the write consistency token
        when a write actually happened, else `None`.
        """
        unique_team_ids: list[str] = []
        seen: set[str] = set()
        for team_id in team_ids:
            if not team_id or team_id in seen:
                continue
            seen.add(team_id)
            unique_team_ids.append(team_id)

        if not unique_team_ids:
            return None

        organization = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)
        existing_team_ids = await self._teams_with_relation(
            relation=RelationType.ORGANIZATION, subject=organization
        )
        target_team_ids = (
            unique_team_ids
            if existing_team_ids is None
            else [tid for tid in unique_team_ids if tid not in existing_team_ids]
        )
        if not target_team_ids:
            return None

        relations = [team_organization_relation(team_id) for team_id in target_team_ids]
        return await self.add_relations(relations)

    async def ensure_team_public_relations(
        self,
        team_ids: Iterable[str],
        *,
        consistency_token: str | None = None,
    ) -> str | None:
        """Ensure each team grants `public` (profile/discovery `can_read`) to
        every user (TEAM-09, RFC FRED-TEAM-CONFIG-RFC.md §5.1.1).

        Marketplace discovery is gated by `TeamVisibility` (TEAM-10, RFC
        §5.1.2), never by `joining_mode` — only the ability to become a
        member is gated (see `JoiningMode`). Callers must pass only teams
        whose stored `visibility` is `PUBLIC`; a `PRIVATE` team's `public`
        relation is instead withheld/revoked via
        `revoke_team_public_relations` below. This mirrors
        `ensure_team_organization_relations` exactly: idempotent
        (`on_duplicate_writes=IGNORE` at the OpenFGA write layer), called
        both at team creation and lazily on every team listing, so it
        backfills every pre-existing public team without a separate one-off
        migration.

        Example:
        - Before returning `GET /teams`, ensure `user:* -> public -> team:<id>`
          exists for every `PUBLIC` team about to be listed.

        Since #2065, only writes edges actually missing (see
        `_teams_with_relation`) — a steady-state call issues zero writes. Pass
        `consistency_token=HIGHER_CONSISTENCY` on a direct visibility-toggle
        call (`update_team`) — the lazy listing call sites can keep the
        default eventually-consistent read.
        """
        unique_team_ids: list[str] = []
        seen: set[str] = set()
        for team_id in team_ids:
            if not team_id or team_id in seen:
                continue
            seen.add(team_id)
            unique_team_ids.append(team_id)

        if not unique_team_ids:
            return None

        wildcard_user = RebacReference(Resource.USER, "*")
        existing_team_ids = await self._teams_with_relation(
            relation=RelationType.PUBLIC,
            subject=wildcard_user,
            consistency_token=consistency_token,
        )
        target_team_ids = (
            unique_team_ids
            if existing_team_ids is None
            else [tid for tid in unique_team_ids if tid not in existing_team_ids]
        )
        if not target_team_ids:
            return None

        relations = [
            Relation(
                subject=wildcard_user,
                relation=RelationType.PUBLIC,
                resource=RebacReference(Resource.TEAM, team_id),
            )
            for team_id in target_team_ids
        ]
        return await self.add_relations(relations)

    async def revoke_team_public_relations(
        self,
        team_ids: Iterable[str],
        *,
        consistency_token: str | None = None,
    ) -> str | None:
        """Revoke `public` from every user for each team — the inverse of
        `ensure_team_public_relations`, for teams whose `TeamVisibility` is
        `PRIVATE` (TEAM-10, RFC FRED-TEAM-CONFIG-RFC.md §5.1.2).

        A private team must be entirely unreadable to non-members — not just
        absent from the marketplace listing, but also refused on a direct
        `GET /teams/{team_id}` (both paths gate on the same `can_read =
        team_member or public` computed relation). Revoking `public` rather
        than layering a separate "listed" concept keeps that single
        computed relation authoritative for both surfaces. `team_member`
        access is untouched — a private team behaves identically to a
        public one for its own members.

        Idempotent (deleting an absent tuple is a no-op) and safe to call
        both lazily (every team listing, alongside
        `ensure_team_public_relations` for the public subset) and
        immediately on a `visibility` change (`update_team`), matching the
        grant side's own dual call sites.

        Since #2065, only deletes edges actually present (see
        `_teams_with_relation`) — a steady-state call issues zero deletes.
        Pass `consistency_token=HIGHER_CONSISTENCY` on a direct
        visibility-toggle call: an eventually-consistent existence-check read
        can still miss a `public` grant this same request just wrote moments
        earlier (e.g. a team made public then immediately private again),
        which would wrongly skip the revoke and leave a private team publicly
        readable until a later reconciliation. The lazy listing call sites
        can keep the default eventually-consistent read.
        """
        unique_team_ids: list[str] = []
        seen: set[str] = set()
        for team_id in team_ids:
            if not team_id or team_id in seen:
                continue
            seen.add(team_id)
            unique_team_ids.append(team_id)

        if not unique_team_ids:
            return None

        wildcard_user = RebacReference(Resource.USER, "*")
        existing_team_ids = await self._teams_with_relation(
            relation=RelationType.PUBLIC,
            subject=wildcard_user,
            consistency_token=consistency_token,
        )
        target_team_ids = (
            unique_team_ids
            if existing_team_ids is None
            else [tid for tid in unique_team_ids if tid in existing_team_ids]
        )
        if not target_team_ids:
            return None

        relations = [
            Relation(
                subject=wildcard_user,
                relation=RelationType.PUBLIC,
                resource=RebacReference(Resource.TEAM, team_id),
            )
            for team_id in target_team_ids
        ]
        return await self.delete_relations(relations)

    async def add_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
        *,
        actor_uid: str | None = None,
    ) -> str | None:
        """Create one statement where the subject is a user.

        `actor_uid` defaults to `user.uid` — every current caller grants a
        user a relation on themselves (e.g. tag ownership on creation), so the
        subject and the acting principal are the same. Pass it explicitly if a
        future caller ever grants on someone else's behalf.

        Example:
        - Add `user:bob editor tag:finance`.
        """
        return await self.add_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            ),
            actor_uid=actor_uid if actor_uid is not None else user.uid,
        )

    async def delete_relations(self, relations: Iterable[Relation]) -> str | None:
        """Delete several statements and return the latest consistency token.

        Example:
        - Remove owner/manager/member links when removing a team member.
        """
        tokens = await asyncio.gather(
            *(self.delete_relation(relation) for relation in relations),
            return_exceptions=False,
        )

        token: str | None = None
        for t in reversed(tokens):
            if t is not None:
                token = t
                break

        return token

    @abstractmethod
    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject: RebacReference,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        """List every persisted tuple with `relation` on any `resource_type`
        object where `subject` is the exact tuple user.

        `subject` must be exact, not just a type: OpenFGA's Read API rejects a
        relation + object-type-only (no id) filter that also has no `user` to
        anchor it — confirmed against live OpenFGA v1.12.1 and v1.15.1 stores, HTTP 400
        `"the 'tuple_key' field was provided but the object type field is
        required and both the object id and user cannot be empty"`. There is
        no OpenFGA query shape for "this relation, across every object of a
        type, for any user" — a caller that needs that (no single exact
        subject to anchor on) must fan out per-object instead, e.g. via
        `list_direct_relations` (see `teams.service._bulk_team_membership`
        for the #2065 case this replaced).
        """

    async def delete_user_relation(
        self,
        user: KeycloakUser,
        relation: RelationType,
        resource_type: Resource,
        resource_id: str,
    ) -> str | None:
        """Delete one statement where the subject is a user."""
        return await self.delete_relation(
            Relation(
                subject=RebacReference(Resource.USER, user.uid),
                relation=relation,
                resource=RebacReference(resource_type, resource_id),
            )
        )

    async def delete_user_relations(self, user: KeycloakUser) -> str | None:
        """Delete all statements referencing a user."""
        return await self.delete_all_relations_of_reference(
            RebacReference(Resource.USER, user.uid)
        )

    @abstractmethod
    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a subject can access for one permission.

        Example:
        - Return all teams a user can read.
        """

    @abstractmethod
    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List subjects linked to a resource by one relation.

        Example:
        - List all owners of one team.
        """

    async def has_direct_relation(
        self,
        subject: RebacReference,
        relation: RelationType,
        resource: RebacReference,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Return `True` when a *literal* tuple is persisted for this triple.

        Unlike `has_permission` (Check) or `lookup_subjects` (ListUsers), this
        must not resolve computed/union relations (e.g. schema.fga's
        `team_member: [user] or team_admin or team_editor or team_analyst`).
        A `team_admin`-only user must read as `False` here even though they
        satisfy the computed `team_member` relation everywhere else.

        Example:
        - Distinguish "this user holds a direct `team_member` tuple" from
          "this user is a `team_member` only because they are `team_admin`" —
          needed to preserve a member's base role when a single elevated role
          is later revoked (AUTHZ-06).

        Not implemented by default; override in engines that can answer a
        direct-tuple read without expanding usersets.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support direct relation reads"
        )

    async def list_direct_relations(
        self,
        resource: RebacReference,
        *,
        subject: RebacReference | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        """Read every relation literally persisted on one exact resource.

        Why this function exists:
        - a caller projecting several role-shaped facts about one resource
          (admins, member count, the caller's own roles) from a single team
          needs one exact `Read` on that object, not a relation-by-relation
          scan across every team (`list_relations`, unaffected — it stays the
          bulk, cross-team primitive backing `_list_teams`)

        How to use it:
        - pass the exact resource; no relation filter is applied server-side,
          so the caller folds the returned tuples locally
        - pass `subject` (an exact `RebacReference`, e.g. one user) to narrow
          server-side to that one subject's relations on this resource — e.g.
          `_get_user_roles_in_team` transfers O(that user's roles), never
          O(every member of the team). `subject=None` (the default) returns
          every relation on the resource, of any subject.

        Not implemented by default; override in engines that can answer an
        exact-object tuple read (mirrors `has_direct_relation` above).
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not support direct relation listing"
        )

    async def lookup_user_resources(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        *,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        """List resources a user can access for one permission."""
        resource_type = _resource_for_permission(permission)
        # Self-heal the caller's own personal-team tuple before enumerating
        # (AUTHZ-08 follow-up): `lookup_resources`/OpenFGA `ListObjects` never
        # goes through `has_user_permission`/`check_user_team_permission_or_raise`,
        # so without this a first-touch user's own personal team was silently
        # missing from "list my teams" results (e.g. the `/fs` virtual `/teams`
        # directory) until some other check-triggering call happened to
        # provision it first.
        await self._ensure_personal_team_editor(
            user, resource_type, personal_team_id(user.uid)
        )
        return await self.lookup_resources(
            subject=RebacReference(Resource.USER, user.uid),
            permission=permission,
            resource_type=resource_type,
            consistency_token=consistency_token,
        )

    @abstractmethod
    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        """Return `True` when a subject is authorized for an action."""

    async def has_permissions(
        self,
        subject: RebacReference,
        permissions: Sequence[RebacPermission],
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[bool]:
        """Check several permissions for the same subject/resource pair.

        Why this function exists:
        - a caller projecting a permission list (e.g. `TeamWithPermissions.
          permissions`) needs one round-trip per permission set, not one
          `has_permission` per permission — `OpenFgaRebacEngine` overrides
          this with a native `BatchCheck` call; this default (concurrent
          `has_permission`s) keeps every other engine and test fake working
          without implementing a new abstract method.

        How to use it:
        - pass permissions in the order you want results back in; an empty
          sequence returns `[]` without calling the engine at all

        `contextual_relations` is materialized once, up front — if a caller
        passed a generator, iterating it once per concurrent `has_permission`
        call would exhaust it after the first and starve every other call
        instead of raising, since `asyncio.gather` schedules them concurrently
        with no guaranteed order.

        Example:
        - `allowed = await rebac.has_permissions(subject, list(TeamPermission), team_ref)`
        """
        permissions_list = list(permissions)
        if not permissions_list:
            return []
        contextual_relations_seq = (
            tuple(contextual_relations) if contextual_relations is not None else None
        )
        return list(
            await asyncio.gather(
                *(
                    self.has_permission(
                        subject,
                        permission,
                        resource,
                        contextual_relations=contextual_relations_seq,
                        consistency_token=consistency_token,
                    )
                    for permission in permissions_list
                )
            )
        )

    async def _ensure_personal_team_editor(
        self, user: KeycloakUser, resource_type: Resource, resource_id: str
    ) -> None:
        """Self-heal a personal team's own `team_editor` tuple on first touch (AUTHZ-08).

        Personal teams (`personal-<uid>`) are real ReBAC team objects, but carry
        no tuple until the owner's first permission check touches one — this
        lazily provisions exactly one (`user:<uid> team_editor team:personal-
        <uid>`), matching `build_personal_team`'s hardcoded permission set
        (`can_read`, `can_update_resources`, `can_update_agents` — all implied
        by `team_editor`). Runs before every `check_user_permission_or_raise`/
        `has_user_permission` call so it applies uniformly across every backend,
        with no per-caller special-casing.

        Never provisions for another user's personal team — `add_relation`'s own
        write-guard would refuse that shape regardless, but this check avoids
        even attempting (and audit-logging) a doomed write on every such call.
        """
        if not self.enabled or resource_type != Resource.TEAM:
            return
        if not is_personal_team_id(resource_id):
            return
        if resource_id != personal_team_id(user.uid):
            return
        team_ref = RebacReference(Resource.TEAM, resource_id)
        user_ref = RebacReference(Resource.USER, user.uid)
        if await self.has_direct_relation(user_ref, RelationType.TEAM_EDITOR, team_ref):
            return
        await self.add_user_relation(
            user, RelationType.TEAM_EDITOR, Resource.TEAM, resource_id
        )

    async def has_user_permission(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> bool:
        """Check one permission for one user/resource pair."""
        resource_type = _resource_for_permission(permission)
        await self._ensure_personal_team_editor(user, resource_type, resource_id)
        return await self.has_permission(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            consistency_token=consistency_token,
        )

    async def check_permission_or_raise(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> None:
        """Raise `AuthorizationError` when access is denied.

        Example:
        - Raises if Bob tries to update a team where he is only a member.
        """
        if not await self.has_permission(
            subject,
            permission,
            resource,
            contextual_relations=contextual_relations,
            consistency_token=consistency_token,
        ):
            logger.warning(
                "ReBAC authorization denied: subject=%s:%s permission=%s resource=%s:%s",
                subject.type.value,
                subject.id,
                permission.value,
                resource.type.value,
                resource.id,
            )
            raise AuthorizationError(
                subject.id,
                permission.value,
                resource.type,
                f"Not authorized to {permission.value} {resource.type.value} {resource.id}",
            )

    async def check_user_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: RebacPermission,
        resource_id: str,
        *,
        consistency_token: str | None = None,
    ) -> None:
        """User-focused wrapper around `check_permission_or_raise`."""
        resource_type = _resource_for_permission(permission)
        await self._ensure_personal_team_editor(user, resource_type, resource_id)
        await self.check_permission_or_raise(
            RebacReference(Resource.USER, user.uid),
            permission,
            RebacReference(resource_type, resource_id),
            consistency_token=consistency_token,
        )

    async def check_user_team_permission_or_raise(
        self,
        user: KeycloakUser,
        permission: TeamPermission,
        team_id: str,
    ) -> str | None:
        """Check one team permission — thin wrapper over
        `check_user_team_permissions_or_raise`."""
        return await self.check_user_team_permissions_or_raise(
            user=user,
            team_id=team_id,
            permissions=[permission],
        )

    async def check_user_team_permissions_or_raise(
        self,
        user: KeycloakUser,
        team_id: str,
        permissions: Iterable[TeamPermission],
    ) -> str | None:
        """Check one or more team permissions for a user on one team.

        The canonical path for team permission checks across every backend
        (control-plane, knowledge-flow, fred-runtime). Since #2065 this no
        longer ensures `organization -> team` first: that structural edge is
        established once, directly, at team creation
        (`teams.service.create_team`), and repaired only on cold paths
        (control-plane startup, platform import) via
        `ensure_team_organization_relations` — never here. Nothing in
        schema.fga's computed team permissions reads the persisted edge, so a
        per-request Check never needed it. Returns `None`: with no write in
        this call, there is no consistency token to propagate. No I/O at all
        when `permissions` is empty.
        """
        permissions_to_check = list(permissions)
        if not permissions_to_check:
            return None

        await asyncio.gather(
            *(
                self.check_user_permission_or_raise(
                    user=user,
                    permission=permission,
                    resource_id=team_id,
                )
                for permission in permissions_to_check
            ),
            return_exceptions=False,
        )
        return None
