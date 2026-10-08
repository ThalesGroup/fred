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
"""Platform UI theme settings: store round-trip, request validation, the
platform-admin gate, and exposure on the public `/frontend/config`."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
from control_plane_backend.app.dependencies import get_application_container_from_app
from control_plane_backend.main import create_app
from control_plane_backend.models.base import Base as CPBase
from control_plane_backend.platform_ui_settings.schemas import (
    SetPlatformUiSettingsRequest,
)
from control_plane_backend.platform_ui_settings.service import (
    get_platform_ui_settings,
    set_platform_ui_settings,
)
from control_plane_backend.platform_ui_settings.store import PlatformUiSettingsStore
from control_plane_backend.product import service as product_service
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fred_core import AuthorizationError, KeycloakUser, PlatformPermission
from fred_core.security.models import Resource
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    # Without it create_app() reads the developer's config/.env (prod config).
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


@pytest_asyncio.fixture
async def store(control_plane_sql_engine: AsyncEngine) -> PlatformUiSettingsStore:
    return PlatformUiSettingsStore(control_plane_sql_engine)


@pytest.mark.asyncio
async def test_store_is_empty_until_saved(store: PlatformUiSettingsStore) -> None:
    assert await store.get() is None


@pytest.mark.asyncio
async def test_store_round_trips_and_overwrites_the_single_row(
    store: PlatformUiSettingsStore,
) -> None:
    await store.set(default_theme="cobalt", hidden_themes=["cloud"], updated_by="a")
    second = await store.set(default_theme=None, hidden_themes=[], updated_by="b")

    stored = await store.get()
    assert stored is not None
    assert (stored.default_theme, stored.hidden_themes, stored.updated_by) == (
        None,
        [],
        "b",
    )
    assert second.updated_at is not None


@pytest.mark.asyncio
async def test_resaving_identical_settings_still_records_the_save(
    store: PlatformUiSettingsStore,
) -> None:
    first = await store.set(default_theme="cloud", hidden_themes=[], updated_by="a")
    second = await store.set(default_theme="cloud", hidden_themes=[], updated_by="a")
    assert first.updated_at is not None and second.updated_at is not None
    assert second.updated_at >= first.updated_at


@pytest.mark.parametrize(
    "payload",
    [
        {"default_theme": "cobalt", "hidden_themes": ["cobalt"]},
        {"hidden_themes": ["cloud", "cloud"]},
        {"default_theme": "Cobalt"},
        {"hidden_themes": ["a" * 33]},
        {"hidden_themes": [f"t{i}" for i in range(33)]},
        {"default_theme": "pebble", "extra": True},
    ],
)
def test_request_rejects_inconsistent_or_malformed_settings(payload: dict) -> None:
    with pytest.raises(ValidationError):
        SetPlatformUiSettingsRequest.model_validate(payload)


def test_request_accepts_ids_the_backend_does_not_know() -> None:
    request = SetPlatformUiSettingsRequest.model_validate(
        {"default_theme": "aurora", "hidden_themes": ["pebble"]}
    )
    assert request.default_theme == "aurora"


class _RoleRebac:
    def __init__(self, *allowed: PlatformPermission) -> None:
        self._allowed = set(allowed)

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        if permission not in self._allowed:
            raise AuthorizationError(
                user.uid, str(permission), Resource.PLATFORM, "denied"
            )


class _MemoryStore:
    def __init__(self) -> None:
        self.writes = 0

    async def get(self):
        return None

    async def set(self, *, default_theme, hidden_themes, updated_by):
        self.writes += 1
        return SimpleNamespace(
            default_theme=default_theme,
            hidden_themes=hidden_themes,
            updated_by=updated_by,
            updated_at=None,
        )


def _deps(rebac: _RoleRebac, store: _MemoryStore) -> ProductServiceDependencies:
    fake = SimpleNamespace(
        get_platform_ui_settings_store=lambda: store,
        team_dependencies=SimpleNamespace(rebac=rebac),
    )
    return cast(ProductServiceDependencies, fake)


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u", username="u", roles=[], email=None)


@pytest.mark.asyncio
async def test_non_admin_can_neither_read_nor_write() -> None:
    store = _MemoryStore()
    deps = _deps(_RoleRebac(PlatformPermission.CAN_EDIT_PLATFORM_PROMPT), store)
    with pytest.raises(AuthorizationError):
        await get_platform_ui_settings(user=_user(), deps=deps)
    with pytest.raises(AuthorizationError):
        await set_platform_ui_settings(
            user=_user(),
            request=SetPlatformUiSettingsRequest(default_theme="cobalt"),
            deps=deps,
        )
    assert store.writes == 0


@pytest.mark.asyncio
async def test_platform_admin_reads_defaults_then_writes() -> None:
    store = _MemoryStore()
    deps = _deps(_RoleRebac(PlatformPermission.CAN_MANAGE_PLATFORM), store)

    unset = await get_platform_ui_settings(user=_user(), deps=deps)
    assert (unset.default_theme, unset.hidden_themes, unset.updated_at) == (
        None,
        [],
        None,
    )

    saved = await set_platform_ui_settings(
        user=_user(),
        request=SetPlatformUiSettingsRequest(
            default_theme="cobalt", hidden_themes=["pebble"]
        ),
        deps=deps,
    )
    assert (saved.default_theme, saved.hidden_themes, saved.updated_by) == (
        "cobalt",
        ["pebble"],
        "u",
    )


async def _frontend_config(tmp_path: Path, saved: dict | None) -> dict:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'ui.sqlite3'}")
    async with engine.begin() as conn:
        await conn.run_sync(CPBase.metadata.create_all)
    try:
        store = PlatformUiSettingsStore(engine)
        if saved is not None:
            await store.set(updated_by="admin", **saved)
        app = create_app()
        container = get_application_container_from_app(app)
        container.get_platform_ui_settings_store = lambda: store  # type: ignore[method-assign]
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/control-plane/v1/frontend/config")
        assert resp.status_code == 200
        return resp.json()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_public_config_omits_ui_themes_when_never_saved(tmp_path: Path) -> None:
    assert "ui_themes" not in await _frontend_config(tmp_path, None)


@pytest.mark.asyncio
async def test_public_config_omits_a_null_default_theme(tmp_path: Path) -> None:
    payload = await _frontend_config(
        tmp_path, {"default_theme": None, "hidden_themes": ["pebble"]}
    )
    assert payload["ui_themes"] == {"hidden_themes": ["pebble"]}


@pytest.mark.asyncio
async def test_public_config_exposes_saved_ui_themes_without_auth(
    tmp_path: Path,
) -> None:
    payload = await _frontend_config(
        tmp_path, {"default_theme": "cobalt", "hidden_themes": ["pebble"]}
    )
    assert payload["ui_themes"] == {
        "default_theme": "cobalt",
        "hidden_themes": ["pebble"],
    }


@pytest.mark.asyncio
async def test_public_config_survives_an_unavailable_settings_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing table (migration not run) must not take the login page down."""

    class _BrokenStore:
        async def get(self):
            raise RuntimeError("no such table: platform_ui_settings")

    # The app's logging setup does not propagate to caplog; watch the logger itself.
    warnings: list[str] = []
    monkeypatch.setattr(
        product_service.logger,
        "warning",
        lambda msg, *args, **kwargs: warnings.append(msg % args),
    )
    monkeypatch.setattr(product_service, "_ui_settings_failure_logged", set())
    app = create_app()
    container = get_application_container_from_app(app)
    container.get_platform_ui_settings_store = lambda: _BrokenStore()  # type: ignore[method-assign]
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/frontend/config")
        again = await client.get("/control-plane/v1/frontend/config")
    assert resp.status_code == 200 and again.status_code == 200
    assert "ui_themes" not in resp.json()
    # Public endpoint, hit on every page load: one warning per outage.
    assert [w for w in warnings if "UI settings unavailable" in w] == [
        "[frontend-config] platform UI settings unavailable: "
        "RuntimeError: no such table: platform_ui_settings"
    ]
