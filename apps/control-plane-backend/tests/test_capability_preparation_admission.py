"""Focused admission and transaction checks for reusable preparation."""

from __future__ import annotations

import io
import asyncio
import os
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock
from types import SimpleNamespace
from fred_core import TeamPermission
from fred_core.common import TeamId
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import AssetSlot
from fred_sdk.contracts.capability.preparation import PreparationSpec
from fred_sdk.contracts.capability.preparation import PreparationResult
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane_backend.capability_preparations.admission import (
    StagedAsset,
    persist_agent_preparations,
    stage_assets,
)
from control_plane_backend.capability_preparations.dispatcher import (
    claim_due,
    finish_delivery,
)
from control_plane_backend.capability_preparations.readiness import (
    agent_preparation_readiness,
)
from control_plane_backend.capability_preparations.schemas import (
    WorkerPreparationResult,
)
from control_plane_backend.capability_preparations.service import (
    begin_worker_attempt,
    get_work_asset,
    list_agent_preparations,
    publish_worker_result,
    retry_agent_preparation,
)
from control_plane_backend.agent_instances.store import (
    AgentInstanceRecord,
    AgentInstanceStore,
)
from control_plane_backend.config.models import ManagedAgentTuning
from control_plane_backend.models.agent_instance_models import AgentInstanceRow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)
from control_plane_backend.product import api as product_api


@dataclass
class Upload:
    slot_key: str
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"


class MemoryStore:
    def __init__(self, fail_after: int | None = None) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_after = fail_after

    def put_object(self, key: str, stream: io.BytesIO, *, content_type: str) -> None:
        if self.fail_after is not None and len(self.objects) >= self.fail_after:
            raise OSError("storage outage")
        self.objects[key] = stream.read()

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture(autouse=True)
def direct_store_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    async def direct(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", direct)


def _entry() -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id="example",
        version="1",
        name="example",
        description="example",
        icon="star",
        assets=[AssetSlot(key="source", accepted_types=[".txt"], max_count=2)],
        preparation=PreparationSpec(asset_slots=("source",), rules_version="v1"),
    )


def _second_entry() -> CapabilityCatalogEntry:
    return _entry().model_copy(
        update={
            "id": "reverse",
            "name": "reverse",
            "preparation": PreparationSpec(
                asset_slots=("source",),
                rules_version="v2",
                config_fields=("mode",),
                public_config_fields=("mode",),
            ),
        }
    )


@pytest.mark.asyncio
async def test_multipart_parser_bounds_uploaded_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(product_api, "MAX_CAPABILITY_ASSET_BYTES", 3)

    class Upload:
        filename = "a.txt"
        content_type = "text/plain"

        async def read(self, size: int) -> bytes:
            assert size == 4
            return b"abcd"

    with pytest.raises(HTTPException) as error:
        await product_api._parse_capability_asset_uploads(
            ["example:source"], [Upload()]
        )
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_unauthorized_save_never_parses_or_stores_assets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deny = AsyncMock(side_effect=HTTPException(status_code=403))
    parse = AsyncMock()
    monkeypatch.setattr(product_api, "require_team_access", deny)
    monkeypatch.setattr(product_api, "_parse_capability_asset_uploads", parse)
    await_params = dict(
        team_id=TeamId("t1"),
        deps=SimpleNamespace(team_dependencies=SimpleNamespace()),
        http_request=SimpleNamespace(headers={}),
        request="{}",
        asset_slots=["example:source"],
        asset_files=[],
        user=object(),
    )
    with pytest.raises(HTTPException) as error:
        await product_api.post_team_agent_instance_with_assets(**await_params)
    assert error.value.status_code == 403
    parse.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorized_multipart_save_passes_bounded_asset_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Upload:
        filename = "input.txt"
        content_type = "text/plain"

        async def read(self, size: int) -> bytes:
            assert size == product_api.MAX_CAPABILITY_ASSET_BYTES + 1
            return b"content"

    authorize = AsyncMock(return_value=TeamId("t1"))
    save = AsyncMock(return_value=object())
    monkeypatch.setattr(product_api, "require_team_access", authorize)
    monkeypatch.setattr(product_api, "enroll_agent_instance", save)
    await product_api.post_team_agent_instance_with_assets(
        team_id=TeamId("t1"),
        deps=SimpleNamespace(team_dependencies=SimpleNamespace()),
        http_request=SimpleNamespace(headers={}),
        request='{"template_id":"r:t","display_name":"Agent","usage_statement":"use"}',
        asset_slots=["example:source"],
        asset_files=[Upload()],
        user=object(),
    )
    assert authorize.await_args.kwargs["required_permissions"] == [
        TeamPermission.CAN_UPDATE_AGENTS
    ]
    assert save.await_args.kwargs["asset_uploads"]["example"][0].content == b"content"


@pytest.mark.asyncio
async def test_stage_rejects_undeclared_and_failed_upload_cleans_originals() -> None:
    store = MemoryStore(fail_after=1)
    with pytest.raises(OSError, match="storage outage"):
        await stage_assets(
            store,
            available=[_entry()],
            selected_ids=["example"],
            uploads={
                "example": [
                    Upload("source", "a.txt", b"a"),
                    Upload("source", "b.txt", b"b"),
                ]
            },
        )
    assert store.objects == {}
    with pytest.raises(ValueError, match="unselected"):
        await stage_assets(
            MemoryStore(),
            available=[_entry()],
            selected_ids=[],
            uploads={"example": [Upload("source", "a.txt", b"a")]},
        )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_preparation_intention_is_atomic_and_unchanged_save_reuses_it() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_admission_{uuid4().hex}"
    sync_engine = create_engine(url)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda sync: AgentInstanceRow.__table__.create(sync)
            )
            for table in (
                CapabilityAssetRow.__table__,
                CapabilityPreparationRow.__table__,
                CapabilityPreparationAssetRow.__table__,
            ):
                await connection.run_sync(lambda sync, table=table: table.create(sync))
        async with engine.begin() as connection:
            await connection.execute(
                AgentInstanceRow.__table__.insert().values(
                    agent_instance_id="a1",
                    team_id="t1",
                    template_id="template",
                    source_runtime_id="runtime",
                    source_agent_id="template",
                    display_name="Agent",
                )
            )
        config = {"example": {"config": {"mode": "a"}}}
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        async with sessions() as session:
            async with session.begin():
                await persist_agent_preparations(
                    session,
                    owner_id="a1",
                    team_id="t1",
                    runtime_id="runtime",
                    available=[_entry()],
                    selected_ids=["example"],
                    capability_config=config,
                    staged=[],
                )
        async with sessions() as session:
            async with session.begin():
                await persist_agent_preparations(
                    session,
                    owner_id="a1",
                    team_id="t1",
                    runtime_id="runtime",
                    available=[_entry()],
                    selected_ids=["example"],
                    capability_config=config,
                    staged=[],
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(CapabilityPreparationRow)
                    )
                ) == 1
        for mode in ("b", "a"):
            async with sessions() as session:
                async with session.begin():
                    await persist_agent_preparations(
                        session,
                        owner_id="a1",
                        team_id="t1",
                        runtime_id="runtime",
                        available=[_entry()],
                        selected_ids=["example"],
                        capability_config={"example": {"config": {"mode": mode}}},
                        staged=[],
                    )
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(CapabilityPreparationRow)
                )
            ) == 3
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CapabilityPreparationRow)
                    .where(CapabilityPreparationRow.is_current.is_(True))
                )
            ) == 1
        uploaded = StagedAsset(
            id=str(uuid4()),
            capability_id="example",
            slot_key="source",
            filename="input.txt",
            content_type="text/plain",
            sha256="a" * 64,
            size=1,
            object_key=f"capability-assets/{uuid4()}",
        )
        async with sessions() as session:
            async with session.begin():
                await persist_agent_preparations(
                    session,
                    owner_id="a1",
                    team_id="t1",
                    runtime_id="runtime",
                    available=[_entry()],
                    selected_ids=["example"],
                    capability_config=config,
                    staged=[uploaded],
                )
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(CapabilityAssetRow)
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(CapabilityPreparationAssetRow)
                )
                == 1
            )
            assert (
                await list_agent_preparations(
                    session, agent_instance_id="a1", team_id="t2", limit=32, offset=0
                )
            ).items == []
            assert (
                len(
                    (
                        await list_agent_preparations(
                            session,
                            agent_instance_id="a1",
                            team_id="t1",
                            limit=32,
                            offset=0,
                        )
                    ).items
                )
                == 1
            )
        async with sessions() as session:
            async with session.begin():
                current = (
                    await session.execute(
                        select(CapabilityPreparationRow).where(
                            CapabilityPreparationRow.is_current.is_(True)
                        )
                    )
                ).scalar_one()
                current.state = "failed"
                retry = await retry_agent_preparation(
                    session,
                    agent_instance_id="a1",
                    team_id="t1",
                    capability_id="example",
                )
                assert retry is not None and retry.state == "pending"
                assert retry.preparation_id != current.id
        async with sessions() as session:
            async with session.begin():
                current = (
                    await session.execute(
                        select(CapabilityPreparationRow).where(
                            CapabilityPreparationRow.is_current.is_(True)
                        )
                    )
                ).scalar_one()
                current.state = "running"
                await session.flush()
                work = await begin_worker_attempt(
                    session, preparation_id=current.id, attempt=1
                )
                assert work is not None
                assert work.attempt == 1
                assert (
                    await begin_worker_attempt(
                        session, preparation_id=current.id, attempt=1
                    )
                ) is not None
                assert work.assets[0].asset_id == UUID(uploaded.id)
                assert (
                    await get_work_asset(
                        session, preparation_id=current.id, asset_id=uploaded.id
                    )
                ) is not None
                assert (
                    await get_work_asset(
                        session, preparation_id=current.id, asset_id=str(uuid4())
                    )
                ) is None
                stale = WorkerPreparationResult(
                    input_revision="stale",
                    attempt=1,
                    state="succeeded",
                    result=PreparationResult(
                        reference=f"capability-results/{current.id}/1/result.json"
                    ),
                )
                assert not await publish_worker_result(
                    session, preparation_id=current.id, completion=stale
                )
                complete = stale.model_copy(
                    update={"input_revision": current.input_revision}
                )
                assert await publish_worker_result(
                    session, preparation_id=current.id, completion=complete
                )
                assert not await publish_worker_result(
                    session, preparation_id=current.id, completion=complete
                )
        async with sessions() as session:
            page = await list_agent_preparations(
                session, agent_instance_id="a1", team_id="t1", limit=32, offset=0
            )
            assert complete.result is not None
            assert page.items[0].result_reference == complete.result.reference
            assert page.items[0].assets[0].sha256 == uploaded.sha256
        store = AgentInstanceStore(engine)
        with pytest.raises(ValueError, match="exceeds 128 KiB"):
            async with sessions() as session:
                async with session.begin():
                    await store.create(
                        AgentInstanceRecord(
                            agent_instance_id="a2",
                            team_id=TeamId("t1"),
                            template_id="template",
                            source_runtime_id="runtime",
                            source_agent_id="template",
                            display_name="Another agent",
                            description=None,
                            enabled=True,
                            created_by="user",
                            tuning=ManagedAgentTuning(
                                role="Agent", description="Agent"
                            ),
                        ),
                        session=session,
                    )
                    await persist_agent_preparations(
                        session,
                        owner_id="a2",
                        team_id="t1",
                        runtime_id="runtime",
                        available=[_entry()],
                        selected_ids=["example"],
                        capability_config={
                            "example": {"config": {"large": "x" * (129 * 1024)}}
                        },
                        staged=[],
                    )
        assert await store.get("a2") is None
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_two_capabilities_share_save_dispatch_status_and_readiness() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_multi_{uuid4().hex}"
    sync_engine = create_engine(url)
    with sync_engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_async_engine(
        url, connect_args={"options": f"-c search_path={schema}"}
    )
    try:
        async with engine.begin() as connection:
            for table in (
                CapabilityAssetRow.__table__,
                CapabilityPreparationRow.__table__,
                CapabilityPreparationAssetRow.__table__,
            ):
                await connection.run_sync(lambda sync, table=table: table.create(sync))
        sessions = async_sessionmaker(engine, expire_on_commit=False)
        uploads = {
            cap_id: [Upload("source", f"{cap_id}.txt", cap_id.encode())]
            for cap_id in ("example", "reverse")
        }
        stored = MemoryStore()
        staged = await stage_assets(
            stored,
            available=[_entry(), _second_entry()],
            selected_ids=list(uploads),
            uploads=uploads,
        )
        async with sessions() as session:
            async with session.begin():
                await persist_agent_preparations(
                    session,
                    owner_id="a1",
                    team_id="t1",
                    runtime_id="fred-agents",
                    available=[_entry(), _second_entry()],
                    selected_ids=list(uploads),
                    capability_config={
                        cap_id: {"config": {"mode": cap_id}} for cap_id in uploads
                    },
                    staged=staged,
                )
        async with sessions() as session:
            async with session.begin():
                await persist_agent_preparations(
                    session,
                    owner_id="a1",
                    team_id="t1",
                    runtime_id="fred-agents",
                    available=[_entry(), _second_entry()],
                    selected_ids=list(uploads),
                    capability_config={
                        "example": {"config": {"mode": "example"}},
                        "reverse": {
                            "config": {"mode": "reverse", "display_override": "edited"}
                        },
                    },
                    staged=[],
                )
                assert (
                    await session.scalar(
                        select(func.count()).select_from(CapabilityPreparationRow)
                    )
                ) == 2
        deliveries = await claim_due(sessions)
        assert len(deliveries) == 2
        assert all(
            delivery.task_queue == "capability-preparation-fred-agents"
            for delivery in deliveries
        )
        for delivery in deliveries:
            await finish_delivery(
                sessions, delivery, run_id=f"run-{delivery.preparation_id}"
            )
        async with sessions() as session:
            rows = (
                (
                    await session.execute(
                        select(CapabilityPreparationRow).where(
                            CapabilityPreparationRow.is_current.is_(True)
                        )
                    )
                )
                .scalars()
                .all()
            )
            by_capability = {row.capability_id: row for row in rows}
            assert set(by_capability) == {"example", "reverse"}
            for cap_id, row in by_capability.items():
                assert row.run_id is not None
                work = await get_work_asset(
                    session,
                    preparation_id=row.id,
                    asset_id=next(
                        asset.id for asset in staged if asset.capability_id == cap_id
                    ),
                )
                assert work is not None
            verdict = await agent_preparation_readiness(
                session, team_id="t1", agent_instance_ids=["a1"]
            )
            assert verdict["a1"].capability_ids == ("example", "reverse")
            page = await list_agent_preparations(
                session, agent_instance_id="a1", team_id="t1", limit=20, offset=0
            )
            assert {item.capability_id for item in page.items} == {"example", "reverse"}
            assert next(
                item for item in page.items if item.capability_id == "reverse"
            ).public_config == {"mode": "reverse"}
        async with sessions() as session:
            async with session.begin():
                reverse = await session.get(
                    CapabilityPreparationRow, by_capability["reverse"].id
                )
                assert reverse is not None
                reverse.state = "failed"
                example = await session.get(
                    CapabilityPreparationRow, by_capability["example"].id
                )
                assert example is not None
                example.state = "succeeded"
        async with sessions() as session:
            verdict = await agent_preparation_readiness(
                session, team_id="t1", agent_instance_ids=["a1"]
            )
            assert verdict["a1"].capability_ids == ("reverse",)
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()
