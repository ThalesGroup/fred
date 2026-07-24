"""Kea-path import coverage (MIGR-05.04 / MIGR-05.11 / chat-context prompts).

Exercises the importer against bundles shaped exactly like the ones produced
by main's `migration/export_service.py` (verified against a real kea dump,
2026-07-22): manifest WITHOUT `users_schema_version`, kea table file names
(`teammetadata.jsonl`), agents carrying their prompt in
`payload_json.tuning.fields[].default`, chat-context resources with YAML
front-matter, and an unfiltered OpenFGA tuple dump using the kea role names.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from control_plane_backend.agent_instances.store import AgentInstanceStore
from control_plane_backend.import_export.bundle import open_bundle
from control_plane_backend.import_export.importer import (
    MigrationReport,
    run_import,
    transform_kea_tuples,
)
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.models.prompt_models import PromptRow
from fred_core import Relation, RelationType
from fred_core.documents.tag_models import TagRow
from fred_core.models import Base as CoreBase
from fred_core.scheduler import SchedulerBackend
from fred_core.tasks.models import StartMigrationRequest
from fred_core.tasks.service import TaskService
from fred_core.teams.team_metatada_models import TeamMetadataRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

UID_BOB = "8d343657-8f63-4a7b-9d7f-83a2e3459f94"
UID_LIAM = "1e28af93-e676-4596-8087-c550ec7adc38"
TEAM_FREDLAB = "05186d87-139d-4adb-8d6a-95d61d7afdb4"


# ── bundle builder (mirrors main's export format) ─────────────────────────────


def _jsonl(rows: list[dict[str, Any]]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


def _kea_bundle(
    *,
    agents: list[dict[str, Any]] | None = None,
    resources: list[dict[str, Any]] | None = None,
    tags: list[dict[str, Any]] | None = None,
    teammetadata: list[dict[str, Any]] | None = None,
    tuples: list[dict[str, Any]] | None = None,
    realm: dict[str, Any] | None = None,
) -> bytes:
    """Build a kea snapshot zip byte-identical in shape to main's exporter.

    Deliberately omits `users_schema_version` from the manifest and writes the
    team table under its kea file name `teammetadata.jsonl`.
    """
    agents = agents or []
    resources = resources or []
    tags = tags or []
    teammetadata = teammetadata or []
    tuples = tuples or []
    manifest = {
        "format_version": 1,
        "source_platform": "kea",
        "created_at": "2026-07-22T18:06:01+00:00",
        "tables": {
            "tag": len(tags),
            "metadata": 0,
            "resource": len(resources),
            "mcp-server": 0,
            "teammetadata": len(teammetadata),
            "users": 0,
            "agent": len(agents),
        },
        "tuple_count": len(tuples),
        "realm_exported": False,
        "content_keys": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr("postgres/agent.jsonl", _jsonl(agents))
        zf.writestr("postgres/resource.jsonl", _jsonl(resources))
        zf.writestr("postgres/tag.jsonl", _jsonl(tags))
        zf.writestr("postgres/metadata.jsonl", "")
        zf.writestr("postgres/mcp-server.jsonl", "")
        zf.writestr("postgres/teammetadata.jsonl", _jsonl(teammetadata))
        zf.writestr("postgres/users.jsonl", "")
        zf.writestr("openfga/tuples.json", json.dumps(tuples))
        if realm is not None:
            zf.writestr("keycloak/realm.json", json.dumps(realm))
    return buffer.getvalue()


def _kea_agent(
    agent_id: str,
    *,
    name: str,
    definition_ref: str = "v2.react.basic",
    system_prompt: str | None = None,
    prompt_key: str = "system_prompt_template",
    extra_fields: list[dict[str, Any]] | None = None,
    role: str = "General assistant with optional tools",
    description: str = "General-purpose assistant",
    tags: list[str] | None = None,
    agent_type: str = "agent",
) -> dict[str, Any]:
    fields: list[dict[str, Any]] = list(extra_fields or [])
    if system_prompt is not None:
        fields.append({"key": prompt_key, "type": "prompt", "default": system_prompt})
    return {
        "id": agent_id,
        "name": name,
        "payload_json": {
            "id": agent_id,
            "name": name,
            "type": agent_type,
            "enabled": True,
            "definition_ref": definition_ref,
            "tuning": {
                "role": role,
                "description": description,
                "tags": tags or [],
                "fields": fields,
                "mcp_servers": [{"id": "mcp-knowledge-flow-mcp-text"}],
            },
        },
    }


def _chat_context(
    resource_id: str, *, name: str, author: str, body: str
) -> dict[str, Any]:
    content = (
        f"version: v1\nkind: chat-context\nname: {name}\n"
        f"description: {name}\nschema:\n  type: object\n---\n{body}"
    )
    return {
        "resource_id": resource_id,
        "resource_name": name,
        "resource_type": "chat-context",
        "author": author,
        "doc": {
            "id": resource_id,
            "kind": "chat-context",
            "version": "v1",
            "name": name,
            "description": f"{name} description",
            "labels": ["migrated"],
            "author": author,
            "content": content,
            "library_tags": [],
        },
        "created_at": "2026-07-01T10:00:00+00:00",
        "updated_at": "2026-07-02T10:00:00+00:00",
    }


# ── test harness ──────────────────────────────────────────────────────────────


class FakeRebac:
    """Records relations the tuple phase writes; mimics RebacEngine enough."""

    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.relations: list[Relation] = []

    async def add_relation(
        self, relation: Relation, *, actor_uid: str | None = None
    ) -> None:
        self.relations.append(relation)


async def _make_engine(tmp_path: Path, name: str) -> AsyncEngine:
    import control_plane_backend.models.agent_instance_models  # noqa: F401
    import control_plane_backend.models.prompt_models  # noqa: F401
    import fred_core.tasks.orm_models  # noqa: F401

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / name}")
    async with engine.begin() as conn:
        await conn.run_sync(CoreBase.metadata.create_all)
        await conn.run_sync(CPBase.metadata.create_all)
    return engine


async def _import(
    bundle_bytes: bytes, engine: AsyncEngine, rebac: FakeRebac | None = None
) -> MigrationReport:
    # Task events go to a separate SQLite file: with a single shared file, the
    # import's open write transaction blocks the event INSERTs (one writer at
    # a time in SQLite) — a test-harness artifact, not a product concern
    # (production runs on Postgres).
    tasks_engine = create_async_engine(
        f"sqlite+aiosqlite:///{engine.url.database}.tasks"
    )
    try:
        async with tasks_engine.begin() as conn:
            await conn.run_sync(CoreBase.metadata.create_all)
        task_service = TaskService.build(
            engine=tasks_engine, backend=SchedulerBackend.MEMORY
        )
        start = await task_service.start(StartMigrationRequest(), created_by="tester")
        return await run_import(
            bundle=open_bundle(bundle_bytes),
            import_id="imp-kea",
            task_id=start.task_id,
            task_service=task_service,
            engine=engine,
            agent_instance_store=AgentInstanceStore(engine),
            rebac=rebac,  # type: ignore[arg-type]
        )
    finally:
        await tasks_engine.dispose()


# ── manifest / bundle-format compatibility ────────────────────────────────────


def test_kea_manifest_without_users_schema_version_opens() -> None:
    """Main's exporter predates the field; kea bundles must not be rejected."""
    bundle = open_bundle(_kea_bundle())
    assert bundle.manifest.source_platform == "kea"
    assert bundle.manifest.users_schema_version == 1


def test_swift_manifest_still_requires_users_schema_version() -> None:
    """The kea default must not weaken the swift-native contract (RFC §4)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps({"format_version": 1, "source_platform": "swift"}),
        )
    with pytest.raises(Exception):
        open_bundle(buffer.getvalue())


@pytest.mark.asyncio
async def test_kea_teammetadata_file_name_is_read(tmp_path: Path) -> None:
    """Kea dumps `teammetadata.jsonl`; the team phase must still see the rows."""
    engine = await _make_engine(tmp_path, "teams.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                teammetadata=[
                    {"id": TEAM_FREDLAB, "name": "fredlab", "is_private": True}
                ]
            ),
            engine,
        )
        assert report.teams_imported == 1
        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(engine)() as session:
            row = (
                await session.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.id == TEAM_FREDLAB)
                )
            ).scalar_one()
            assert row.name == "fredlab"
            # kea's legacy is_private bool never maps to a joining mode.
            assert row.joining_mode == "request_only"
    finally:
        await engine.dispose()


# ── agents: prompt + tuning transfer (MIGR-05.11) ─────────────────────────────


@pytest.mark.asyncio
async def test_kea_agent_keeps_prompt_and_tuning(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "agents.sqlite3")
    try:
        bundle = _kea_bundle(
            agents=[
                _kea_agent(
                    "agent-bob",
                    name="BobPersoAgent",
                    system_prompt="search in bob perso folders",
                    role="Bob's helper",
                    description="Personal helper for Bob",
                    tags=["perso"],
                )
            ],
            tuples=[
                {
                    "user": f"user:{UID_BOB}",
                    "relation": "owner",
                    "object": "agent:agent-bob",
                }
            ],
        )
        report = await _import(bundle, engine)
        assert report.agents_imported == 1

        record = await AgentInstanceStore(engine).get("agent-bob")
        assert record is not None
        assert str(record.team_id) == f"personal-{UID_BOB}"
        assert record.created_by == UID_BOB
        assert record.description == "Personal helper for Bob"
        assert record.tuning.role == "Bob's helper"
        assert record.tuning.description == "Personal helper for Bob"
        assert record.tuning.tags == ["perso"]
        # The runtime overlays this key onto the template's system prompt.
        assert record.tuning.values["prompts.system"] == "search in bob perso folders"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kea_v1_secondary_prompts_warn(tmp_path: Path) -> None:
    """v1 dotted per-node prompts have no swift field — warn, keep the system one."""
    engine = await _make_engine(tmp_path, "v1.sqlite3")
    try:
        bundle = _kea_bundle(
            agents=[
                _kea_agent(
                    "agent-v1",
                    name="Rico",
                    definition_ref="v2.react.basic",
                    system_prompt="rag system prompt",
                    prompt_key="prompts.system",
                    extra_fields=[
                        {
                            "key": "prompts.grade_documents",
                            "type": "prompt",
                            "default": "grade the documents",
                        }
                    ],
                )
            ],
            tuples=[
                {
                    "user": f"user:{UID_LIAM}",
                    "relation": "owner",
                    "object": "agent:agent-v1",
                }
            ],
        )
        report = await _import(bundle, engine)
        assert report.agents_imported == 1
        record = await AgentInstanceStore(engine).get("agent-v1")
        assert record is not None
        assert record.tuning.values["prompts.system"] == "rag system prompt"
        assert any("prompts.grade_documents" in w for w in report.warnings)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kea_leader_rows_are_skipped(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "leader.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                agents=[_kea_agent("lead-1", name="OldLeader", agent_type="leader")]
            ),
            engine,
        )
        assert report.agents_imported == 0
        assert report.agents_skipped == 1
        assert report.agents_gap == 0
    finally:
        await engine.dispose()


# ── chat contexts → personal prompts ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_context_becomes_personal_prompt(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "prompts.sqlite3")
    try:
        bundle = _kea_bundle(
            resources=[
                _chat_context(
                    "ctx-bob",
                    name="Bob Perso Chat Context",
                    author=UID_BOB,
                    body="speak spanish to bob",
                ),
                {
                    "resource_id": "tpl-1",
                    "resource_name": "SomeTemplate",
                    "resource_type": "template",
                    "author": UID_BOB,
                    "doc": {"content": "irrelevant"},
                },
            ]
        )
        report = await _import(bundle, engine)
        assert report.prompts_imported == 1
        assert report.prompts_skipped == 1
        assert any("kind 'template'" in w for w in report.warnings)

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(engine)() as session:
            row = (
                await session.execute(
                    select(PromptRow).where(PromptRow.prompt_id == "ctx-bob")
                )
            ).scalar_one()
            assert row.team_id == f"personal-{UID_BOB}"
            assert row.name == "Bob Perso Chat Context"
            # Front-matter stripped: only the body is the prompt text.
            assert row.text == "speak spanish to bob"
            assert row.created_by == UID_BOB
            assert row.tags == ["migrated"]

        # Idempotent: re-importing the same bundle skips the existing row.
        rerun = await _import(bundle, engine)
        assert rerun.prompts_imported == 0
        assert rerun.prompts_skipped == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_kea_library_tags_are_not_migrated(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "tags.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                tags=[
                    {"tag_id": "tag-doc", "name": "TEST", "type": "document"},
                    {"tag_id": "tag-ctx", "name": "PERSO", "type": "chat-context"},
                ]
            ),
            engine,
        )
        assert report.tags_imported == 1
        assert any("library tag(s)" in w for w in report.warnings)

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(engine)() as session:
            ids = {
                row.tag_id
                for row in (await session.execute(select(TagRow))).scalars().all()
            }
            assert ids == {"tag-doc"}
    finally:
        await engine.dispose()


# ── teams & platform roles from the Keycloak realm export ────────────────────


@pytest.mark.asyncio
async def test_teams_created_from_realm_groups(tmp_path: Path) -> None:
    """Every tuple-referenced team gets a teammetadata row, named from the
    realm export's groups; a customized team keeps its kea row's fields."""
    engine = await _make_engine(tmp_path, "realm-teams.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                teammetadata=[
                    # Only the customized team has a kea row — and no name.
                    {
                        "id": "team-custom",
                        "description": "Custom team",
                        "is_private": True,
                    }
                ],
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:team-custom",
                    },
                    {
                        "user": f"user:{UID_LIAM}",
                        "relation": "member",
                        "object": "team:team-untouched",
                    },
                    # personal refs must never become teams
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "member",
                        "object": "team:personal",
                    },
                ],
                realm={
                    "groups": [
                        {"id": "team-custom", "name": "fredlab"},
                        {"id": "team-untouched", "name": "northbridge"},
                    ]
                },
            ),
            engine,
        )
        assert report.teams_imported == 2

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(engine)() as session:
            rows = {
                row.id: row
                for row in (await session.execute(select(TeamMetadataRow)))
                .scalars()
                .all()
            }
            assert set(rows) == {"team-custom", "team-untouched"}
            assert rows["team-custom"].name == "fredlab"
            assert rows["team-custom"].description == "Custom team"
            assert rows["team-untouched"].name == "northbridge"
            assert rows["team-untouched"].joining_mode == "request_only"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_teams_without_realm_are_named_by_id(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "noreal.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:team-x",
                    }
                ]
            ),
            engine,
        )
        assert report.teams_imported == 1
        assert any("no name in the bundle" in w for w in report.warnings)

        from fred_core.sql.async_session import make_session_factory

        async with make_session_factory(engine)() as session:
            row = (
                await session.execute(
                    select(TeamMetadataRow).where(TeamMetadataRow.id == "team-x")
                )
            ).scalar_one()
            assert row.name == "team-x"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_platform_roles_from_realm_users(tmp_path: Path) -> None:
    """A full realm export (users[] with realmRoles) re-provisions platform
    roles: admin → platform_admin, viewer → platform_observer, editor dropped."""
    engine = await _make_engine(tmp_path, "realm-roles.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                realm={
                    "groups": [],
                    "users": [
                        {"id": UID_BOB, "username": "bob", "realmRoles": ["admin"]},
                        {"id": UID_LIAM, "username": "liam", "realmRoles": ["viewer"]},
                        {
                            "id": "e5786097-6bdb-4e65-8084-a0470b20a71b",
                            "username": "marc",
                            "realmRoles": ["editor"],
                        },
                    ],
                }
            ),
            engine,
            rebac=rebac,
        )
        written = {_rel_key(r) for r in rebac.relations}
        assert (f"user:{UID_BOB}", "platform_admin", "organization:fred") in written
        assert (f"user:{UID_LIAM}", "platform_observer", "organization:fred") in written
        assert not any("marc" in k[0] for k in written)
        assert report.platform_roles_granted == 2
        assert any("'editor' dropped" in w and "marc" in w for w in report.warnings)
    finally:
        await engine.dispose()


# ── OpenFGA tuple restore (MIGR-05.04) ────────────────────────────────────────


def _rel_key(relation: Relation) -> tuple[str, str, str]:
    return (
        f"{relation.subject.type.value}:{relation.subject.id}",
        relation.relation.value,
        f"{relation.resource.type.value}:{relation.resource.id}",
    )


def test_transform_kea_tuples_role_mapping() -> None:
    result = transform_kea_tuples(
        [
            # kea hierarchical roles: owner also holds manager+member tuples.
            {"user": f"user:{UID_BOB}", "relation": "owner", "object": "team:T1"},
            {"user": f"user:{UID_BOB}", "relation": "manager", "object": "team:T1"},
            {"user": f"user:{UID_BOB}", "relation": "member", "object": "team:T1"},
            {"user": f"user:{UID_LIAM}", "relation": "manager", "object": "team:T1"},
            {"user": f"user:{UID_LIAM}", "relation": "member", "object": "team:T1"},
            {
                "user": "user:75730f40-9e81-49c6-a95a-ec903262a76c",
                "relation": "member",
                "object": "team:T1",
            },
            # dropped shapes:
            {"user": "user:alice", "relation": "manager", "object": "team:T1"},
            {
                "user": f"user:{UID_BOB}",
                "relation": "member",
                "object": "team:personal",
            },
            {
                "user": "organization:fred",
                "relation": "organization",
                "object": "team:personal",
            },
            {"user": "tag:LIB", "relation": "parent", "object": "resource:R1"},
            # replayed 1:1:
            {
                "user": "organization:fred",
                "relation": "organization",
                "object": "team:T1",
            },
            {"user": "tag:LIB", "relation": "parent", "object": "document:D1"},
            {"user": f"user:{UID_BOB}", "relation": "owner", "object": "tag:LIB"},
            {"user": "team:T1", "relation": "owner", "object": "agent:A2"},
        ]
    )
    written = {_rel_key(r) for r in result.relations}
    assert written == {
        (f"user:{UID_BOB}", "team_admin", "team:T1"),
        (f"user:{UID_BOB}", "team_editor", "team:T1"),
        (f"user:{UID_LIAM}", "team_editor", "team:T1"),
        ("user:75730f40-9e81-49c6-a95a-ec903262a76c", "team_member", "team:T1"),
        ("organization:fred", "organization", "team:T1"),
        ("tag:LIB", "parent", "document:D1"),
        (f"user:{UID_BOB}", "owner", "tag:LIB"),
        ("team:T1", "owner", "agent:A2"),
    }
    # No redundant direct team_member next to an elevated role, no analyst ever.
    assert (f"user:{UID_BOB}", "team_member", "team:T1") not in written
    assert not any(r.relation == RelationType.TEAM_ANALYST for r in result.relations)
    assert result.dropped_personal == 2
    assert result.dropped_non_uuid == 1
    assert result.dropped_resource_parent == 1
    assert result.dropped_unknown == 0


@pytest.mark.asyncio
async def test_tuple_phase_writes_transformed_relations(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "tuples.sqlite3")
    try:
        rebac = FakeRebac()
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:T1",
                    },
                    {
                        "user": f"user:{UID_LIAM}",
                        "relation": "member",
                        "object": "team:T1",
                    },
                    {"user": "user:alice", "relation": "member", "object": "team:T1"},
                ]
            ),
            engine,
            rebac=rebac,
        )
        written = {_rel_key(r) for r in rebac.relations}
        assert written == {
            (f"user:{UID_BOB}", "team_admin", "team:T1"),
            (f"user:{UID_BOB}", "team_editor", "team:T1"),
            (f"user:{UID_LIAM}", "team_member", "team:T1"),
        }
        assert report.tuples_written == 3
        assert report.tuples_dropped == 1
        assert any("non-UUID" in w for w in report.warnings)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_tuple_phase_warns_when_rebac_disabled(tmp_path: Path) -> None:
    engine = await _make_engine(tmp_path, "norebac.sqlite3")
    try:
        report = await _import(
            _kea_bundle(
                tuples=[
                    {
                        "user": f"user:{UID_BOB}",
                        "relation": "owner",
                        "object": "team:T1",
                    }
                ]
            ),
            engine,
            rebac=None,
        )
        assert report.tuples_written == 0
        assert any("NOT restored" in w for w in report.warnings)
    finally:
        await engine.dispose()
