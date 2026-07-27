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
  `transform_kea_tuples` (importer.py) has nothing to translate for them.
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
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fred_core import RebacReference, Relation, RelationType, Resource

from control_plane_backend.users.dependencies import UserServiceDependencies
from control_plane_backend.users.service import (
    find_user_sub_by_username,
    find_user_subs_bulk,
)


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
    """Resolves kea Keycloak subs to swift (S3NS) Keycloak subs, live, by username.

    One instance per run, shared by every call site that needs a username -> sub
    lookup (relation subjects, agent/tag/resource owners, platform-role grants,
    team-membership derivation, and the `users.json` provisioning phase in
    `importer.py`) — never construct a second instance mid-run, or the whole point
    of the shared cache/prefetch below is lost.

    A cutover-scale run (~2000 users) makes this the single biggest latency risk in
    the import: resolving by individual username lookup is one Keycloak Admin API
    call per *distinct* username (bounded further by `resolve_relation_subjects`'s
    own concurrency cap), which is still thousands of round trips. `create()` avoids
    that by listing the whole target realm once (`find_user_subs_bulk`, itself a
    single paginated sweep) and building an in-memory `username -> sub` index —
    every `resolve`/`find_sub` call is then a dict lookup, not a network call. A
    username missing from that snapshot (e.g. created moments ago by
    `_provision_bundle_identities`, or the target realm couldn't be listed at all)
    falls back to one live per-username lookup, memoized so it's never repeated.
    """

    def __init__(
        self,
        user_deps: UserServiceDependencies | None,
        prefetched: dict[str, str] | None = None,
    ) -> None:
        self._user_deps = user_deps
        self._prefetched = prefetched or {}
        self._sub_cache: dict[str, str | None] = {}
        self._cache: dict[str, KeaUserResolution] = {}

    @classmethod
    async def create(
        cls, user_deps: UserServiceDependencies | None
    ) -> "KeaUserResolver":
        """Build a resolver with the target realm's users prefetched in bulk.

        The one recommended construction path for both the real import and the
        dry-run preview (`kea_migration_api.py`) — see the class docstring for why
        a bulk prefetch, not per-username lookups, is what keeps a cutover-scale
        run fast and bounded.
        """
        prefetched = (
            await find_user_subs_bulk(user_deps) if user_deps is not None else {}
        )
        return cls(user_deps, prefetched)

    async def find_sub(self, username: str) -> str | None:
        """Resolve one username to its swift sub — the shared low-level primitive.

        Bulk prefetch first (no I/O), then a memoized fallback lookup (at most one
        real Keycloak call per distinct username never seen in the prefetch,
        across the whole life of this resolver instance).
        """
        prefetched_sub = self._prefetched.get(username)
        if prefetched_sub is not None:
            return prefetched_sub
        if username in self._sub_cache:
            return self._sub_cache[username]
        swift_sub = (
            await find_user_sub_by_username(username, self._user_deps)
            if self._user_deps is not None
            else None
        )
        self._sub_cache[username] = swift_sub
        return swift_sub

    def remember(self, username: str, swift_sub: str) -> None:
        """Record an identity resolvable with zero further I/O this run.

        Called right after `_provision_bundle_identities` creates a Keycloak user —
        without this, the very next phase (`_resolve_bundle_usernames`) would pay
        for a fallback lookup this run already knows the answer to.
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
