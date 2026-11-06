"""Platform candidates never replace the active result until success."""

from __future__ import annotations

import os
from typing import Literal
from uuid import uuid4

import pytest
from fred_sdk.contracts.capability.preparation import PreparationResult, PreparationSpec
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane_backend.capability_preparations.admission import StagedAsset
from control_plane_backend.capability_preparations.platform import (
    reset_platform_selection,
    start_platform_candidate,
)
from control_plane_backend.capability_preparations.schemas import (
    WorkerPreparationResult,
)
from control_plane_backend.capability_preparations.service import publish_worker_result
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
    CapabilityPlatformSelectionRow,
)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.integration_postgres
async def test_platform_candidate_promotion_and_reset_are_fenced() -> None:
    url = os.environ.get("FRED_CAP_PREP_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("Set FRED_CAP_PREP_TEST_POSTGRES_URL for PostgreSQL verification")
    schema = f"cap_prep_platform_{uuid4().hex}"
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
                CapabilityPlatformSelectionRow.__table__,
            ):
                await connection.run_sync(lambda sync, table=table: table.create(sync))
        sessions = async_sessionmaker(engine, expire_on_commit=False)

        async def start() -> CapabilityPreparationRow:
            asset_id = str(uuid4())
            async with sessions() as session:
                async with session.begin():
                    return await start_platform_candidate(
                        session,
                        runtime_id="r",
                        capability_id="example",
                        slot_key="source",
                        spec=PreparationSpec(
                            asset_slots=("source",), rules_version="v1"
                        ),
                        config={"use_vision": False},
                        staged=StagedAsset(
                            id=asset_id,
                            capability_id="example",
                            slot_key="source",
                            filename="source.txt",
                            content_type="text/plain",
                            sha256="a" * 64,
                            size=1,
                            object_key=f"capability-assets/{asset_id}",
                        ),
                    )

        async def complete(
            row: CapabilityPreparationRow,
            *,
            state: Literal["succeeded", "failed"],
        ) -> bool:
            async with sessions() as session:
                async with session.begin():
                    current = await session.get(CapabilityPreparationRow, row.id)
                    assert current is not None
                    if not current.is_current:
                        return await publish_worker_result(
                            session,
                            preparation_id=row.id,
                            completion=WorkerPreparationResult(
                                input_revision=row.input_revision,
                                attempt=1,
                                state="failed",
                                error_code="late",
                            ),
                        )
                    current.state = "running"
                    current.attempts = 1
                    await session.flush()
                    return await publish_worker_result(
                        session,
                        preparation_id=row.id,
                        completion=WorkerPreparationResult(
                            input_revision=row.input_revision,
                            attempt=1,
                            state=state,
                            result=(
                                PreparationResult(
                                    reference=f"capability-results/{row.id}/1/result.json"
                                )
                                if state == "succeeded"
                                else None
                            ),
                            error_code="invalid" if state == "failed" else None,
                        ),
                    )

        async def selection() -> CapabilityPlatformSelectionRow:
            async with sessions() as session:
                row = await session.get(
                    CapabilityPlatformSelectionRow, ("r", "example", "source")
                )
                assert row is not None
                return row

        first = await start()
        assert await complete(first, state="succeeded")
        assert (await selection()).active_preparation_id == first.id

        failed = await start()
        assert (await selection()).active_preparation_id == first.id
        assert await complete(failed, state="failed")
        assert (await selection()).active_preparation_id == first.id

        replacement = await start()
        assert not await complete(failed, state="failed")
        assert await complete(replacement, state="succeeded")
        selected = await selection()
        assert selected.active_preparation_id == replacement.id
        assert selected.candidate_preparation_id is None
        async with sessions() as session:
            old = await session.get(CapabilityPreparationRow, first.id)
            assert old is not None and not old.is_current
            assert old.superseded_at is not None

        async with sessions() as session:
            async with session.begin():
                await reset_platform_selection(
                    session,
                    runtime_id="r",
                    capability_id="example",
                    slot_key="source",
                )
        assert (await selection()).active_preparation_id is None
        assert not await complete(replacement, state="failed")
    finally:
        await engine.dispose()
        with sync_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        sync_engine.dispose()
