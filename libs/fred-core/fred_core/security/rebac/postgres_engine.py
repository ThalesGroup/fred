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

"""PostgreSQL-backed implementation of the relationship authorization engine.

Strategy
--------
Tuples are stored in a single ``rebac_tuples`` table.  For each request, all
stored tuples are fetched and merged with the per-request *contextual* tuples
(user group-memberships, org roles) into an in-memory directed graph.  Permission
rules from the fixed OpenFGA schema are then evaluated as Python graph traversal.

Trade-off: O(n) fetch per request.  For typical deployments (< 50 K tuples) this
is < 10 ms.  It is intentionally simple for this experimental branch; a
production version would use targeted recursive CTEs.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import (
    AgentPermission,
    DocumentPermission,
    OrganizationPermission,
    RebacDisabledResult,
    RebacEngine,
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    ResourcePermission,
    TagPermission,
    TeamPermission,
)
from fred_core.security.structure import M2MSecurity, PostgresRebacConfig
from fred_core.sql.async_session import make_session_factory
from fred_core.sql.base_sql import create_async_engine_from_config

logger = logging.getLogger(__name__)

_CREATE_TABLE = text("""
CREATE TABLE IF NOT EXISTS rebac_tuples (
    subject_type VARCHAR(64)  NOT NULL,
    subject_id   VARCHAR(512) NOT NULL,
    relation     VARCHAR(64)  NOT NULL,
    object_type  VARCHAR(64)  NOT NULL,
    object_id    VARCHAR(512) NOT NULL,
    PRIMARY KEY (subject_type, subject_id, relation, object_type, object_id)
)
""")

_CREATE_INDEX = text("""
CREATE INDEX IF NOT EXISTS idx_rebac_by_object
    ON rebac_tuples(object_type, object_id, relation)
""")

# ─────────────────────────────────────────────────────────────────────────────
# In-memory authorization graph
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class _Row:
    st: str  # subject_type
    si: str  # subject_id
    r: str  # relation
    ot: str  # object_type
    oi: str  # object_id


class _Graph:
    """Directed graph for permission evaluation built from stored + contextual tuples."""

    __slots__ = ("_by_obj", "_by_subj", "_all")

    def __init__(self, rows: Iterable[_Row]) -> None:
        by_obj: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
        by_subj: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
        all_: dict[str, set[str]] = defaultdict(set)

        for row in rows:
            by_obj[(row.r, row.ot, row.oi)].add((row.st, row.si))
            by_subj[(row.st, row.si, row.r)].add((row.ot, row.oi))
            all_[row.ot].add(row.oi)
            all_[row.st].add(row.si)

        self._by_obj = by_obj
        self._by_subj = by_subj
        self._all = all_

    def direct(self, st: str, si: str, r: str, ot: str, oi: str) -> bool:
        return (st, si) in self._by_obj.get((r, ot, oi), set())

    def subjects(self, r: str, ot: str, oi: str) -> set[tuple[str, str]]:
        return self._by_obj.get((r, ot, oi), set())

    def objects(self, st: str, si: str, r: str) -> set[tuple[str, str]]:
        return self._by_subj.get((st, si, r), set())

    def all_of_type(self, t: str) -> set[str]:
        return self._all.get(t, set())


def _relation_to_row(rel: Relation) -> _Row:
    return _Row(
        st=rel.subject.type.value,
        si=rel.subject.id,
        r=rel.relation.value,
        ot=rel.resource.type.value,
        oi=rel.resource.id,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Schema-derived permission evaluation
#
# Each function directly encodes the corresponding OpenFGA schema rule.
# Cycle guards (visited sets) prevent infinite recursion through tag parent chains.
# ─────────────────────────────────────────────────────────────────────────────

# ── organization ──────────────────────────────────────────────────────────────


def _org_admin(g: _Graph, u: str, org: str) -> bool:
    return g.direct("user", u, "admin", "organization", org)


def _org_editor(g: _Graph, u: str, org: str) -> bool:
    return g.direct("user", u, "editor", "organization", org) or _org_admin(g, u, org)


def _org_viewer(g: _Graph, u: str, org: str) -> bool:
    return g.direct("user", u, "viewer", "organization", org) or _org_editor(g, u, org)


# ── team ──────────────────────────────────────────────────────────────────────


def _team_owner(g: _Graph, u: str, team: str) -> bool:
    if g.direct("user", u, "owner", "team", team):
        return True
    # admin from organization: owner = [user] or admin from organization
    for st, org in g.subjects("organization", "team", team):
        if st == "organization" and _org_admin(g, u, org):
            return True
    return False


def _team_manager(g: _Graph, u: str, team: str) -> bool:
    return g.direct("user", u, "manager", "team", team) or _team_owner(g, u, team)


def _team_member(g: _Graph, u: str, team: str) -> bool:
    return g.direct("user", u, "member", "team", team) or _team_manager(g, u, team)


def _team_public(g: _Graph, team: str) -> bool:
    # public: [user:*]  — stored as (user:*, public, team:T)
    return g.direct("user", "*", "public", "team", team)


def _team_can_read(g: _Graph, u: str, team: str) -> bool:
    return _team_member(g, u, team) or _team_public(g, team)


# ── agent ─────────────────────────────────────────────────────────────────────


def _agent_owner_teams(g: _Graph, agent: str) -> set[str]:
    return {si for (st, si) in g.subjects("owner", "agent", agent) if st == "team"}


def _agent_read(g: _Graph, u: str, agent: str) -> bool:
    # read: owner or member from owner
    if g.direct("user", u, "owner", "agent", agent):
        return True
    for team in _agent_owner_teams(g, agent):
        if _team_member(g, u, team):
            return True
    return False


def _agent_update(g: _Graph, u: str, agent: str) -> bool:
    # update: owner or can_update_agents from owner
    if g.direct("user", u, "owner", "agent", agent):
        return True
    for team in _agent_owner_teams(g, agent):
        if _team_manager(g, u, team):
            return True
    return False


# ── tag ───────────────────────────────────────────────────────────────────────


def _tag_owner_teams(g: _Graph, tag: str) -> set[str]:
    return {si for (st, si) in g.subjects("owner", "tag", tag) if st == "team"}


def _tag_parents(g: _Graph, tag: str) -> set[str]:
    """Return all direct parent tags of *tag* (stored as (parent, parent, child))."""
    return {si for (st, si) in g.subjects("parent", "tag", tag) if st == "tag"}


def _tag_read(g: _Graph, u: str, tag: str, _vis: set[str] | None = None) -> bool:
    # read: viewer or editor or owner or read from parent or member from owner
    if _vis is None:
        _vis = set()
    if tag in _vis:
        return False
    _vis.add(tag)

    if (
        g.direct("user", u, "viewer", "tag", tag)
        or g.direct("user", u, "editor", "tag", tag)
        or g.direct("user", u, "owner", "tag", tag)
    ):
        return True
    for team in _tag_owner_teams(g, tag):
        if _team_member(g, u, team):
            return True
    for parent in _tag_parents(g, tag):
        if _tag_read(g, u, parent, _vis):
            return True
    return False


def _tag_update(g: _Graph, u: str, tag: str, _vis: set[str] | None = None) -> bool:
    # update: editor or owner or update from parent or can_update_resources from owner
    if _vis is None:
        _vis = set()
    if tag in _vis:
        return False
    _vis.add(tag)

    if g.direct("user", u, "editor", "tag", tag) or g.direct(
        "user", u, "owner", "tag", tag
    ):
        return True
    for team in _tag_owner_teams(g, tag):
        if _team_manager(g, u, team):
            return True
    for parent in _tag_parents(g, tag):
        if _tag_update(g, u, parent, _vis):
            return True
    return False


def _tag_delete(g: _Graph, u: str, tag: str, _vis: set[str] | None = None) -> bool:
    # delete: owner or delete from parent or can_update_resources from owner
    if _vis is None:
        _vis = set()
    if tag in _vis:
        return False
    _vis.add(tag)

    if g.direct("user", u, "owner", "tag", tag):
        return True
    for team in _tag_owner_teams(g, tag):
        if _team_manager(g, u, team):
            return True
    for parent in _tag_parents(g, tag):
        if _tag_delete(g, u, parent, _vis):
            return True
    return False


def _tag_share(g: _Graph, u: str, tag: str, _vis: set[str] | None = None) -> bool:
    # share: owner or share from parent
    if _vis is None:
        _vis = set()
    if tag in _vis:
        return False
    _vis.add(tag)

    if g.direct("user", u, "owner", "tag", tag):
        return True
    for parent in _tag_parents(g, tag):
        if _tag_share(g, u, parent, _vis):
            return True
    return False


# ── document / resource (derive from parent tag) ──────────────────────────────


def _parent_tag(g: _Graph, obj_type: str, obj_id: str) -> str | None:
    for st, si in g.subjects("parent", obj_type, obj_id):
        if st == "tag":
            return si
    return None


# ── dispatch ──────────────────────────────────────────────────────────────────


def _has_permission(g: _Graph, u: str, perm: RebacPermission, rt: str, ri: str) -> bool:
    """Evaluate *perm* for user *u* on resource (*rt*:*ri*) using *g*."""

    if isinstance(perm, TeamPermission):
        match perm:
            case TeamPermission.CAN_READ:
                return _team_can_read(g, u, ri)
            case TeamPermission.CAN_UPDATE_INFO:
                return _team_owner(g, u, ri)
            case TeamPermission.CAN_UPDATE_RESOURCES:
                return _team_manager(g, u, ri)
            case TeamPermission.CAN_UPDATE_AGENTS:
                return _team_manager(g, u, ri)
            case (
                TeamPermission.CAN_ADMINISTER_MEMBERS
                | TeamPermission.CAN_ADMINISTER_MANAGERS
                | TeamPermission.CAN_ADMINISTER_OWNERS
            ):
                return _team_owner(g, u, ri)
            case TeamPermission.CAN_READ_MEMEBERS:
                return _team_member(g, u, ri)
            case TeamPermission.CAN_READ_CONVERSATIONS:
                return _team_member(g, u, ri)

    elif isinstance(perm, TagPermission):
        match perm:
            case TagPermission.READ:
                return _tag_read(g, u, ri)
            case TagPermission.UPDATE:
                return _tag_update(g, u, ri)
            case TagPermission.DELETE:
                return _tag_delete(g, u, ri)
            case TagPermission.SHARE:
                return _tag_share(g, u, ri)
            case TagPermission.OWNER:
                return g.direct("user", u, "owner", "tag", ri)
            case TagPermission.EDITOR:
                return g.direct("user", u, "editor", "tag", ri)
            case TagPermission.VIEWER:
                return g.direct("user", u, "viewer", "tag", ri)

    elif isinstance(perm, DocumentPermission):
        parent = _parent_tag(g, "document", ri)
        if parent is None:
            return False
        match perm:
            case DocumentPermission.READ:
                return _tag_read(g, u, parent)
            case DocumentPermission.UPDATE:
                return _tag_update(g, u, parent)
            case DocumentPermission.DELETE:
                return _tag_update(g, u, parent)

    elif isinstance(perm, ResourcePermission):
        parent = _parent_tag(g, "resource", ri)
        if parent is None:
            return False
        match perm:
            case ResourcePermission.READ:
                return _tag_read(g, u, parent)
            case ResourcePermission.UPDATE:
                return _tag_update(g, u, parent)
            case ResourcePermission.DELETE:
                return _tag_update(g, u, parent)
            case ResourcePermission.SHARE:
                return _tag_share(g, u, parent)

    elif isinstance(perm, AgentPermission):
        match perm:
            case AgentPermission.READ:
                return _agent_read(g, u, ri)
            case AgentPermission.UPDATE:
                return _agent_update(g, u, ri)
            case AgentPermission.DELETE:
                return _agent_update(g, u, ri)
            case AgentPermission.OWNER:
                return g.direct("user", u, "owner", "agent", ri)

    elif isinstance(perm, OrganizationPermission):
        match perm:
            case OrganizationPermission.CAN_EDIT_AGENT_CLASS_PATH:
                return _org_admin(g, u, ri)

    raise ValueError(f"Unsupported permission type: {perm!r}")


# ─────────────────────────────────────────────────────────────────────────────
# PostgresRebacEngine
# ─────────────────────────────────────────────────────────────────────────────


class PostgresRebacEngine(RebacEngine):
    """Evaluates permissions by storing tuples in PostgreSQL and evaluating
    the fixed Fred schema in-process using an in-memory graph per request."""

    def __init__(
        self,
        config: PostgresRebacConfig,
        m2m_security: M2MSecurity,
    ) -> None:
        super().__init__(m2m_security)
        self._config = config
        self._engine: AsyncEngine | None = None
        self._factory: async_sessionmaker[AsyncSession] | None = None
        self._init_lock = asyncio.Lock()

    # ── RebacEngine interface ─────────────────────────────────────────────────

    async def add_relation(self, relation: Relation) -> str | None:
        factory = await self._get_factory()
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "INSERT INTO rebac_tuples"
                        " (subject_type, subject_id, relation, object_type, object_id)"
                        " VALUES (:st, :si, :r, :ot, :oi)"
                        " ON CONFLICT DO NOTHING"
                    ),
                    {
                        "st": relation.subject.type.value,
                        "si": relation.subject.id,
                        "r": relation.relation.value,
                        "ot": relation.resource.type.value,
                        "oi": relation.resource.id,
                    },
                )
        logger.debug("Added relation %s", relation)
        return "consistent"  # Postgres commits are immediately visible

    async def delete_relation(self, relation: Relation) -> str | None:
        factory = await self._get_factory()
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "DELETE FROM rebac_tuples"
                        " WHERE subject_type=:st AND subject_id=:si"
                        "   AND relation=:r"
                        "   AND object_type=:ot AND object_id=:oi"
                    ),
                    {
                        "st": relation.subject.type.value,
                        "si": relation.subject.id,
                        "r": relation.relation.value,
                        "ot": relation.resource.type.value,
                        "oi": relation.resource.id,
                    },
                )
        logger.debug("Deleted relation %s", relation)
        return "consistent"

    async def delete_all_relations_of_reference(
        self, reference: RebacReference
    ) -> str | None:
        factory = await self._get_factory()
        async with factory() as session:
            async with session.begin():
                await session.execute(
                    text(
                        "DELETE FROM rebac_tuples"
                        " WHERE (subject_type=:t AND subject_id=:i)"
                        "    OR (object_type=:t  AND object_id=:i)"
                    ),
                    {"t": reference.type.value, "i": reference.id},
                )
        logger.debug("Deleted all relations of reference %s", reference)
        return "consistent"

    async def list_relations(
        self,
        *,
        resource_type: Resource,
        relation: RelationType,
        subject_type: Resource | None = None,
        consistency_token: str | None = None,
    ) -> list[Relation] | RebacDisabledResult:
        factory = await self._get_factory()
        async with factory() as session:
            if subject_type is not None:
                rows = await session.execute(
                    text(
                        "SELECT subject_type, subject_id, relation, object_type, object_id"
                        " FROM rebac_tuples"
                        " WHERE object_type=:ot AND relation=:r AND subject_type=:st"
                    ),
                    {
                        "ot": resource_type.value,
                        "r": relation.value,
                        "st": subject_type.value,
                    },
                )
            else:
                rows = await session.execute(
                    text(
                        "SELECT subject_type, subject_id, relation, object_type, object_id"
                        " FROM rebac_tuples"
                        " WHERE object_type=:ot AND relation=:r"
                    ),
                    {"ot": resource_type.value, "r": relation.value},
                )
            return [
                Relation(
                    subject=RebacReference(Resource(row[0]), row[1]),
                    relation=RelationType(row[2]),
                    resource=RebacReference(Resource(row[3]), row[4]),
                )
                for row in rows
            ]

    async def lookup_resources(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        g = await self._build_graph(contextual_relations)
        rt = resource_type.value
        u = subject.id
        return [
            RebacReference(resource_type, rid)
            for rid in g.all_of_type(rt)
            if rid != "*" and _has_permission(g, u, permission, rt, rid)
        ]

    async def lookup_subjects(
        self,
        resource: RebacReference,
        relation: RelationType,
        subject_type: Resource,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> list[RebacReference] | RebacDisabledResult:
        g = await self._build_graph(contextual_relations)
        st = subject_type.value
        return [
            RebacReference(subject_type, si)
            for (t, si) in g.subjects(relation.value, resource.type.value, resource.id)
            if t == st and si != "*"
        ]

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Iterable[Relation] | None = None,
        consistency_token: str | None = None,
    ) -> bool:
        g = await self._build_graph(contextual_relations)
        return _has_permission(
            g, subject.id, permission, resource.type.value, resource.id
        )

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
            self._factory = None

    # ── internal ─────────────────────────────────────────────────────────────

    async def _initialize(self) -> None:
        engine = create_async_engine_from_config(self._config.postgres)
        if self._config.create_table_if_needed:
            async with engine.begin() as conn:
                await conn.execute(_CREATE_TABLE)
                await conn.execute(_CREATE_INDEX)
            logger.info("[REBAC][Postgres] rebac_tuples table ready")
        self._engine = engine
        self._factory = make_session_factory(engine)

    async def _get_factory(self) -> async_sessionmaker[AsyncSession]:
        if self._factory is None:
            async with self._init_lock:
                if self._factory is None:
                    await self._initialize()
        return self._factory  # type: ignore[return-value]

    async def _build_graph(
        self, contextual_relations: Iterable[Relation] | None
    ) -> _Graph:
        factory = await self._get_factory()
        async with factory() as session:
            result = await session.execute(
                text(
                    "SELECT subject_type, subject_id, relation, object_type, object_id"
                    " FROM rebac_tuples"
                )
            )
            stored = [
                _Row(st=row[0], si=row[1], r=row[2], ot=row[3], oi=row[4])
                for row in result
            ]

        contextual = [_relation_to_row(rel) for rel in (contextual_relations or [])]
        return _Graph(stored + contextual)
