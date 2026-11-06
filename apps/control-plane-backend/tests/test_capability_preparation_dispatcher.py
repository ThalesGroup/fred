"""Durable dispatch claims and uncertain Temporal delivery."""

from __future__ import annotations

import os
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from temporalio.exceptions import WorkflowAlreadyStartedError

from control_plane_backend.capability_preparations import dispatcher
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityPreparationRow,
)


@pytest.mark.asyncio
async def test_uncertain_start_reconciles_existing_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delivery = dispatcher.Delivery(
        preparation_id=str(uuid4()),
        workflow_id="capability-preparation/test",
        task_queue="capability-preparation-fred-agents",
        deadline_at=utcnow() + timedelta(minutes=1),
        claim_id=str(uuid4()),
        dispatch_attempts=1,
    )
    handle = SimpleNamespace(
        describe=AsyncMock(
            return_value=SimpleNamespace(
                run_id="run-1", status=SimpleNamespace(name="RUNNING")
            )
        )
    )
    client = cast(
        Any,
        SimpleNamespace(
            start_workflow=AsyncMock(
                side_effect=WorkflowAlreadyStartedError(
                    delivery.workflow_id, "CapabilityPreparationWorkflow"
                )
            ),
            get_workflow_handle=lambda _id: handle,
        ),
    )
    finish = AsyncMock()
    monkeypatch.setattr(dispatcher, "finish_delivery", finish)
    await dispatcher._deliver(client, cast(Any, object()), delivery)
    finish.assert_awaited_once()
    assert finish.await_args.kwargs == {
        "run_id": "run-1",
        "terminal_without_result": False,
    }


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_claim_survives_dispatcher_crash_and_fences_stale_owner() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_dispatch_{uuid4().hex}"
    sync_engine = create_engine(url)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: CapabilityPreparationRow.__table__.create(sync)
            )
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        preparation_id = str(uuid4())
        async with sessions() as session:
            async with session.begin():
                session.add(
                    CapabilityPreparationRow(
                        id=preparation_id,
                        owner_kind="agent",
                        owner_id="a1",
                        team_id="t1",
                        runtime_id="fred-agents",
                        capability_id="example",
                        input_revision=str(uuid4()),
                        rules_version="v1",
                        config_json={},
                        gates_readiness=True,
                        is_current=True,
                        state="pending",
                        attempts=0,
                        max_attempts=3,
                        deadline_at=utcnow() + timedelta(minutes=5),
                        workflow_id=f"capability-preparation/{preparation_id}",
                        task_queue="capability-preparation-fred-agents",
                    )
                )
        first = await dispatcher.claim_due(sessions)
        assert len(first) == 1
        assert await dispatcher.claim_due(sessions) == []
        async with sessions() as session:
            async with session.begin():
                row = await session.get(CapabilityPreparationRow, preparation_id)
                assert row is not None
                row.dispatch_until = utcnow() - timedelta(seconds=1)
        second = await dispatcher.claim_due(sessions)
        assert len(second) == 1
        assert second[0].workflow_id == first[0].workflow_id
        await dispatcher.finish_delivery(sessions, first[0], run_id="stale")
        await dispatcher.finish_delivery(sessions, second[0], run_id="run-2")
        async with sessions() as session:
            row = (
                await session.execute(
                    select(CapabilityPreparationRow).where(
                        CapabilityPreparationRow.id == preparation_id
                    )
                )
            ).scalar_one()
            assert row.run_id == "run-2"
            assert row.attempts == 0
            assert row.dispatch_attempts == 2
        expired_id = str(uuid4())
        async with sessions() as session:
            async with session.begin():
                session.add(
                    CapabilityPreparationRow(
                        id=expired_id,
                        owner_kind="agent",
                        owner_id="a2",
                        team_id="t1",
                        runtime_id="fred-agents",
                        capability_id="example",
                        input_revision=str(uuid4()),
                        rules_version="v1",
                        config_json={},
                        gates_readiness=True,
                        is_current=True,
                        state="pending",
                        attempts=0,
                        max_attempts=3,
                        deadline_at=utcnow() - timedelta(seconds=1),
                        workflow_id=f"capability-preparation/{expired_id}",
                        task_queue="capability-preparation-fred-agents",
                    )
                )
        assert await dispatcher.fail_expired(sessions) == 1
        async with sessions() as session:
            expired = await session.get(CapabilityPreparationRow, expired_id)
            assert expired is not None
            assert expired.state == "failed"
            assert expired.error_code == "preparation_deadline_exceeded"
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()
