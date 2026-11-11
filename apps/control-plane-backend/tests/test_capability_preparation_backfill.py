"""Legacy PPT rows import once without losing active agent or platform state."""

# pyright: reportArgumentType=false

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from control_plane_backend.capability_preparations.backfill import (
    LegacyPptAnalysis,
    count_unprepared_ppt_agents,
    import_legacy_builtin_overrides,
    import_legacy_ppt_analysis,
)
from control_plane_backend.capability_preparations.backfill_cli import _run
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPlatformSelectionRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class ContentStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, key, stream, *, content_type):
        self.objects[key] = stream.read()


class Artifacts:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.directories: set[str] = set()

    async def mkdir(self, path):
        self.directories.add(path)

    async def write(self, path, content):
        self.objects[path] = content.encode() if isinstance(content, str) else content


@pytest.mark.asyncio
async def test_backfill_dry_run_reads_legacy_rows_without_destination(
    tmp_path, monkeypatch
) -> None:
    template = b"old presentation"
    database = tmp_path / "legacy.sqlite3"
    runtime_config = tmp_path / "runtime.yaml"
    runtime_config.write_text(
        yaml.safe_dump(
            {
                "app": {"runtime_id": "fred-agents"},
                "storage": {"postgres": {"sqlite_path": str(database)}},
            }
        )
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{database}")
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "CREATE TABLE cap_ppt_builder_analysis ("
                "agent_instance_id TEXT, team_id TEXT, template_sha256 TEXT, "
                "labelling_key TEXT, analysis_version INTEGER, status TEXT, "
                "job_id TEXT, attempts INTEGER, template_pptx BLOB, "
                "inventory_json TEXT, patterns_pdf BLOB, error TEXT, "
                "template_filename TEXT, overrides_json TEXT, "
                "created_at TIMESTAMP, updated_at TIMESTAMP)"
            )
        )
        await connection.execute(
            text(
                "INSERT INTO cap_ppt_builder_analysis VALUES "
                "(:agent, :team, :sha, 'rules', 23, 'succeeded', :job, 1, "
                ":template, '{}', NULL, NULL, 'old.pptx', NULL, :now, :now)"
            ),
            {
                "agent": str(uuid4()),
                "team": "team-1",
                "sha": hashlib.sha256(template).hexdigest(),
                "job": str(uuid4()),
                "template": template,
                "now": datetime.now(timezone.utc),
            },
        )
    await engine.dispose()
    missing_control_plane_config = tmp_path / "missing.yaml"
    monkeypatch.setenv("CONFIG_FILE", str(missing_control_plane_config))
    counts = await _run(
        SimpleNamespace(
            control_plane_config=missing_control_plane_config,
            control_plane_env=None,
            runtime_config=runtime_config,
            rules_version="23",
            dry_run=True,
        )
    )
    assert counts == {"total": 1, "legacy_succeeded": 1}
    assert not missing_control_plane_config.exists()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_backfill_preserves_agent_and_platform_results() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_backfill_{uuid4().hex}"
    sync_engine = create_engine(url)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        async with engine.begin() as connection:
            for table in (
                AgentInstanceRow.__table__,
                CapabilityAssetRow.__table__,
                CapabilityPreparationRow.__table__,
                CapabilityPreparationAssetRow.__table__,
                CapabilityPlatformSelectionRow.__table__,
            ):
                await connection.run_sync(lambda sync, table=table: table.create(sync))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        template = b"old presentation"
        sha = hashlib.sha256(template).hexdigest()
        now = datetime.now(timezone.utc)
        agent_id = str(uuid4())
        legacy = LegacyPptAnalysis(
            agent_instance_id=agent_id,
            team_id="team-1",
            template_sha256=sha,
            labelling_key="vision:old-profile",
            analysis_version=23,
            status="succeeded",
            job_id=str(uuid4()),
            attempts=1,
            template_pptx=template,
            inventory_json='{"slide_width":100,"slide_height":100,"patterns":[]}',
            patterns_pdf=b"%PDF",
            error=None,
            template_filename="old.pptx",
            overrides_json=None,
            created_at=now,
            updated_at=now,
        )
        content = ContentStore()
        artifacts = Artifacts()
        async with sessions() as session:
            async with session.begin():
                session.add(
                    AgentInstanceRow(
                        agent_instance_id=agent_id,
                        team_id="team-1",
                        template_id="template-1",
                        source_runtime_id="fred-agents",
                        source_agent_id="agent-1",
                        display_name="Agent",
                        tuning_json=json.dumps(
                            {
                                "role": "Agent",
                                "description": "Agent",
                                "capability_config": {
                                    "ppt_builder": {
                                        "config": {
                                            "template_sha256": sha,
                                            "use_vision": False,
                                        }
                                    }
                                },
                            }
                        ),
                    )
                )
        async with sessions() as session:
            assert (
                await count_unprepared_ppt_agents(
                    session, runtime_id="fred-agents", rules_version="23"
                )
                == 1
            )
        async with sessions() as session:
            async with session.begin():
                with pytest.raises(ValueError, match="outdated"):
                    await import_legacy_ppt_analysis(
                        session,
                        legacy=replace(legacy, analysis_version=22),
                        runtime_id="fred-agents",
                        rules_version="23",
                        content_store=content,
                        artifacts=artifacts,
                    )
        assert content.objects == {}
        async with sessions() as session:
            async with session.begin():
                assert (
                    await import_legacy_ppt_analysis(
                        session,
                        legacy=legacy,
                        runtime_id="fred-agents",
                        rules_version="23",
                        content_store=content,
                        artifacts=artifacts,
                    )
                    == "imported"
                )
        async with sessions() as session:
            async with session.begin():
                assert (
                    await import_legacy_ppt_analysis(
                        session,
                        legacy=legacy,
                        runtime_id="fred-agents",
                        rules_version="23",
                        content_store=content,
                        artifacts=artifacts,
                    )
                    == "existing"
                )
        async with sessions() as session:
            assert (
                await count_unprepared_ppt_agents(
                    session, runtime_id="fred-agents", rules_version="23"
                )
                == 0
            )
            assert (
                await count_unprepared_ppt_agents(
                    session, runtime_id="fred-agents", rules_version="24"
                )
                == 1
            )
        async with sessions() as session:
            async with session.begin():
                agent = await session.get(AgentInstanceRow, agent_id)
                assert agent is not None
                tuning = json.loads(agent.tuning_json)
                tuning["capability_config"]["ppt_builder"]["config"]["use_vision"] = (
                    True
                )
                agent.tuning_json = json.dumps(tuning)
        async with sessions() as session:
            assert (
                await count_unprepared_ppt_agents(
                    session, runtime_id="fred-agents", rules_version="23"
                )
                == 1
            )
        async with sessions() as session:
            row = await session.scalar(
                text(
                    "SELECT config_json FROM capability_preparation "
                    "WHERE owner_id = :owner AND is_current"
                ).bindparams(owner=agent_id)
            )
            assert row["use_vision"] is False
            assert len(content.objects) == 1
            assert len(artifacts.objects) == 3
            assert len(artifacts.directories) == 1

        platform = replace(
            legacy,
            agent_instance_id="__platform__",
            team_id="__platform__",
            overrides_json='[{"pattern_id":"slide:1"}]',
        )
        async with sessions() as session:
            async with session.begin():
                assert (
                    await import_legacy_ppt_analysis(
                        session,
                        legacy=platform,
                        runtime_id="fred-agents",
                        rules_version="23",
                        content_store=content,
                        artifacts=artifacts,
                    )
                    == "imported"
                )
                await import_legacy_builtin_overrides(
                    session,
                    runtime_id="fred-agents",
                    overrides_json='[{"pattern_id":"other"}]',
                )
        async with sessions() as session:
            selection = await session.get(
                CapabilityPlatformSelectionRow,
                ("fred-agents", "ppt_builder", "template"),
            )
            assert selection is not None
            assert selection.active_preparation_id is not None
            assert selection.settings_json["overrides"] == [{"pattern_id": "slide:1"}]
        candidate = replace(
            platform,
            agent_instance_id="__platform_next__",
            status="failed",
            job_id=str(uuid4()),
            inventory_json=None,
            patterns_pdf=None,
            error="unavailable",
            overrides_json=None,
        )
        async with sessions() as session:
            async with session.begin():
                assert (
                    await import_legacy_ppt_analysis(
                        session,
                        legacy=candidate,
                        runtime_id="fred-agents",
                        rules_version="23",
                        content_store=content,
                        artifacts=artifacts,
                    )
                    == "imported"
                )
        async with sessions() as session:
            selection = await session.get(
                CapabilityPlatformSelectionRow,
                ("fred-agents", "ppt_builder", "template"),
            )
            assert selection is not None
            assert selection.active_preparation_id is not None
            assert selection.candidate_preparation_id is not None
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()
