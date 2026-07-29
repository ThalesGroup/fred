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

"""KEA CUTOVER 2026 — temporary identity/team-membership reconciliation.

⚠️ DELETE THIS FILE a few weeks after the S3NS cutover completes, along with every
call site tagged "KEA CUTOVER 2026" in `importer.py` and `kea_migration_api.py`
(a standalone router — delete that whole file too). Nothing outside those three
files imports from this module; removal is a self-contained revert.

Why this exists (design session 2026-07-25):
- Real users authenticate via OneAccess (Thales SSO broker), bridged into BOTH kea's
  Keycloak and swift's (S3NS). Each Keycloak realm independently generates its own
  local `sub` for a person on their *first* federated login — the one identifier both
  systems are guaranteed to share is the Keycloak *username* (e.g. "t0324620"), never
  the `sub`. Whether S3NS's `sub` happens to match kea's depends on whether a native
  Keycloak realm import (which can set an explicit id) ran first — not guaranteed, so
  every kea identity is resolved *live*, per run, by username instead of assumed.
- kea's own OpenFGA store never persisted a `member` team relation (main branch derives
  it live from the Keycloak JWT `groups` claim) — swift's target schema.fga does the
  opposite (`team_member` is a stored tuple, "never derived from Keycloak roles or
  groups"). So kea's plain team members only ever show up in a Keycloak *group
  membership* export (`realm.json` `users[].groups`), never in an OpenFGA tuple dump —
  `transform_kea_tuples` (this module) has nothing to translate for them.
- The swift Keycloak (S3NS) may be empty, partially populated, or fully populated at
  the moment this import runs — never assumed. An identity that can't be resolved yet
  is skipped cleanly (not failed) and reported as "pending first login": every write
  this module performs goes through `RebacEngine.add_relation`, which is idempotent
  (`on_duplicate_writes=IGNORE`), so re-running the same bundle later — after more
  people have logged in via OneAccess — safely fills in exactly what was missing, and
  nothing already applied is touched twice. This is deliberate: it replaces a
  login-hook or a "pending grants" table with "just re-run it," which needed no new
  infrastructure and is trivial to reason about under time pressure.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fred_core import RebacReference, Relation, RelationType, Resource

from control_plane_backend.import_export.bundle import KBundle
from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.service import find_user_subs_bulk


class KeaUserOutcome(str, Enum):
    """How one kea identity resolved against swift's (S3NS) Keycloak, this run."""

    # Found on swift Keycloak, same sub as kea — a native realm import (or equivalent)
    # preserved identity end to end; nothing needed translating.
    MATCHED = "matched"
    # Found on swift Keycloak, but under a DIFFERENT sub than kea's — the broker (or
    # whatever created the swift-side account) did not preserve subs; the swift-side
    # sub actually found is used instead.
    RELINKED = "relinked"
    # Not found at all yet — presumably hasn't logged in via OneAccess on S3NS yet.
    # Nothing about this person is written this run; a later re-run picks it up.
    PENDING = "pending"


@dataclass(frozen=True)
class KeaUserResolution:
    kea_sub: str
    kea_username: str
    outcome: KeaUserOutcome
    swift_sub: str | None  # None only when outcome is PENDING


_SUMMARY_NAME_LIMIT = 20


def format_usernames_for_warning(usernames: Iterable[str]) -> str:
    """Render a sorted, comma-joined username list, capped so a real cutover-scale
    run (thousands of PENDING/RELINKED users) can never blow past Postgres
    NOTIFY's ~8000-byte payload limit — `summary_lines()`'s output ends up in a
    `pg_notify` payload via `MigrationResult.warnings` (fred_core.tasks.bus), and
    an uncapped join crashed a real 1008-user rehearsal run with
    `InvalidParameterValueError: payload string too long` (2026-07-25). A list
    this long is unreadable to an operator anyway — the count is already in the
    line's own prefix.
    """
    names = sorted(usernames)
    if len(names) <= _SUMMARY_NAME_LIMIT:
        return ", ".join(names)
    shown = names[:_SUMMARY_NAME_LIMIT]
    return ", ".join(shown) + f", … (+{len(names) - _SUMMARY_NAME_LIMIT} more)"


@dataclass
class KeaReconciliationReport:
    """Structured, per-category outcome of one kea→swift reconciliation run.

    Deliberately separate from `importer.py`'s `MigrationReport` — that shape is frozen
    for `MigrationResult`/OpenAPI stability (see its own docstring); this one is
    temporary migration-window tooling, free to change, and consumed directly (as JSON)
    by the dedicated `/admin/kea-migration` page for a fast look-then-act loop.
    """

    matched: list[KeaUserResolution] = field(default_factory=list)
    relinked: list[KeaUserResolution] = field(default_factory=list)
    pending: list[KeaUserResolution] = field(default_factory=list)
    team_member_grants: int = 0
    team_member_pending: int = 0
    orphan_teams_dropped: list[str] = field(default_factory=list)
    admin_less_teams: list[str] = field(default_factory=list)

    def summary_lines(self) -> list[str]:
        """Render as short, human-readable lines — merged into `MigrationReport.warnings`
        on a real apply, and shown directly, verbatim, on the dry-run admin page."""
        lines = [
            f"KEA RECONCILIATION: {len(self.matched)} user(s) matched "
            "(sub preserved end to end)"
        ]
        if self.relinked:
            lines.append(
                f"KEA RECONCILIATION: {len(self.relinked)} user(s) RELINKED (found on "
                "swift Keycloak under a DIFFERENT sub than kea's — used the swift-side "
                "sub): "
                + format_usernames_for_warning(r.kea_username for r in self.relinked)
            )
        if self.pending:
            lines.append(
                f"KEA RECONCILIATION: {len(self.pending)} user(s) PENDING first login "
                "on swift Keycloak — their team/agent/tag ownership will apply "
                "automatically on the next reconciliation run after they log in: "
                + format_usernames_for_warning(r.kea_username for r in self.pending)
            )
        lines.append(
            f"KEA RECONCILIATION: {self.team_member_grants} plain team-membership "
            f"grant(s) applied, {self.team_member_pending} pending first login"
        )
        if self.orphan_teams_dropped:
            lines.append(
                f"KEA RECONCILIATION: {len(self.orphan_teams_dropped)} orphan team "
                "reference(s) dropped (referenced in OpenFGA tuples but no matching "
                "Keycloak group in the realm export): "
                + ", ".join(sorted(self.orphan_teams_dropped))
            )
        if self.admin_less_teams:
            lines.append(
                f"KEA RECONCILIATION ⚠ {len(self.admin_less_teams)} team(s) will have "
                "ZERO team_admin after this import — ungoverned team, fix before "
                "relying on it: " + ", ".join(sorted(self.admin_less_teams))
            )
        return lines


class KeaUserResolver:
    """Resolves kea Keycloak subs to swift (S3NS) Keycloak subs, by username,
    against one bulk snapshot of the target realm taken at construction time.

    One instance per run, shared by every call site that needs a username -> sub
    lookup (relation subjects, agent/tag/resource owners, platform-role grants,
    team-membership derivation, and the `users.json` provisioning phase in
    `importer.py`) — never construct a second instance mid-run, or the whole point
    of the shared cache/prefetch below is lost.

    A cutover-scale run (~2000 users) makes bulk resolution the only viable
    strategy: Swift starts with just the root admin in Keycloak, so on a first
    import essentially every kea username is missing from the target realm.
    `create()` lists the whole target realm once (`find_user_subs_bulk`, itself a
    single paginated sweep) and builds an in-memory `username -> sub` index —
    the *complete* answer for this run. That snapshot is treated as authoritative
    even when genuinely empty: a username missing from it resolves to `None`
    (PENDING) immediately, with zero further Keycloak calls. There is
    deliberately no per-username fallback lookup — one was tried and it
    silently reintroduced up to ~1900 individual Admin API calls on exactly the
    production scenario the bulk prefetch exists to avoid, slow enough to blow
    past the dry-run's HTTP timeout. A username created mid-run by
    `_provision_bundle_identities` is folded into the same snapshot via
    `remember()`, so it resolves with zero further I/O too. If the bulk sweep
    itself raises — a real Keycloak/network error, or Keycloak M2M being
    disabled (`find_user_subs_bulk` raises `KeycloakM2MUserOperationDisabledError`
    rather than returning `{}`, so a misconfigured M2M client can never look
    identical to a target realm that legitimately has zero matching users) —
    that exception is left to propagate — `create()` is called before the
    Postgres transaction opens, so a broken bulk sweep fails the import before
    anything is written.
    """

    def __init__(self, prefetched: dict[str, str] | None = None) -> None:
        self._prefetched: dict[str, str] = dict(prefetched or {})
        self._cache: dict[str, KeaUserResolution] = {}

    @classmethod
    async def create(
        cls, user_deps: UserServiceDependencies | None
    ) -> "KeaUserResolver":
        """Build a resolver with the target realm's users prefetched in bulk.

        The one recommended construction path for both the real import and the
        dry-run preview (`kea_migration_api.py`) — see the class docstring for why
        a bulk prefetch, never a per-username lookup, is what keeps a
        cutover-scale run fast and bounded. A real bulk-sweep failure (Keycloak
        down, network error) propagates from here, aborting the import before any
        Postgres write.
        """
        prefetched = (
            await find_user_subs_bulk(user_deps) if user_deps is not None else {}
        )
        return cls(prefetched)

    async def find_sub(self, username: str) -> str | None:
        """Resolve one username to its swift sub — the shared low-level primitive.

        A pure dict lookup against the bulk-prefetched snapshot (see the class
        docstring): present -> its sub, absent -> `None` (PENDING). Never makes a
        Keycloak call itself — the bulk snapshot taken at `create()` time is the
        single source of truth for the whole life of this resolver instance.
        """
        return self._prefetched.get(username)

    def remember(self, username: str, swift_sub: str) -> None:
        """Record an identity resolvable with zero further I/O this run.

        Called right after `_provision_bundle_identities` creates a Keycloak user —
        without this, `find_sub` would see the new username missing from the
        bulk-prefetched snapshot and treat it as PENDING, even though this same
        run just created it.
        """
        self._prefetched[username] = swift_sub

    async def resolve(self, kea_sub: str, kea_username: str) -> KeaUserResolution:
        cached = self._cache.get(kea_username)
        if cached is not None:
            return cached
        swift_sub = await self.find_sub(kea_username)
        if swift_sub is None:
            result = KeaUserResolution(
                kea_sub, kea_username, KeaUserOutcome.PENDING, None
            )
        elif swift_sub == kea_sub:
            result = KeaUserResolution(
                kea_sub, kea_username, KeaUserOutcome.MATCHED, swift_sub
            )
        else:
            result = KeaUserResolution(
                kea_sub, kea_username, KeaUserOutcome.RELINKED, swift_sub
            )
        self._cache[kea_username] = result
        return result


def kea_known_group_ids(kea_realm: dict[str, Any] | None) -> set[str]:
    """Return every Keycloak group id in a kea realm export, named or not.

    Deliberately broader than `importer.py`'s own `_realm_group_names` (which only
    returns *named* groups, since that function's job is name resolution) — this one
    answers "does this group exist at all", the question `drop_orphan_teams` needs to
    tell a real-but-unnamed group apart from a genuinely stale tuple reference.
    """
    ids: set[str] = set()

    def _walk(groups: list[dict[str, Any]]) -> None:
        for group in groups:
            group_id = group.get("id")
            if isinstance(group_id, str) and group_id:
                ids.add(group_id)
            _walk(group.get("subGroups") or [])

    _walk((kea_realm or {}).get("groups") or [])
    return ids


def kea_username_by_sub(kea_realm: dict[str, Any] | None) -> dict[str, str]:
    """Return kea_sub -> username from a *kea* Keycloak realm export.

    Only a full export (`kc export --users`) carries `users[]` — a partial export
    (groups only) yields an empty map, same fallback shape as `importer.py`'s own
    `_realm_group_names`.
    """
    out: dict[str, str] = {}
    for user in (kea_realm or {}).get("users") or []:
        sub = user.get("id")
        username = user.get("username")
        if isinstance(sub, str) and sub and isinstance(username, str) and username:
            out[sub] = username
    return out


def kea_group_memberships(kea_realm: dict[str, Any] | None) -> dict[str, list[str]]:
    """Return kea_sub -> [group name, ...] from a kea realm export.

    A full realm export's `users[].groups` carries group *paths* ("/northbridge");
    this strips the leading "/" to match the `name` keys `_realm_group_names`
    produces — kea teams are always top-level groups.
    """
    out: dict[str, list[str]] = {}
    for user in (kea_realm or {}).get("users") or []:
        sub = user.get("id")
        if not isinstance(sub, str) or not sub:
            continue
        paths = user.get("groups") or []
        names = [p.lstrip("/") for p in paths if isinstance(p, str) and p.lstrip("/")]
        if names:
            out[sub] = names
    return out


def _record(report: KeaReconciliationReport, resolution: KeaUserResolution) -> None:
    bucket = {
        KeaUserOutcome.MATCHED: report.matched,
        KeaUserOutcome.RELINKED: report.relinked,
        KeaUserOutcome.PENDING: report.pending,
    }[resolution.outcome]
    if resolution not in bucket:
        bucket.append(resolution)


async def resolve_user_sub(
    kea_sub: str,
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> str | None:
    """Resolve one bare kea sub (agent `created_by`, personal tag `owner_id`, a
    platform-role grant) to its swift sub. `None` when unresolved (PENDING) — the
    caller decides how to handle that (usually: drop this one write, keep going).
    """
    username = username_by_sub.get(kea_sub)
    if username is None:
        resolution = KeaUserResolution(kea_sub, kea_sub, KeaUserOutcome.PENDING, None)
        report.pending.append(resolution)
        return None
    resolution = await resolver.resolve(kea_sub, username)
    _record(report, resolution)
    return resolution.swift_sub


# Keycloak Admin API calls per distinct username, bounded so a cutover-scale run
# (~2000 users) doesn't fire thousands of concurrent requests at once — still fast,
# since KeaUserResolver caches by username and this pre-pass already deduplicates by
# kea_sub before resolving.
_RESOLVE_CONCURRENCY = 15


async def resolve_relation_subjects(
    relations: list[Relation],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> list[Relation]:
    """Rewrite every USER-typed subject in `relations` to its resolved swift sub.

    Team/organization-typed subjects pass through unchanged — a swift team's identity
    never goes through Keycloak (`teams/service.py::create_team` mints its own random
    UUID, no Keycloak call), so there is nothing to resolve there. A relation whose
    user subject cannot be resolved yet (PENDING) is dropped from the output — not
    written this run — and counted in `report.pending`, so a later re-run picks it up.
    """
    distinct_kea_subs = list(
        {str(r.subject.id) for r in relations if r.subject.type == Resource.USER}
    )
    resolved: dict[str, str | None] = {}
    for start in range(0, len(distinct_kea_subs), _RESOLVE_CONCURRENCY):
        chunk = distinct_kea_subs[start : start + _RESOLVE_CONCURRENCY]
        results = await asyncio.gather(
            *(resolve_user_sub(sub, username_by_sub, resolver, report) for sub in chunk)
        )
        resolved.update(zip(chunk, results))

    out: list[Relation] = []
    for relation in relations:
        if relation.subject.type != Resource.USER:
            out.append(relation)
            continue
        swift_sub = resolved[str(relation.subject.id)]
        if swift_sub is None:
            continue
        out.append(
            Relation(
                subject=RebacReference(Resource.USER, swift_sub),
                relation=relation.relation,
                resource=relation.resource,
            )
        )
    return out


async def resolve_agent_team_index(
    agent_team_index: dict[str, str],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> dict[str, str]:
    """Resolve the `personal-{kea_sub}` half of `_build_agent_team_index`'s output.

    Team-owned entries (`team_id_str` is a Keycloak group id) pass through unchanged —
    team identity never goes through Keycloak on swift. A personal agent whose owner
    cannot be resolved yet is dropped from the index entirely — the caller's existing
    "no OpenFGA owner tuple found" branch then correctly skips it as not-yet-importable,
    instead of importing it under a kea sub nobody on swift can look up.
    """
    out: dict[str, str] = {}
    for agent_id, team_id_str in agent_team_index.items():
        if not team_id_str.startswith("personal-"):
            out[agent_id] = team_id_str
            continue
        kea_sub = team_id_str.removeprefix("personal-")
        swift_sub = await resolve_user_sub(kea_sub, username_by_sub, resolver, report)
        if swift_sub is not None:
            out[agent_id] = f"personal-{swift_sub}"
    return out


async def resolve_creator_index(
    agent_creator_index: dict[str, str],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> dict[str, str]:
    """Resolve every kea sub in `_build_agent_creator_index`'s output to its swift sub.

    An unresolved creator is dropped from the index — the caller's `created_by` then
    falls back to `None` (kea's own "team-owned, creator unknown" shape) rather than a
    raw kea sub nobody on swift can look up.
    """
    out: dict[str, str] = {}
    for agent_id, kea_sub in agent_creator_index.items():
        swift_sub = await resolve_user_sub(kea_sub, username_by_sub, resolver, report)
        if swift_sub is not None:
            out[agent_id] = swift_sub
    return out


async def resolve_tag_owner_ids(
    raw_tags: list[dict[str, Any]],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> list[dict[str, Any]]:
    """Resolve personal tag ownership (`owner_id` = a kea user sub) to its swift sub.

    A team-owned tag's `owner_id` is a Keycloak *group* id, never a key in
    `username_by_sub` (which only ever maps *user* subs) — so it passes through
    unchanged with no extra bookkeeping needed to tell the two cases apart. A personal
    tag whose owner cannot be resolved yet is dropped — not imported with a dangling
    `owner_id` nobody on swift can read back; a later re-run picks it up.
    """
    out: list[dict[str, Any]] = []
    for row in raw_tags:
        owner_id = row.get("owner_id")
        if owner_id not in username_by_sub:
            out.append(row)
            continue
        swift_sub = await resolve_user_sub(owner_id, username_by_sub, resolver, report)
        if swift_sub is not None:
            out.append({**row, "owner_id": swift_sub})
    return out


async def resolve_resource_authors(
    raw_resources: list[dict[str, Any]],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> list[dict[str, Any]]:
    """Resolve kea chat-context resource authorship to its swift sub.

    Same rationale as `resolve_tag_owner_ids` — the importer places a chat-context
    resource in `personal-{author}`, so `author` (top-level, or nested in `doc` as a
    fallback — see `importer.py::_import_resource`) must be a swift sub, not kea's.
    An unresolved author is dropped, not imported under a kea sub nobody on swift
    can look up.
    """
    out: list[dict[str, Any]] = []
    for row in raw_resources:
        author = row.get("author") or (row.get("doc") or {}).get("author")
        if author is None or author not in username_by_sub:
            out.append(row)
            continue
        swift_sub = await resolve_user_sub(author, username_by_sub, resolver, report)
        if swift_sub is None:
            continue
        new_row = dict(row)
        if new_row.get("author"):
            new_row["author"] = swift_sub
        else:
            new_row["doc"] = {**(new_row.get("doc") or {}), "author": swift_sub}
        out.append(new_row)
    return out


async def resolve_platform_grants(
    grants: list[tuple[str, RelationType]],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> list[tuple[str, RelationType]]:
    """Resolve each (kea_sub, relation) platform-role grant to its swift sub."""
    out: list[tuple[str, RelationType]] = []
    for kea_sub, relation in grants:
        swift_sub = await resolve_user_sub(kea_sub, username_by_sub, resolver, report)
        if swift_sub is not None:
            out.append((swift_sub, relation))
    return out


async def derive_team_member_relations(
    kea_realm: dict[str, Any] | None,
    group_name_to_team_id: dict[str, str],
    already_elevated: set[tuple[str, str]],
    username_by_sub: dict[str, str],
    resolver: KeaUserResolver,
    report: KeaReconciliationReport,
) -> list[Relation]:
    """Grant `team_member` for every kea Keycloak group membership with no elevated role.

    This is the one Fred concept with no OpenFGA-tuple source on kea (see this module's
    docstring) — its only real source is the realm export's own `users[].groups`.
    `already_elevated` must be the set of (swift_sub, team_id) pairs already receiving
    `team_admin`/`team_editor`/`team_analyst` this run — a user who already has one of
    those never also gets a redundant direct `team_member` tuple (schema.fga derives
    it), matching the rule `importer.py`'s `_effective_team_relations` already applies
    on the `users.json` path.
    """
    relations: list[Relation] = []
    memberships = kea_group_memberships(kea_realm)
    for kea_sub, group_names in memberships.items():
        for group_name in group_names:
            team_id = group_name_to_team_id.get(group_name)
            if team_id is None:
                # A Keycloak group with no matching Fred team (never referenced by any
                # OpenFGA tuple) — not every AD/Keycloak group is a Fred team.
                continue
            swift_sub = await resolve_user_sub(
                kea_sub, username_by_sub, resolver, report
            )
            if swift_sub is None:
                report.team_member_pending += 1
                continue
            if (swift_sub, team_id) in already_elevated:
                continue
            relations.append(
                Relation(
                    subject=RebacReference(Resource.USER, swift_sub),
                    relation=RelationType.TEAM_MEMBER,
                    resource=RebacReference(Resource.TEAM, team_id),
                )
            )
            report.team_member_grants += 1
    return relations


def drop_orphan_teams(
    teams: list[dict[str, Any]],
    known_group_ids: set[str],
    report: KeaReconciliationReport,
) -> list[dict[str, Any]]:
    """Drop any team referenced only by a stray OpenFGA tuple, not by a real kea group.

    `importer.py`'s `_merge_kea_team_rows` builds a team's row from every `team:<id>`
    reference in the OpenFGA tuple dump, falling back to naming an unresolvable one by
    its own id when the realm export has no matching group — that produces a real,
    garbage-named team in swift for a leftover/stale tuple (e.g. from a previous,
    already-wiped test cycle) that no longer corresponds to any Keycloak group.
    Filtering here instead: a team not in the realm export's actual group list, and
    with no name resolved from it, is dropped outright rather than created.
    """
    kept: list[dict[str, Any]] = []
    for row in teams:
        team_id = row["id"]
        if team_id in known_group_ids or row.get("name"):
            kept.append(row)
        else:
            report.orphan_teams_dropped.append(team_id)
    return kept


def drop_orphan_team_relations(
    relations: list[Relation],
    orphan_team_ids: list[str],
) -> list[Relation]:
    """Drop any OpenFGA relation whose subject or resource is a team `drop_orphan_teams`
    already excluded from `teammetadata`.

    `drop_orphan_teams` only filters the DB-row list that becomes `teammetadata` — the
    OpenFGA tuple restore (`transform_kea_tuples` → `resolve_relation_subjects`) is a
    separate list built straight from the bundle's raw tuple dump and was never filtered
    by it. Without this, an orphan team's own tuples (e.g. the `organization:fred`
    grant every team gets) still land in OpenFGA even though the team has no metadata
    row — a dangling `team:<id>` object visible to any reverse OpenFGA lookup but
    invisible to every query that goes through `teammetadata`.
    """
    if not orphan_team_ids:
        return relations
    orphan_ids = set(orphan_team_ids)
    return [
        r
        for r in relations
        if not (r.resource.type == Resource.TEAM and str(r.resource.id) in orphan_ids)
        and not (r.subject.type == Resource.TEAM and str(r.subject.id) in orphan_ids)
    ]


def find_admin_less_teams(
    all_team_ids: set[str],
    resolved_relations: list[Relation],
) -> list[str]:
    """Return every team id in `all_team_ids` that receives zero `team_admin` this run.

    swift's schema.fga treats a team with no `team_admin` as an invariant violated
    everywhere else in the product (bootstrap always seeds one at creation,
    `remove_team_member` refuses to remove the last one) — this import path is the one
    write surface nothing else enforces it on, so it is surfaced loudly here instead of
    silently creating an ungoverned team.
    """
    admined = {
        str(r.resource.id)
        for r in resolved_relations
        if r.relation is RelationType.TEAM_ADMIN
    }
    return sorted(all_team_ids - admined)


# ── Team merge / OpenFGA tuple transform (moved from importer.py 2026-07-28) ──
#
# These were previously defined in importer.py (the permanent executor) and
# re-imported into kea_migration_api.py (the temporary dry-run router) as
# "temporary reuse". Moving them here instead means:
# - importer.py imports FROM this module only, never the reverse — matches
#   this module's own docstring ("nothing outside this file... imports from
#   this module") now literally true, and keeps the deletable surface in one
#   place.
# - `build_kea_reconciliation_plan` below can call them directly without a
#   circular import.


def _realm_group_names(realm: dict[str, Any] | None) -> dict[str, str]:
    """Return group_id → group name from a Keycloak realm export.

    On kea a team's id IS its Keycloak group id, and the group name is the
    only place the team's name exists (kea `teammetadata` has no name column).
    Walks sub-groups too, defensively — kea teams are top-level groups.
    """
    names: dict[str, str] = {}

    def _walk(groups: list[dict[str, Any]]) -> None:
        for group in groups:
            group_id = group.get("id")
            name = group.get("name")
            if isinstance(group_id, str) and isinstance(name, str) and name:
                names[group_id] = name
            _walk(group.get("subGroups") or [])

    _walk((realm or {}).get("groups") or [])
    return names


def _merge_kea_team_rows(
    raw_team_metadata: list[dict[str, Any]],
    tuples: list[dict[str, Any]],
    group_names: dict[str, str],
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Build the full kea team list: every team referenced by tuples, named.

    Kea materialises a `teammetadata` row only when a team was customized
    (description / privacy / banner) — an untouched team exists solely as a
    Keycloak group plus OpenFGA tuples. Swift requires a `teammetadata` row
    (NOT NULL unique `name`) for every team, so this merges:
    - team ids ← every `team:<id>` reference in the tuple dump (excluding the
      kea shared personal team and swift-style personal ids),
    - customization ← the kea `teammetadata` row when present,
    - name ← the realm export's group name; falls back to the id (warned)
      when the bundle has no realm export or the group is gone.
    """
    teams: dict[str, dict[str, Any]] = {}
    for t in tuples:
        for ref in (t.get("object", ""), t.get("user", "")):
            if not ref.startswith("team:"):
                continue
            team_id = ref.removeprefix("team:")
            if team_id == _KEA_SHARED_PERSONAL_TEAM_ID or team_id.startswith(
                "personal-"
            ):
                continue
            teams.setdefault(team_id, {"id": team_id})
    for row in raw_team_metadata:
        team_id = row.get("id")
        if not team_id:
            continue
        merged = teams.setdefault(team_id, {})
        merged.update(row)
        merged["id"] = team_id

    unnamed: list[str] = []
    for team_id, row in teams.items():
        realm_name = group_names.get(team_id)
        if realm_name:
            row["name"] = realm_name
        elif not row.get("name"):
            # `_import_team_metadata` falls back to name=id; surface it.
            unnamed.append(team_id)
    if unnamed:
        warnings.append(
            f"{len(unnamed)} team(s) have no name in the bundle (keycloak "
            "realm export missing or group deleted) — they are named by "
            f"their id: {', '.join(sorted(unnamed))}"
        )
    return [teams[team_id] for team_id in sorted(teams)]


def _realm_platform_role_grants(
    realm: dict[str, Any] | None,
) -> tuple[list[tuple[str, RelationType]], list[str]]:
    """Derive swift platform-role grants from a realm export's users, if any.

    Kea platform roles are Keycloak realm roles (`admin`/`editor`/`viewer`)
    carried per-user — present only in a FULL realm export (`kc export
    --users`); a partial-export has no `users[]` and yields nothing here.
    Mapping (AUTHZ target model): `admin` → platform_admin, `viewer` →
    platform_observer, `editor` → dropped (no swift equivalent — returned
    separately for a warning).
    """
    grants: list[tuple[str, RelationType]] = []
    dropped_editors: list[str] = []
    for user in (realm or {}).get("users") or []:
        sub = user.get("id")
        if not isinstance(sub, str) or not sub:
            continue
        roles = set(user.get("realmRoles") or [])
        if "admin" in roles:
            grants.append((sub, RelationType.PLATFORM_ADMIN))
        if "viewer" in roles:
            grants.append((sub, RelationType.PLATFORM_OBSERVER))
        if "editor" in roles:
            dropped_editors.append(user.get("username") or sub)
    return grants, dropped_editors


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


@dataclass
class KeaReconciliationPlan:
    """Pure, deterministic reconciliation output for one kea bundle — the single
    source of truth shared by the dry-run preview (`kea_migration_api.py`) and
    the real import (`importer.py`). Building it performs Keycloak reads (via
    the shared, bulk-prefetched `resolver`) but zero Postgres/OpenFGA writes;
    both callers execute it identically instead of each recomputing their own
    version of the same team-merge/tuple-transform/relation-resolution sequence.
    """

    team_metadata: list[dict[str, Any]]
    resolved_relations: list[Relation]
    realm_platform_grants: list[tuple[str, RelationType]]
    warnings: list[str]
    tuples_dropped_total: int


async def build_kea_reconciliation_plan(
    bundle: KBundle,
    resolver: KeaUserResolver,
    kea_report: KeaReconciliationReport,
) -> KeaReconciliationPlan:
    """Compute team metadata, resolved OpenFGA relations, and platform-role
    grants for one kea bundle — exactly once, called identically by the
    dry-run preview and the real import (previously copy-pasted, sequencing
    and all, between `kea_migration_api.py` and `importer.py`).

    `kea_report` is mutated in place (matched/relinked/pending users,
    orphan-dropped teams, admin-less teams, team-member grant counts) — the
    caller passes the same instance used elsewhere in its own run so every
    identity resolution in the run lands in one report, not scattered across
    several.
    """
    tuples = bundle.openfga_tuples()
    keycloak_realm = bundle.keycloak_realm()
    kea_username_index = kea_username_by_sub(keycloak_realm)
    warnings: list[str] = []

    team_metadata = _merge_kea_team_rows(
        list(bundle.iter_table("teammetadata")),
        tuples,
        _realm_group_names(keycloak_realm),
        warnings,
    )
    team_metadata = drop_orphan_teams(
        team_metadata, kea_known_group_ids(keycloak_realm), kea_report
    )

    resolved_relations: list[Relation] = []
    tuples_dropped_total = 0
    if tuples:
        transform = transform_kea_tuples(tuples)
        tuples_dropped_total = transform.dropped_total
        # A team `drop_orphan_teams` already excluded above must not still
        # get its OpenFGA tuples written.
        transform.relations = drop_orphan_team_relations(
            transform.relations, kea_report.orphan_teams_dropped
        )
        if transform.dropped_non_uuid:
            warnings.append(
                f"{transform.dropped_non_uuid} OpenFGA tuple(s) with a "
                "non-UUID user subject dropped (pre-MIGR-04 username tuples)"
            )
        if transform.dropped_unknown:
            warnings.append(
                f"{transform.dropped_unknown} OpenFGA tuple(s) dropped — no "
                "swift equivalent for: " + ", ".join(sorted(transform.unknown_shapes))
            )

        resolved_relations = await resolve_relation_subjects(
            transform.relations, kea_username_index, resolver, kea_report
        )

    # Team-member derivation and the admin-coverage check both read the realm
    # export, not `tuples` — a bundle with real teammetadata/groups but an
    # empty-or-absent openfga/tuples.json must still run them, or a team gets
    # created with zero relations and `find_admin_less_teams` never fires to
    # say so (the exact "silently created ungoverned" case its own docstring
    # rules out).
    already_elevated = {
        (str(r.subject.id), str(r.resource.id))
        for r in resolved_relations
        if r.relation
        in (
            RelationType.TEAM_ADMIN,
            RelationType.TEAM_EDITOR,
            RelationType.TEAM_ANALYST,
        )
    }
    group_name_to_team_id = {
        row["name"]: row["id"] for row in team_metadata if row.get("name")
    }
    member_relations = await derive_team_member_relations(
        keycloak_realm,
        group_name_to_team_id,
        already_elevated,
        kea_username_index,
        resolver,
        kea_report,
    )
    resolved_relations = resolved_relations + member_relations
    kea_report.admin_less_teams = find_admin_less_teams(
        {row["id"] for row in team_metadata}, resolved_relations
    )

    realm_grants, dropped_editors = _realm_platform_role_grants(keycloak_realm)
    if dropped_editors:
        warnings.append(
            f"kea platform role 'editor' dropped for {len(dropped_editors)} "
            f"user(s) (no swift equivalent): "
            f"{format_usernames_for_warning(dropped_editors)}"
        )
    realm_grants = await resolve_platform_grants(
        realm_grants, kea_username_index, resolver, kea_report
    )

    return KeaReconciliationPlan(
        team_metadata=team_metadata,
        resolved_relations=resolved_relations,
        realm_platform_grants=realm_grants,
        warnings=warnings,
        tuples_dropped_total=tuples_dropped_total,
    )
