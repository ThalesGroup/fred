"""Readiness combines every current gate without erasing other suspensions."""

import os
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fred_core.common import TeamId
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane_backend.agent_instances.store import AgentInstanceRecord
from control_plane_backend.agent_instances.suspension import SuspensionReason
from control_plane_backend.capability_preparations.readiness import _verdict
from control_plane_backend.capability_preparations.readiness import (
    agent_preparation_readiness,
)
from control_plane_backend.capability_preparations.schemas import (
    WorkerPreparationResult,
)
from control_plane_backend.capability_preparations.service import (
    current_agent_results,
    publish_worker_result,
    retire_agent_preparations,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)
from control_plane_backend.product import service


def _record(reason: str | None = None) -> AgentInstanceRecord:
    return AgentInstanceRecord(
        agent_instance_id="a1",
        team_id=TeamId("t1"),
        template_id="r:template",
        source_runtime_id="r",
        source_agent_id="template",
        display_name="Agent",
        description=None,
        enabled=True,
        created_by="user",
        tuning=ManagedAgentTuning(role="Agent", description="Agent"),
        suspension_reason=reason,
    )


def test_multiple_preparations_and_separate_suspension() -> None:
    rows = [
        SimpleNamespace(capability_id="alpha", state="running", error_detail=None),
        SimpleNamespace(
            capability_id="beta", state="failed", error_detail="Template invalid"
        ),
        SimpleNamespace(capability_id="gamma", state="succeeded", error_detail=None),
    ]
    verdict = _verdict(rows)
    assert not verdict.ready
    assert verdict.capability_ids == ("alpha", "beta")
    assert verdict.detail == "Template invalid"
    summary = service._record_to_summary(_record(), preparation_verdict=verdict)
    assert summary.suspension_reason == SuspensionReason.CAPABILITY_PENDING
    assert summary.suspension_detail == "Template invalid"
    suspended = service._record_to_summary(
        _record(SuspensionReason.CAPABILITY_ACCESS_REVOKED.value),
        preparation_verdict=verdict,
    )
    assert suspended.suspension_reason == SuspensionReason.CAPABILITY_ACCESS_REVOKED
    assert suspended.suspension_detail is None
    assert _verdict(rows[2:]).ready


@pytest.mark.asyncio
async def test_turn_admission_refuses_current_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _record()
    deps = SimpleNamespace(
        get_agent_instance_store=lambda: SimpleNamespace(
            get_for_team=AsyncMock(return_value=record)
        ),
    )
    monkeypatch.setattr(
        service,
        "_preparation_verdicts",
        AsyncMock(
            return_value={
                record.agent_instance_id: _verdict(
                    [
                        SimpleNamespace(
                            capability_id="alpha", state="running", error_detail=None
                        )
                    ]
                )
            }
        ),
    )
    with pytest.raises(service.ExecutionPreparationError, match="alpha") as error:
        await service.prepare_execution(
            user=SimpleNamespace(uid="user"),
            team_id=TeamId("t1"),
            agent_instance_id="a1",
            deps=deps,
        )
    assert error.value.http_status == 409


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_batch_readiness_uses_only_current_team_gates() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_readiness_{uuid4().hex}"
    sync_engine = create_engine(url)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(CapabilityPreparationRow.__table__.create)
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        now = utcnow()
        async with sessions() as session:
            async with session.begin():
                for owner_id, team_id, cap_id, state, current, gate in [
                    ("a1", "t1", "alpha", "running", True, True),
                    ("a1", "t1", "beta", "failed", True, True),
                    ("a1", "t1", "gamma", "failed", False, True),
                    ("a2", "t1", "delta", "failed", True, False),
                    ("a3", "t2", "epsilon", "failed", True, True),
                    ("a4", "t1", "zeta", "succeeded", True, True),
                ]:
                    preparation_id = str(uuid4())
                    session.add(
                        CapabilityPreparationRow(
                            id=preparation_id,
                            owner_kind="agent",
                            owner_id=owner_id,
                            team_id=team_id,
                            runtime_id="r",
                            capability_id=cap_id,
                            input_revision=str(uuid4()),
                            rules_version="v1",
                            config_json={},
                            gates_readiness=gate,
                            is_current=current,
                            state=state,
                            max_attempts=3,
                            deadline_at=now + timedelta(minutes=5),
                            workflow_id=f"capability-preparation/{preparation_id}",
                            task_queue="capability-preparation-r",
                            error_detail="Invalid slide" if cap_id == "beta" else None,
                            result_reference=(
                                f"capability-results/{preparation_id}/1/result.json"
                                if cap_id == "zeta"
                                else None
                            ),
                        )
                    )
        async with sessions() as session:
            verdicts = await agent_preparation_readiness(
                session,
                team_id="t1",
                agent_instance_ids=["a1", "a2", "a3"],
            )
        assert verdicts["a1"].capability_ids == ("alpha", "beta")
        assert verdicts["a1"].detail == "Invalid slide"
        assert "a2" not in verdicts
        assert "a3" not in verdicts
        async with sessions() as session:
            assert (
                await current_agent_results(
                    session, agent_instance_id="a4", team_id="t1"
                )
            )["zeta"].endswith("/result.json")
            assert (
                await current_agent_results(
                    session, agent_instance_id="a4", team_id="t2"
                )
                == {}
            )
        async with sessions() as session:
            async with session.begin():
                running = await session.scalar(
                    select(CapabilityPreparationRow).where(
                        CapabilityPreparationRow.owner_id == "a1",
                        CapabilityPreparationRow.capability_id == "alpha",
                    )
                )
                assert running is not None
                running.attempts = 1
                await session.flush()
                await retire_agent_preparations(
                    session, team_id="t1", agent_instance_ids=["a1"]
                )
                assert not await publish_worker_result(
                    session,
                    preparation_id=running.id,
                    completion=WorkerPreparationResult(
                        input_revision=running.input_revision,
                        attempt=1,
                        state="failed",
                        error_code="late_completion",
                    ),
                )
        async with sessions() as session:
            assert not await agent_preparation_readiness(
                session, team_id="t1", agent_instance_ids=["a1"]
            )
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()
