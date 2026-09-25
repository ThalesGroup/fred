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

"""Platform announcements: authorization, content versioning, validation.

The distinction most of this file exists to pin: `content_version` is the key
each browser stores a dismissal against, so moving it is the only way the
server can bring a closed banner back. It moves when the wording changes and
when a disabled announcement goes back on air — a relaunch is meant to reach
the users who closed the previous run. It stays put on the transitions that
are not a relaunch: turning an announcement off, and re-saving one unchanged.

The second theme is the gate: every administrative operation asks for
`can_manage_platform`, while the delivery route asks for nothing beyond
authentication, because an announcement is content every user is meant to see.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import cast

import pytest
import pytest_asyncio
from control_plane_backend.announcements.schemas import AnnouncementWriteRequest
from control_plane_backend.announcements.service import (
    create_announcement,
    delete_announcement,
    list_active_announcements,
    list_announcements,
    set_announcement_enabled,
    update_announcement,
)
from control_plane_backend.announcements.store import AnnouncementStore
from control_plane_backend.product.dependencies import ProductServiceDependencies
from fastapi import HTTPException
from fred_core import AuthorizationError, KeycloakUser, OrganizationPermission
from fred_core.logs.log_setup import AUDIT_LOGGER_NAME
from fred_core.security.models import Resource
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncEngine


class _RoleRebac:
    """Answers `check_user_permission_or_raise` from a fixed permission set."""

    def __init__(self, *allowed: OrganizationPermission) -> None:
        self._allowed = set(allowed)
        self.asked: list[OrganizationPermission] = []

    async def check_user_permission_or_raise(
        self, user, permission, resource_id, **kwargs
    ) -> None:
        self.asked.append(permission)
        if permission not in self._allowed:
            raise AuthorizationError(
                user.uid, str(permission), Resource.ORGANIZATION, "denied"
            )


def _platform_admin() -> _RoleRebac:
    return _RoleRebac(OrganizationPermission.CAN_MANAGE_PLATFORM)


def _nobody() -> _RoleRebac:
    """Authenticated, holds no organization permission at all."""
    return _RoleRebac()


def _user(uid: str = "admin") -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, roles=[])


def _deps(store: AnnouncementStore, rebac: _RoleRebac) -> ProductServiceDependencies:
    """The two collaborators the announcement service actually touches.

    Cast once here rather than annotating every call site: the service reads
    exactly these two attributes, and a real container would drag in the whole
    product dependency graph for no extra coverage.
    """
    return cast(
        ProductServiceDependencies,
        SimpleNamespace(
            get_announcement_store=lambda: store,
            team_dependencies=SimpleNamespace(rebac=rebac),
        ),
    )


def _write(**overrides) -> AnnouncementWriteRequest:
    payload = {
        "severity": "info",
        "title": {"en": "Title", "fr": "Titre"},
        "description_short": {"en": "Short", "fr": "Court"},
        "description_long": {},
        "enabled": False,
        "dismissible": True,
    }
    payload.update(overrides)
    return AnnouncementWriteRequest(**payload)


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point `create_app()` at the test configuration.

    Without this the loader picks up the developer's `config/.env`, which
    selects `configuration_prod.yaml` and its enabled Prometheus exporter — the
    route tests below then fail to bind its port on any machine already running
    the stack.
    """
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


@pytest_asyncio.fixture
async def store(control_plane_sql_engine: AsyncEngine) -> AnnouncementStore:
    return AnnouncementStore(control_plane_sql_engine)


# ---------------------------------------------------------------------------
# Content versioning — the dismissal key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_editing_text_bumps_the_content_version(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)

    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_write(title={"en": "Reworded", "fr": "Reformulé"}),
        deps=deps,
    )

    assert updated.content_version == created.content_version + 1


@pytest.mark.asyncio
async def test_relaunching_bumps_the_version_so_the_banner_comes_back(
    store: AnnouncementStore,
) -> None:
    # Dismissals live in each browser's storage and the server cannot reach
    # them; expiring the key they hang on is the only lever it has.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)

    enabled = await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=True, deps=deps
    )
    disabled = await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=False, deps=deps
    )
    relaunched = await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=True, deps=deps
    )

    assert (enabled.enabled, disabled.enabled, relaunched.enabled) == (
        True,
        False,
        True,
    )
    assert enabled.content_version == created.content_version + 1
    # Switching it off changes nothing on screen, so it expires no dismissal.
    assert disabled.content_version == enabled.content_version
    assert relaunched.content_version == enabled.content_version + 1


@pytest.mark.asyncio
async def test_re_enabling_an_already_live_announcement_does_not_bump(
    store: AnnouncementStore,
) -> None:
    # Only the off → on transition is a relaunch. A client re-sending the state
    # it already has must not resurrect everyone's dismissed banner.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(
        user=_user(), request=_write(enabled=True), deps=deps
    )

    again = await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=True, deps=deps
    )

    assert again.content_version == created.content_version


@pytest.mark.asyncio
async def test_update_that_only_switches_delivery_off_does_not_bump(
    store: AnnouncementStore,
) -> None:
    # The full-update route carries `enabled` too, so it has to follow the same
    # rule as the toggle: off is not a relaunch.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(
        user=_user(), request=_write(enabled=True), deps=deps
    )

    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_write(enabled=False),
        deps=deps,
    )

    assert updated.enabled is False
    assert updated.content_version == created.content_version


@pytest.mark.asyncio
async def test_update_that_puts_it_back_on_air_bumps_the_version(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)

    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_write(enabled=True),
        deps=deps,
    )

    assert updated.content_version == created.content_version + 1


@pytest.mark.asyncio
async def test_changing_dismissible_bumps_the_version(
    store: AnnouncementStore,
) -> None:
    # `dismissible` changes the banner's controls, so it IS reader-visible.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)

    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_write(dismissible=False),
        deps=deps,
    )

    assert updated.content_version == created.content_version + 1


@pytest.mark.asyncio
async def test_resubmitting_identical_content_does_not_bump_the_version(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)

    updated = await update_announcement(
        user=_user(), announcement_id=created.id, request=_write(), deps=deps
    )

    assert updated.content_version == created.content_version


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_list_returns_only_enabled_announcements(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await create_announcement(user=_user(), request=_write(enabled=False), deps=deps)
    shown = await create_announcement(
        user=_user(), request=_write(enabled=True), deps=deps
    )

    active = await list_active_announcements(deps=deps)

    assert [a.id for a in active] == [shown.id]


@pytest.mark.asyncio
async def test_active_list_asks_for_no_permission(store: AnnouncementStore) -> None:
    # Authentication is the gate; the route's `get_current_user` provides it.
    # A user holding nothing must still receive the banners.
    rebac = _nobody()
    deps = _deps(store, rebac)
    await create_announcement(
        user=_user(), request=_write(enabled=True), deps=_deps(store, _platform_admin())
    )

    active = await list_active_announcements(deps=deps)

    assert len(active) == 1
    assert rebac.asked == []


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_every_admin_operation_asks_for_can_manage_platform(
    store: AnnouncementStore,
) -> None:
    rebac = _platform_admin()
    deps = _deps(store, rebac)
    created = await create_announcement(user=_user(), request=_write(), deps=deps)
    await list_announcements(user=_user(), deps=deps)
    await update_announcement(
        user=_user(), announcement_id=created.id, request=_write(), deps=deps
    )
    await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=True, deps=deps
    )
    await delete_announcement(user=_user(), announcement_id=created.id, deps=deps)

    assert rebac.asked == [OrganizationPermission.CAN_MANAGE_PLATFORM] * 5


@pytest.mark.asyncio
async def test_non_administrator_is_refused_every_mutation(
    store: AnnouncementStore,
) -> None:
    existing = await create_announcement(
        user=_user(), request=_write(), deps=_deps(store, _platform_admin())
    )
    deps = _deps(store, _nobody())

    for call in (
        lambda: list_announcements(user=_user("mallory"), deps=deps),
        lambda: create_announcement(user=_user("mallory"), request=_write(), deps=deps),
        lambda: update_announcement(
            user=_user("mallory"),
            announcement_id=existing.id,
            request=_write(),
            deps=deps,
        ),
        lambda: set_announcement_enabled(
            user=_user("mallory"),
            announcement_id=existing.id,
            enabled=True,
            deps=deps,
        ),
        lambda: delete_announcement(
            user=_user("mallory"), announcement_id=existing.id, deps=deps
        ),
    ):
        with pytest.raises(AuthorizationError):
            await call()

    # And nothing was written behind the refusal.
    still_there = await store.get(existing.id)
    assert still_there is not None
    assert still_there.enabled is False


@pytest.mark.asyncio
async def test_refused_create_persists_nothing(store: AnnouncementStore) -> None:
    deps = _deps(store, _nobody())

    with pytest.raises(AuthorizationError):
        await create_announcement(user=_user("mallory"), request=_write(), deps=deps)

    assert await store.list_all() == []


# ---------------------------------------------------------------------------
# Unknown ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_operations_on_an_unknown_id_report_404(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())

    for call in (
        lambda: update_announcement(
            user=_user(), announcement_id="ghost", request=_write(), deps=deps
        ),
        lambda: set_announcement_enabled(
            user=_user(), announcement_id="ghost", enabled=True, deps=deps
        ),
        lambda: delete_announcement(user=_user(), announcement_id="ghost", deps=deps),
    ):
        with pytest.raises(HTTPException) as exc:
            await call()
        assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_mutations_emit_audit_records(
    store: AnnouncementStore, caplog: pytest.LogCaptureFixture
) -> None:
    deps = _deps(store, _platform_admin())

    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
        created = await create_announcement(user=_user(), request=_write(), deps=deps)
        await update_announcement(
            user=_user(),
            announcement_id=created.id,
            request=_write(title={"en": "New"}),
            deps=deps,
        )
        await set_announcement_enabled(
            user=_user(), announcement_id=created.id, enabled=True, deps=deps
        )
        await delete_announcement(user=_user(), announcement_id=created.id, deps=deps)

    events = [
        record.__dict__.get("audit_event")
        for record in caplog.records
        if record.name == AUDIT_LOGGER_NAME
    ]
    assert events == [
        "platform.announcement.created",
        "platform.announcement.updated",
        "platform.announcement.toggled",
        "platform.announcement.deleted",
    ]


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


def test_short_description_empty_in_every_locale_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _write(description_short={})


def test_whitespace_only_locale_does_not_count_as_authored() -> None:
    # "Present but blank" must not pass for text, or the banner ships an empty
    # line where the French wording should be.
    with pytest.raises(ValidationError):
        _write(description_short={"fr": "   \n "})


def test_blank_locales_are_dropped_from_an_otherwise_valid_map() -> None:
    request = _write(title={"en": "Kept", "fr": "  "})

    assert request.title == {"en": "Kept"}


def test_title_empty_in_every_locale_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _write(title={})


def test_unknown_severity_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _write(severity="tertiary")


def test_long_description_may_be_omitted() -> None:
    assert _write(description_long={}).description_long == {}


def test_over_long_text_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _write(description_short={"en": "x" * 501})


# ---------------------------------------------------------------------------
# The routes themselves
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_route_rejects_an_unauthenticated_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real route, not just the service, must enforce authentication.

    This is the security line the retired deploy-time banner did not have: its
    content rode on the public pre-auth `/frontend/config`. Announcements are
    admin-authored rows and must never be readable without a token.
    """
    from control_plane_backend.main import create_app
    from fred_core.security import oidc
    from httpx import ASGITransport, AsyncClient

    app = create_app()
    # Same ordering trap as the bootstrap route's 401 test: create_app() applies
    # the test config (security.user.enabled=False), so the flip has to happen
    # after it, not before.
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )

    get_application_container_from_app(app).configuration.security.user.enabled = True

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/control-plane/v1/announcements/active")

    assert resp.status_code == 401


def test_every_announcement_route_is_registered() -> None:
    from control_plane_backend.main import create_app

    paths = create_app().openapi()["paths"]

    assert "/control-plane/v1/announcements/active" in paths
    assert "/control-plane/v1/admin/platform/announcements" in paths
    admin_item = paths["/control-plane/v1/admin/platform/announcements"]
    assert set(admin_item) == {"get", "post"}
    by_id = paths["/control-plane/v1/admin/platform/announcements/{announcement_id}"]
    assert set(by_id) == {"put", "delete"}
    toggle = paths[
        "/control-plane/v1/admin/platform/announcements/{announcement_id}/enabled"
    ]
    assert set(toggle) == {"put"}
