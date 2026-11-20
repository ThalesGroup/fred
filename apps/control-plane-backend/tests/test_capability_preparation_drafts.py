# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""A selected template starts work before its agent exists."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from control_plane_backend.capability_preparations import draft_api, drafts
from control_plane_backend.capability_preparations.admission import (
    StagedAsset,
    persist_agent_preparations,
)
from control_plane_backend.capability_preparations.drafts import (
    adopt_draft,
    create_draft,
    draft_status,
)
from control_plane_backend.capability_preparations.schemas import (
    WorkerPreparationResult,
)
from control_plane_backend.capability_preparations.service import (
    claim_cleanup,
    get_worker_work,
    publish_worker_result,
)
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.capability_preparation_models import (
    CapabilityAssetRow,
    CapabilityPreparationAssetRow,
    CapabilityPreparationRow,
)
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fastapi import HTTPException, Request, UploadFile
from fred_core import KeycloakUser
from fred_core.common import TeamId
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import AssetSlot
from fred_sdk.contracts.capability.preparation import PreparationResult, PreparationSpec
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def _entry() -> CapabilityCatalogEntry:
    return CapabilityCatalogEntry(
        id="ppt_builder",
        version="1",
        name="PowerPoint builder",
        description="Build slides",
        icon="slideshow",
        assets=[AssetSlot(key="template", accepted_types=[".pptx"], max_count=1)],
        preparation=PreparationSpec(
            asset_slots=("template",),
            min_assets=1,
            activation_field="template_sha256",
            config_fields=("template_sha256", "use_vision"),
            rules_version="v1",
            supports_drafts=True,
        ),
    )


@pytest_asyncio.fixture
async def sessions():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        for table in (
            CapabilityAssetRow.__table__,
            CapabilityPreparationRow.__table__,
            CapabilityPreparationAssetRow.__table__,
        ):
            await connection.run_sync(cast(Table, table).create)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _create(sessions, *, state="pending"):
    entry = _entry()
    assert entry.preparation is not None
    staged = StagedAsset(
        id=str(uuid4()),
        capability_id=entry.id,
        slot_key="template",
        filename="deck.pptx",
        content_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        sha256="a" * 64,
        size=123,
        object_key=f"capability-assets/{uuid4()}",
    )
    async with sessions() as session:
        async with session.begin():
            row = await create_draft(
                session,
                team_id="team",
                author_id="author",
                target_id="template:runtime:template",
                group_id=str(uuid4()),
                generation=1,
                runtime_id="runtime",
                capability_id=entry.id,
                spec=entry.preparation,
                validated_config={"template_sha256": "b" * 64, "use_vision": False},
                staged=staged,
            )
            if state == "running":
                row.state = "running"
                row.attempts = 1
            if state == "succeeded":
                row.state = "running"
                row.attempts = 1
                await session.flush()
                accepted = await publish_worker_result(
                    session,
                    preparation_id=row.id,
                    completion=WorkerPreparationResult(
                        input_revision=row.input_revision,
                        attempt=1,
                        state="succeeded",
                        result=PreparationResult(
                            reference=f"capability-results/{row.id}/1/inventory.json",
                            summary="Analysed 4 layouts",
                        ),
                    ),
                )
                assert accepted
        return row.id, staged.id, entry


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["pending", "running", "succeeded"])
async def test_save_adopts_exact_selected_preparation_without_second_job(
    sessions, state
):
    draft_id, asset_id, entry = await _create(sessions, state=state)
    async with sessions() as session:
        async with session.begin():
            status = await draft_status(
                session, await session.get(CapabilityPreparationRow, draft_id)
            )
            assert status.preparation.state == state
            await persist_agent_preparations(
                session,
                owner_id="agent",
                team_id="team",
                runtime_id="runtime",
                available=[entry],
                selected_ids=[entry.id],
                capability_config={
                    entry.id: {
                        "config": {"template_sha256": "b" * 64, "use_vision": False}
                    }
                },
                staged=[],
                draft_ids={entry.id: draft_id},
                draft_author_id="author",
                draft_target_id="template:runtime:template",
            )
        row = await session.get(CapabilityPreparationRow, draft_id)
        asset = await session.get(CapabilityAssetRow, asset_id)
        assert row.owner_kind == asset.owner_kind == "agent"
        assert row.owner_id == asset.owner_id == "agent"
        assert row.state == state
        assert row.id == draft_id
        assert (await session.scalars(select(CapabilityPreparationRow))).all() == [row]
        if state == "succeeded":
            assert (
                row.result_reference
                == f"capability-results/{draft_id}/1/inventory.json"
            )
        if state == "running":
            work = await get_worker_work(session, draft_id)
            assert work is not None and work.owner_kind == "agent"


@pytest.mark.asyncio
async def test_wrong_author_or_settings_cannot_adopt(sessions):
    draft_id, _, entry = await _create(sessions)
    assert entry.preparation is not None
    async with sessions() as session:
        async with session.begin():
            for author, config in (
                ("other", {"template_sha256": "b" * 64, "use_vision": False}),
                ("author", {"template_sha256": "b" * 64, "use_vision": True}),
            ):
                with pytest.raises(ValueError, match="no longer current"):
                    await adopt_draft(
                        session,
                        draft_id=draft_id,
                        team_id="team",
                        author_id=author,
                        target_id="template:runtime:template",
                        agent_id="agent",
                        runtime_id="runtime",
                        capability_id=entry.id,
                        spec=entry.preparation,
                        config=config,
                        previous=None,
                    )
        row = await session.get(CapabilityPreparationRow, draft_id)
        assert row.owner_kind == "draft" and row.is_current


@pytest.mark.asyncio
async def test_replacing_template_counts_retained_draft_storage(sessions, monkeypatch):
    draft_id, _, entry = await _create(sessions)
    assert entry.preparation is not None
    monkeypatch.setattr(drafts, "MAX_AUTHOR_STORED_BYTES", 200)
    async with sessions() as session:
        original = await session.get(CapabilityPreparationRow, draft_id)
        assert original is not None
        group_id = original.owner_id
        await session.rollback()
        with pytest.raises(ValueError, match="Temporary template storage is full"):
            async with session.begin():
                await create_draft(
                    session,
                    team_id="team",
                    author_id="author",
                    target_id="template:runtime:template",
                    group_id=group_id,
                    generation=2,
                    runtime_id="runtime",
                    capability_id=entry.id,
                    spec=entry.preparation,
                    validated_config={"template_sha256": "c" * 64, "use_vision": False},
                    staged=StagedAsset(
                        id=str(uuid4()),
                        capability_id=entry.id,
                        slot_key="template",
                        filename="replacement.pptx",
                        content_type="application/octet-stream",
                        sha256="c" * 64,
                        size=123,
                        object_key=f"capability-assets/{uuid4()}",
                    ),
                )


@pytest.mark.asyncio
async def test_expired_draft_is_fenced_and_claimed_for_cleanup(sessions):
    draft_id, _, entry = await _create(sessions)
    assert entry.preparation is not None
    async with sessions() as session:
        async with session.begin():
            row = await session.get(CapabilityPreparationRow, draft_id)
            row.draft_expires_at = utcnow() - timedelta(seconds=1)
            row.deadline_at = utcnow() - timedelta(seconds=1)
        async with session.begin():
            leases = await claim_cleanup(session, runtime_id="runtime", limit=8)
            assert len(leases) == 1
            assert str(leases[0].preparation_id) == draft_id
            with pytest.raises(ValueError, match="no longer current"):
                await adopt_draft(
                    session,
                    draft_id=draft_id,
                    team_id="team",
                    author_id="author",
                    target_id="template:runtime:template",
                    agent_id="agent",
                    runtime_id="runtime",
                    capability_id=entry.id,
                    spec=entry.preparation,
                    config={"template_sha256": "b" * 64, "use_vision": False},
                    previous=None,
                )


@pytest.mark.asyncio
async def test_upload_route_starts_durable_work_before_agent_save_and_scopes_reads(
    sessions, monkeypatch
):
    entry = _entry()
    source = SimpleNamespace(runtime_id="runtime", base_url="http://runtime")
    monkeypatch.setattr(
        draft_api, "require_team_access", AsyncMock(return_value=TeamId("team"))
    )
    monkeypatch.setattr(
        draft_api, "_target_entry", AsyncMock(return_value=(source, entry))
    )
    monkeypatch.setattr(
        draft_api,
        "_validate_capability_config_via_pod",
        AsyncMock(
            return_value={"config": {"template_sha256": "b" * 64, "use_vision": False}}
        ),
    )

    class MemoryStore:
        def __init__(self):
            self.objects = {}

        def put_object(self, key, stream, *, content_type):
            self.objects[key] = stream.read()

        def delete_object(self, key):
            self.objects.pop(key, None)

    class Upload:
        filename = "deck.pptx"
        content_type = (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

        async def read(self, limit):
            return b"pptx"[:limit]

    store = MemoryStore()
    deps = cast(
        ProductServiceDependencies,
        SimpleNamespace(
            team_dependencies=SimpleNamespace(),
            get_content_store=lambda: store,
            get_sql_session_factory=lambda: sessions,
        ),
    )
    user = cast(KeycloakUser, SimpleNamespace(uid="author"))
    status = await draft_api.post_team_capability_preparation_draft(
        team_id=TeamId("team"),
        deps=deps,
        http_request=cast(Request, SimpleNamespace(headers={})),
        target_kind="template",
        target_id="runtime:template",
        capability_id=entry.id,
        slot_key="template",
        group_id=uuid4(),
        generation=1,
        config_json='{"use_vision": false}',
        file=cast(UploadFile, Upload()),
        user=user,
    )
    assert status.preparation.state == "pending"
    assert status.config["template_sha256"] == "b" * 64
    assert len(store.objects) == 1
    async with sessions() as session:
        work = await session.get(CapabilityPreparationRow, status.draft_id)
        assert work is not None and work.owner_kind == "draft"
    with pytest.raises(HTTPException) as denied:
        await draft_api.get_team_capability_preparation_draft(
            team_id=TeamId("team"),
            draft_id=UUID(status.draft_id),
            deps=deps,
            user=cast(KeycloakUser, SimpleNamespace(uid="other")),
        )
    assert denied.value.status_code == 404
