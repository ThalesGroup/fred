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

"""Notification service and routes: payload validation, best-effort emission,
and a caller who only ever reaches their own notifications."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
from control_plane_backend.app.dependencies import attach_application_container
from control_plane_backend.notifications import api as notifications_api
from control_plane_backend.notifications.schemas import (
    AgentRepublishNeededPayload,
    NotificationType,
    validate_payload,
)
from control_plane_backend.notifications.service import NotificationService
from control_plane_backend.notifications.store import NotificationStore
from fastapi import FastAPI
from fred_core import KeycloakUser, get_current_user
from fred_core.kpi.base_kpi_writer import BaseKPIWriter
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine

_PAYLOAD = AgentRepublishNeededPayload(
    team_id="alpha",
    team_name="Alpha",
    agent_instance_id="agent-1",
    agent_name="Analyst",
    entry_id="e1",
    editor_name="Bob",
)


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[])


class _Kpi:
    def __init__(self) -> None:
        self.counts: list[tuple[str, dict]] = []

    def count(self, name: str, *, dims: dict, actor) -> None:
        self.counts.append((name, dims))


@pytest_asyncio.fixture
async def kpi() -> _Kpi:
    return _Kpi()


@pytest_asyncio.fixture
async def service(
    control_plane_sql_engine: AsyncEngine, kpi: _Kpi
) -> NotificationService:
    return NotificationService(
        NotificationStore(control_plane_sql_engine),
        get_kpi_writer=lambda: cast(BaseKPIWriter, kpi),
    )


async def _notify(service: NotificationService, *recipients: str, group: str = "g1"):
    return await service.notify(
        recipients=list(recipients),
        type=NotificationType.AGENT_REPUBLISH_NEEDED,
        payload=_PAYLOAD,
        group_key=group,
        team_id="alpha",
    )


# --- payloads -------------------------------------------------------------------


def test_payload_validation_refuses_an_unknown_type_and_a_missing_field() -> None:
    with pytest.raises(ValueError):
        validate_payload("agent.unknown", _PAYLOAD)
    incomplete = _PAYLOAD.model_dump()
    del incomplete["editor_name"]
    with pytest.raises(ValidationError):
        validate_payload(NotificationType.AGENT_REPUBLISH_NEEDED, incomplete)
    assert validate_payload(NotificationType.AGENT_REPUBLISH_NEEDED, _PAYLOAD) == (
        _PAYLOAD.model_dump()
    )


# --- emission -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_notify_creates_one_row_per_recipient_and_counts_it(
    service: NotificationService, kpi: _Kpi
) -> None:
    assert await _notify(service, "alice", "dave")

    for uid in ("alice", "dave"):
        page = await service.list_page(_user(uid), limit=50, before=None)
        assert [item.type for item in page.items] == ["agent.republish_needed"]
        assert page.items[0].payload.agent_name == "Analyst"
    assert (
        kpi.counts
        == [
            (
                "notifications.created_total",
                {"notification_type": "agent.republish_needed"},
            )
        ]
        * 2
    )


@pytest.mark.asyncio
async def test_a_failing_store_never_raises_and_logs_ids_only(
    service: NotificationService,
    kpi: _Kpi,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _down(*_args, **_kwargs):
        raise RuntimeError("database down")

    monkeypatch.setattr(service.store, "upsert", _down)
    monkeypatch.setattr(service.store, "resolve", _down)

    with caplog.at_level(logging.WARNING):
        assert not await _notify(service, "alice")
        assert not await service.resolve(
            ["g1"], actor_uid="bob", actor_name="Bob", outcome="republished"
        )

    text = " ".join(record.getMessage() for record in caplog.records)
    assert "g1" in text
    assert "Analyst" not in text and "Bob" not in text
    assert [name for name, _ in kpi.counts] == ["notifications.emit_failed_total"] * 2


@pytest.mark.asyncio
async def test_an_invalid_payload_is_not_raised_to_the_caller(
    service: NotificationService,
) -> None:
    assert not await service.notify(
        recipients=["alice"],
        type=NotificationType.AGENT_MARKETPLACE_REMOVED,
        payload=_PAYLOAD,
        group_key="g1",
    )
    assert (await service.summary(_user("alice"))).unseen_count == 0


@pytest.mark.asyncio
async def test_resolve_removes_the_actors_row_and_names_them_to_the_others(
    service: NotificationService,
) -> None:
    await _notify(service, "alice", "dave")

    await service.resolve(
        ["g1"], actor_uid="alice", actor_name="Alice", outcome="republished"
    )

    assert (await service.list_page(_user("alice"), limit=50, before=None)).items == []
    [other] = (await service.list_page(_user("dave"), limit=50, before=None)).items
    assert other.handled_by_name == "Alice" and other.handled_at is not None


# --- routes ---------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(
    service: NotificationService,
) -> AsyncIterator[tuple[AsyncClient, list[KeycloakUser]]]:
    caller = [_user("alice")]
    app = FastAPI()
    app.include_router(notifications_api.router)
    attach_application_container(
        app,
        SimpleNamespace(get_notification_service=lambda: service),  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_current_user] = lambda: caller[0]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        yield http, caller


@pytest.mark.asyncio
async def test_routes_list_see_read_delete_and_clear(
    service: NotificationService, client
) -> None:
    http, _ = client
    await _notify(service, "alice", group="g1")
    await _notify(service, "alice", group="g2")

    assert (await http.get("/notifications/summary")).json() == {"unseen_count": 2}
    page = (await http.get("/notifications", params={"limit": 1})).json()
    assert len(page["items"]) == 1 and page["next_cursor"]
    newest = page["items"][0]["id"]
    rest = (
        await http.get("/notifications", params={"before": page["next_cursor"]})
    ).json()
    assert len(rest["items"]) == 1 and rest["next_cursor"] is None

    seen = await http.post("/notifications/seen", json={"up_to": newest})
    assert seen.status_code == 200 and seen.json() == {"unseen_count": 0}
    assert (await http.post(f"/notifications/{newest}/read")).status_code == 204
    assert (await http.delete(f"/notifications/{newest}")).status_code == 204
    assert len((await http.get("/notifications")).json()["items"]) == 1
    assert (await http.delete("/notifications")).status_code == 204
    assert (await http.get("/notifications")).json()["items"] == []


@pytest.mark.asyncio
async def test_another_users_notification_answers_404(
    service: NotificationService, client
) -> None:
    http, caller = client
    await _notify(service, "alice")
    [notification] = (
        await service.list_page(_user("alice"), limit=50, before=None)
    ).items

    caller[0] = _user("bob")
    assert (await http.get("/notifications")).json()["items"] == []
    assert (await http.get("/notifications/summary")).json() == {"unseen_count": 0}
    for response in (
        await http.post(f"/notifications/{notification.id}/read"),
        await http.delete(f"/notifications/{notification.id}"),
        await http.post("/notifications/seen", json={"up_to": notification.id}),
    ):
        assert response.status_code == 404
    assert (await http.delete("/notifications")).status_code == 204

    page = await service.list_page(_user("alice"), limit=50, before=None)
    assert [item.read_at for item in page.items] == [None]


@pytest.mark.asyncio
async def test_a_malformed_cursor_or_limit_answers_422(client) -> None:
    http, _ = client
    assert (await http.get("/notifications", params={"before": "x"})).status_code == 422
    assert (await http.get("/notifications", params={"limit": 51})).status_code == 422


@pytest.mark.asyncio
async def test_notification_routes_reject_an_unauthenticated_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from fred_core.security import oidc

    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    app = create_app()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    get_application_container_from_app(app).configuration.security.user.enabled = True
    base = "/control-plane/v1/notifications"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http:
        responses = [
            await http.get(f"{base}/summary"),
            await http.get(base),
            await http.post(f"{base}/seen", json={"up_to": "x"}),
            await http.post(f"{base}/x/read"),
            await http.delete(f"{base}/x"),
            await http.delete(base),
        ]

    assert [response.status_code for response in responses] == [401] * 6
