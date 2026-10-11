# SPDX-License-Identifier: Apache-2.0
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from control_plane_backend.platform_access import api, service
from fastapi import FastAPI, HTTPException
from fred_core.security.platform_access.access_control import get_platform_access
from fred_core.security.platform_access.models import PlatformAccessLinkRow
from fred_core.teams.team_metatada_models import TeamMetadataRow
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, select
from test_platform_access import access as access_fixture
from test_platform_access import user

access = access_fixture


@pytest_asyncio.fixture
async def history(access, monkeypatch):
    now = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now if tz is not None else now.replace(tzinfo=None)

    monkeypatch.setattr(service, "datetime", Clock)
    actor = user("accepted")
    await service.set_team(access, actor, "demo", False, True)
    rows = []
    async with access.store.mutation() as session:
        session.add(TeamMetadataRow(id="other", name="Other"))
        for index in range(33):
            token = f"{index:043d}"
            row = PlatformAccessLinkRow(
                id=uuid4(),
                team_id="demo" if index < 32 else "other",
                token=token,
                token_hash=hashlib.sha256(token.encode()).hexdigest(),
                note=f"Invitation {index}",
                created_by=actor.uid,
                created_at=now - timedelta(minutes=index),
                expires_at=now if index >= 2 else None,
                revoked_at=now if index >= 18 else None,
                opening_count=index,
            )
            session.add(row)
            rows.append(row.id)
    access.rebac.members[actor.uid] = {"demo"}
    return actor, rows


@pytest.mark.asyncio
async def test_status_filters_cover_full_history_and_priority(access, history):
    actor, rows = history
    all_links = await service.list_links(access, "demo", 25, 25)
    assert (all_links.total, all_links.inactive_count, len(all_links.items)) == (
        32,
        30,
        7,
    )
    active = await service.list_links(access, "demo", 0, 25, "active")
    assert (active.total, active.inactive_count) == (2, 30)
    expired = await service.list_links(access, "demo", 10, 5, "expired")
    assert expired.total == 16 and len(expired.items) == 5
    assert {item.status for item in expired.items} == {"expired"}
    revoked = await service.list_links(access, "demo", 0, 25, "revoked")
    assert revoked.total == 14
    assert {item.id for item in revoked.items} == set(rows[18:32])
    await service.set_team(access, actor, "demo", False, False)
    assert (await service.list_links(access, "demo", 0, 25, "active")).total == 0
    suspended = await service.list_links(access, "demo", 0, 25, "suspended")
    assert suspended.total == 2 and suspended.inactive_count == 30
    assert {item.status for item in suspended.items} == {"suspended"}


@pytest.mark.asyncio
async def test_cleanup_is_team_scoped_and_preserves_valid_suspended_links(
    access, history
):
    actor, rows = history
    await service.set_team(access, actor, "demo", False, False)
    assert await service.delete_inactive_links(access, "demo") == 30
    assert await service.delete_inactive_links(access, "demo") == 0
    remaining = await service.list_links(access, "demo", 0, 25)
    assert {item.id for item in remaining.items} == set(rows[:2])
    assert remaining.inactive_count == 0
    assert (await service.list_links(access, "other", 0, 25)).total == 1
    assert access.rebac.members[actor.uid] == {"demo"}
    async with access.store.read() as session:
        team = await session.scalar(
            select(TeamMetadataRow).where(TeamMetadataRow.id == "demo")
        )
        assert not team.platform_access_free
    await service.set_team(access, actor, "demo", False, True)
    assert {
        item.status for item in (await service.list_links(access, "demo", 0, 25)).items
    } == {"active"}
    assert await service.reveal_link(access, "demo", rows[0]) == f"{0:043d}"
    with pytest.raises(HTTPException) as error:
        await service.preview_link(access, actor, f"{2:043d}", None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_cleanup_rolls_back_database_failure(access, history):
    def reject_commit(connection):
        raise RuntimeError("commit failed")

    event.listen(access.store.engine.sync_engine, "commit", reject_commit)
    try:
        with pytest.raises(HTTPException) as error:
            await service.delete_inactive_links(access, "demo")
        assert error.value.status_code == 503
    finally:
        event.remove(access.store.engine.sync_engine, "commit", reject_commit)
    assert (await service.list_links(access, "demo", 0, 25)).total == 32


@pytest.mark.asyncio
async def test_cleanup_route_and_filter_validation(access, history, monkeypatch):
    actor, _ = history
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_platform_access] = lambda: access
    app.dependency_overrides[api.get_current_user] = lambda: actor
    audit = []
    monkeypatch.setattr(
        api, "emit_audit_log", lambda *args, **kwargs: audit.append((args, kwargs))
    )
    base = "/admin/platform/access/teams/demo/enrollment-links"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get(base, params={"status": "invalid"})).status_code == 422
        response = await client.get(base, params={"status": "revoked", "limit": 1})
        assert (
            response.json()["total"] == 14 and response.json()["inactive_count"] == 30
        )
        response = await client.delete(f"{base}/inactive")
        assert response.status_code == 200 and response.json() == {"deleted_count": 30}
    assert audit[-1] == (
        ("platform.access.links.deleted",),
        {"actor_uid": actor.uid, "team_id": "demo", "deleted_count": 30},
    )
