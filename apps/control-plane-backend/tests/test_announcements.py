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
    dismiss_patch_note,
    get_active_patch_note,
    list_activation_history,
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
from sqlalchemy.exc import IntegrityError
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


def _patch_note(**overrides) -> AnnouncementWriteRequest:
    payload = {
        "kind": "patch_note",
        "severity": "info",
        "title": {"en": "What's new in 3.4", "fr": "Nouveautés 3.4"},
        "description_short": {},
        "description_long": {"en": "# Release 3.4\n\nBody", "fr": "## Version 3.4"},
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
async def test_saving_content_never_changes_delivery(
    store: AnnouncementStore,
) -> None:
    # The editor fills `enabled` from the announcement as it was when the
    # dialog opened. Honouring it would let a save land on top of a toggle
    # someone made meanwhile — silently pulling a live banner, or putting one
    # back on air and expiring every dismissal with it.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_write(), deps=deps)
    await set_announcement_enabled(
        user=_user(), announcement_id=created.id, enabled=True, deps=deps
    )

    # A stale snapshot: the editor still believes the announcement is disabled.
    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_write(enabled=False),
        deps=deps,
    )

    assert updated.enabled is True


@pytest.mark.asyncio
async def test_toggle_between_read_and_write_survives_a_content_save(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another admin switches the note on after `update_announcement` read it
    # but before it wrote: the content save must not put the old state back.
    deps = _deps(store, _platform_admin())
    created = await create_announcement(user=_user(), request=_patch_note(), deps=deps)
    original_update = store.update

    async def _toggle_then_update(**kwargs):
        await store.set_enabled(
            announcement_id=created.id,
            enabled=True,
            content_version=created.content_version,
            updated_by="other",
        )
        return await original_update(**kwargs)

    monkeypatch.setattr(store, "update", _toggle_then_update)

    updated = await update_announcement(
        user=_user(),
        announcement_id=created.id,
        request=_patch_note(
            title={"en": "Fixed"}, description_long={"en": "# Fixed typo"}
        ),
        deps=deps,
    )

    assert updated.enabled is True
    assert (await store.get(created.id)).enabled is True  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_a_stale_snapshot_cannot_relaunch_through_the_content_route(
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

    assert updated.enabled is False
    assert updated.content_version == created.content_version


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
    assert set(paths["/control-plane/v1/announcements/patch-note"]) == {"get"}
    dismissal = paths["/control-plane/v1/announcements/{announcement_id}/dismissal"]
    assert set(dismissal) == {"put"}
    history = paths["/control-plane/v1/admin/platform/announcements/activation-history"]
    assert set(history) == {"get"}


# ---------------------------------------------------------------------------
# Patch notes: payload rules
# ---------------------------------------------------------------------------


def test_kind_defaults_to_banner() -> None:
    assert _write().kind == "banner"


def test_patch_note_without_body_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _patch_note(description_long={"en": "  ", "fr": ""})


def test_patch_note_normalizes_severity_dismissible_and_short() -> None:
    request = _patch_note(
        severity="error", description_short={"en": "Ignored"}, dismissible=False
    )

    assert (request.severity, request.dismissible) == ("info", True)
    assert request.description_short == {}


def test_patch_note_keeps_its_title_like_a_banner() -> None:
    request = _patch_note(
        title={"en": "What's new", "fr": "  "}, description_long={"en": "Body"}
    )

    assert request.title == {"en": "What's new"}


def test_patch_note_title_and_body_locales_must_match() -> None:
    with pytest.raises(ValidationError):
        _patch_note(title={"en": "What's new"})
    with pytest.raises(ValidationError):
        _patch_note(description_long={"fr": "Corps"})


def test_patch_note_without_title_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _patch_note(title={"en": " ", "fr": ""})
    with pytest.raises(ValidationError):
        _patch_note(title={"en": "x" * 201})


def test_banner_rules_are_unchanged() -> None:
    with pytest.raises(ValidationError):
        _write(title={})
    with pytest.raises(ValidationError):
        _write(description_short={})
    assert _write(severity="warning", dismissible=False).severity == "warning"


# ---------------------------------------------------------------------------
# Patch notes: one active at a time, and the activation history
# ---------------------------------------------------------------------------


async def _history(deps: ProductServiceDependencies):
    return await list_activation_history(user=_user(), deps=deps)


@pytest.mark.asyncio
async def test_enabling_a_patch_note_disables_the_previous_one(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    a = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )
    b = await create_announcement(user=_user(), request=_patch_note(), deps=deps)

    await set_announcement_enabled(
        user=_user(), announcement_id=b.id, enabled=True, deps=deps
    )

    listed = {
        x.id: x.enabled for x in await list_announcements(user=_user(), deps=deps)
    }
    assert listed == {a.id: False, b.id: True}


@pytest.mark.asyncio
async def test_enabling_a_patch_note_leaves_banners_enabled(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    banners = [
        await create_announcement(user=_user(), request=_write(enabled=True), deps=deps)
        for _ in range(2)
    ]
    await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )
    b = await create_announcement(user=_user(), request=_patch_note(), deps=deps)

    await set_announcement_enabled(
        user=_user(), announcement_id=b.id, enabled=True, deps=deps
    )

    assert {x.id for x in await list_active_announcements(deps=deps)} == {
        banner.id for banner in banners
    }


@pytest.mark.asyncio
async def test_creating_an_enabled_patch_note_disables_the_previous_one(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    a = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )

    b = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )

    assert (await store.get(a.id)).enabled is False  # type: ignore[union-attr]
    assert b.enabled is True


@pytest.mark.asyncio
async def test_activation_and_deactivation_record_events_with_actor(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(
        user=_user("alice"), request=_write(severity="warning"), deps=deps
    )

    await set_announcement_enabled(
        user=_user("alice"), announcement_id=x.id, enabled=True, deps=deps
    )
    await set_announcement_enabled(
        user=_user("bob"), announcement_id=x.id, enabled=False, deps=deps
    )

    events = await _history(deps)
    assert [(e.action, e.actor_uid) for e in events] == [
        ("deactivated", "bob"),
        ("activated", "alice"),
    ]
    assert all(e.announcement_id == x.id and e.kind == "banner" for e in events)
    assert events[0].label == {"en": "Title", "fr": "Titre"}
    # The banner's severity is snapshotted so the history can colour its type.
    assert all(e.severity == "warning" for e in events)


@pytest.mark.asyncio
async def test_auto_deactivation_is_recorded_for_the_acting_admin(
    store: AnnouncementStore, caplog: pytest.LogCaptureFixture
) -> None:
    deps = _deps(store, _platform_admin())
    a = await create_announcement(
        user=_user("carol"), request=_patch_note(enabled=True), deps=deps
    )
    b = await create_announcement(user=_user("carol"), request=_patch_note(), deps=deps)

    with caplog.at_level(logging.INFO, logger=AUDIT_LOGGER_NAME):
        await set_announcement_enabled(
            user=_user("alice"), announcement_id=b.id, enabled=True, deps=deps
        )

    events = await _history(deps)
    assert [(e.announcement_id, e.action, e.actor_uid) for e in events[:2]] == [
        (b.id, "activated", "alice"),
        (a.id, "deactivated", "alice"),
    ]
    assert events[0].kind == "patch_note"
    assert events[0].label == {"en": "What's new in 3.4", "fr": "Nouveautés 3.4"}
    # A patch note's stored severity is a placeholder: none in the history.
    assert all(e.severity is None for e in events[:2])
    toggled = [
        r
        for r in caplog.records
        if r.__dict__.get("audit_event") == "platform.announcement.toggled"
    ]
    assert toggled[0].__dict__["auto_disabled_ids"] == [a.id]


@pytest.mark.asyncio
async def test_no_op_toggle_records_no_event(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(user=_user(), request=_write(), deps=deps)

    await set_announcement_enabled(
        user=_user(), announcement_id=x.id, enabled=False, deps=deps
    )

    assert await _history(deps) == []


@pytest.mark.asyncio
async def test_deleting_an_enabled_announcement_records_deactivation(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    note = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )

    await delete_announcement(user=_user("dave"), announcement_id=note.id, deps=deps)

    events = await _history(deps)
    assert [(e.action, e.actor_uid) for e in events] == [
        ("deactivated", "dave"),
        ("activated", "admin"),
    ]


@pytest.mark.asyncio
async def test_history_survives_deletion(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(user=_user(), request=_write(), deps=deps)
    for enabled in (True, False):
        await set_announcement_enabled(
            user=_user(), announcement_id=x.id, enabled=enabled, deps=deps
        )

    await delete_announcement(user=_user(), announcement_id=x.id, deps=deps)

    events = await _history(deps)
    assert [e.action for e in events] == ["deactivated", "activated"]
    assert all(e.label["en"] == "Title" and e.kind == "banner" for e in events)


async def _simulate_concurrent_activation(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
):
    """Another admin's activation lands between our read and our write."""
    deps = _deps(store, _platform_admin())
    await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )
    b = await create_announcement(user=_user(), request=_patch_note(), deps=deps)

    async def _sees_nothing_to_disable(**_kwargs):
        return []

    monkeypatch.setattr(store, "disable_other_patch_notes", _sees_nothing_to_disable)
    return deps, b


@pytest.mark.asyncio
async def test_concurrent_patch_note_activation_returns_409(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, b = await _simulate_concurrent_activation(store, monkeypatch)

    with pytest.raises(HTTPException) as exc:
        await set_announcement_enabled(
            user=_user(), announcement_id=b.id, enabled=True, deps=deps
        )

    assert exc.value.status_code == 409
    assert (await store.get(b.id)).enabled is False  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_concurrent_enabled_patch_note_creation_returns_409(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, _ = await _simulate_concurrent_activation(store, monkeypatch)
    before = await store.list_all()

    with pytest.raises(HTTPException) as exc:
        await create_announcement(
            user=_user(), request=_patch_note(enabled=True), deps=deps
        )

    assert exc.value.status_code == 409
    assert len(await store.list_all()) == len(before)


@pytest.mark.asyncio
async def test_failed_toggle_records_no_event(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps, b = await _simulate_concurrent_activation(store, monkeypatch)
    before = await _history(deps)

    with pytest.raises(HTTPException):
        await set_announcement_enabled(
            user=_user(), announcement_id=b.id, enabled=True, deps=deps
        )

    assert await _history(deps) == before


@pytest.mark.asyncio
async def test_kind_cannot_change_on_update(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    banner = await create_announcement(user=_user(), request=_write(), deps=deps)

    with pytest.raises(HTTPException) as exc:
        await update_announcement(
            user=_user(), announcement_id=banner.id, request=_patch_note(), deps=deps
        )

    assert exc.value.status_code == 422
    assert (await store.get(banner.id)).kind == "banner"  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Patch notes: delivery and dismissal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_patch_note_is_delivered_until_dismissed(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _nobody())
    note = await create_announcement(
        user=_user(),
        request=_patch_note(enabled=True),
        deps=_deps(store, _platform_admin()),
    )

    delivered = await get_active_patch_note(user=_user("alice"), deps=deps)
    assert delivered.patch_note is not None and delivered.patch_note.id == note.id

    assert delivered.dismissed is False

    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=deps)
    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=deps)

    # Still returned, so the user can reopen it on request, but flagged.
    after = await get_active_patch_note(user=_user("alice"), deps=deps)
    assert after.patch_note is not None and after.dismissed is True


@pytest.mark.asyncio
async def test_dismissal_is_per_user(store: AnnouncementStore) -> None:
    deps = _deps(store, _nobody())
    note = await create_announcement(
        user=_user(),
        request=_patch_note(enabled=True),
        deps=_deps(store, _platform_admin()),
    )

    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=deps)

    assert (
        await get_active_patch_note(user=_user("bob"), deps=deps)
    ).dismissed is False


@pytest.mark.asyncio
async def test_new_patch_note_is_delivered_after_dismissing_the_previous_one(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    a = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )
    await dismiss_patch_note(user=_user("alice"), announcement_id=a.id, deps=admin)
    b = await create_announcement(user=_user(), request=_patch_note(), deps=admin)

    await set_announcement_enabled(
        user=_user(), announcement_id=b.id, enabled=True, deps=admin
    )

    delivered = await get_active_patch_note(user=_user("alice"), deps=admin)
    assert delivered.patch_note is not None and delivered.patch_note.id == b.id
    assert delivered.dismissed is False


@pytest.mark.asyncio
async def test_editing_a_dismissed_patch_note_does_not_redeliver_it(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    a = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )
    await dismiss_patch_note(user=_user("alice"), announcement_id=a.id, deps=admin)

    edited = await update_announcement(
        user=_user(),
        announcement_id=a.id,
        request=_patch_note(
            title={"en": "What's new"},
            description_long={"en": "# Release 3.4 (fixed typo)"},
        ),
        deps=admin,
    )

    assert edited.content_version == a.content_version
    assert (await get_active_patch_note(user=_user("alice"), deps=admin)).dismissed


async def _dismissed_then_disabled(store: AnnouncementStore):
    """Alice dismissed an active patch note that was then switched off."""
    admin = _deps(store, _platform_admin())
    note = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )
    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=admin)
    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=False, deps=admin
    )
    return admin, note


@pytest.mark.asyncio
async def test_re_enabling_a_patch_note_shows_it_again(
    store: AnnouncementStore,
) -> None:
    admin, note = await _dismissed_then_disabled(store)

    relaunched = await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )

    assert relaunched.content_version == note.content_version + 1
    assert not (await get_active_patch_note(user=_user("alice"), deps=admin)).dismissed
    # Once shown again, a fresh "don't show again" holds.
    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=admin)
    assert (await get_active_patch_note(user=_user("alice"), deps=admin)).dismissed


@pytest.mark.asyncio
async def test_re_enabling_a_patch_note_edited_while_off_shows_it_again(
    store: AnnouncementStore,
) -> None:
    admin, note = await _dismissed_then_disabled(store)
    await update_announcement(
        user=_user(),
        announcement_id=note.id,
        request=_patch_note(title={"en": "What's new in 3.5", "fr": "Nouveautés 3.5"}),
        deps=admin,
    )

    relaunched = await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )

    assert relaunched.content_version == note.content_version + 1
    assert not (await get_active_patch_note(user=_user("alice"), deps=admin)).dismissed


@pytest.mark.asyncio
async def test_re_enabling_clears_only_that_notes_dismissals(
    store: AnnouncementStore,
) -> None:
    admin, note = await _dismissed_then_disabled(store)
    await dismiss_patch_note(user=_user("bob"), announcement_id=note.id, deps=admin)
    other = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )
    await dismiss_patch_note(user=_user("alice"), announcement_id=other.id, deps=admin)

    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )

    for uid in ("alice", "bob"):
        assert not await store.is_dismissed(announcement_id=note.id, user_id=uid)
    assert await store.is_dismissed(announcement_id=other.id, user_id="alice")


@pytest.mark.asyncio
async def test_re_enabling_a_live_patch_note_keeps_its_dismissals(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    note = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )
    await dismiss_patch_note(user=_user("alice"), announcement_id=note.id, deps=admin)

    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )

    assert await store.is_dismissed(announcement_id=note.id, user_id="alice")


@pytest.mark.asyncio
async def test_admin_list_counts_dismissals_since_last_enabled(
    store: AnnouncementStore,
) -> None:
    admin, note = await _dismissed_then_disabled(store)
    await dismiss_patch_note(user=_user("bob"), announcement_id=note.id, deps=admin)
    banner = await create_announcement(user=_user(), request=_write(), deps=admin)

    counts = {
        a.id: a.dismissal_count
        for a in await list_announcements(user=_user(), deps=admin)
    }
    assert counts == {note.id: 2, banner.id: None}

    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )

    counts = {
        a.id: a.dismissal_count
        for a in await list_announcements(user=_user(), deps=admin)
    }
    assert counts[note.id] == 0


@pytest.mark.asyncio
async def test_toggle_and_delete_lock_the_row_they_read(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _deps(store, _platform_admin())
    note = await create_announcement(user=_user(), request=_patch_note(), deps=admin)
    real_get = store.get
    locked: list[bool] = []

    async def _spy(announcement_id, *, for_update=False, session=None):
        locked.append(for_update)
        return await real_get(announcement_id, for_update=for_update, session=session)

    monkeypatch.setattr(store, "get", _spy)
    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=True, deps=admin
    )
    await update_announcement(
        user=_user(), announcement_id=note.id, request=_patch_note(), deps=admin
    )
    await delete_announcement(user=_user(), announcement_id=note.id, deps=admin)

    assert locked == [True, True, True]


@pytest.mark.asyncio
async def test_dismissing_a_banner_returns_404(store: AnnouncementStore) -> None:
    admin = _deps(store, _platform_admin())
    banner = await create_announcement(
        user=_user(), request=_write(enabled=True), deps=admin
    )

    for announcement_id in (banner.id, "ghost"):
        with pytest.raises(HTTPException) as exc:
            await dismiss_patch_note(
                user=_user("alice"), announcement_id=announcement_id, deps=admin
            )
        assert exc.value.status_code == 404
    assert not await store.is_dismissed(announcement_id=banner.id, user_id="alice")


@pytest.mark.asyncio
async def test_dismissing_a_note_deleted_meanwhile_returns_404(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    admin = _deps(store, _platform_admin())
    note = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=admin
    )

    async def _foreign_key_failure(**_kwargs):
        raise IntegrityError("INSERT", {}, Exception("FOREIGN KEY constraint failed"))

    monkeypatch.setattr(store, "add_dismissal", _foreign_key_failure)

    with pytest.raises(HTTPException) as exc:
        await dismiss_patch_note(
            user=_user("alice"), announcement_id=note.id, deps=admin
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_history_requires_can_manage_platform(store: AnnouncementStore) -> None:
    rebac = _nobody()

    with pytest.raises(AuthorizationError):
        await list_activation_history(user=_user("mallory"), deps=_deps(store, rebac))

    assert rebac.asked == [OrganizationPermission.CAN_MANAGE_PLATFORM]


@pytest.mark.asyncio
async def test_user_deletion_removes_patch_note_dismissals(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    from control_plane_backend.app.dependencies import attach_application_container
    from control_plane_backend.users import api as users_api
    from control_plane_backend.users.dependencies import (
        get_user_service_dependencies,
    )
    from fastapi import FastAPI
    from fred_core import get_current_user
    from httpx import ASGITransport, AsyncClient

    admin = _deps(store, _platform_admin())
    note = await create_announcement(user=_user(), request=_patch_note(), deps=admin)
    for uid in ("alice", "bob"):
        await dismiss_patch_note(user=_user(uid), announcement_id=note.id, deps=admin)

    async def _nothing(*_args, **_kwargs) -> None:
        return None

    class _Identity:
        async def a_delete_user(self, _user_id: str) -> dict:
            return {}

    async def _root() -> str:
        return "synthetic-root"

    monkeypatch.setattr(users_api, "remove_user_avatar", _nothing)
    container = SimpleNamespace(
        get_rebac_engine=lambda: SimpleNamespace(
            requires_active_accounts=False, check_user_permission_or_raise=_nothing
        ),
        get_platform_bootstrap_store=lambda: SimpleNamespace(get_completed_by=_root),
        get_prompt_store=lambda: SimpleNamespace(delete_favorites_for_user=_nothing),
        get_announcement_store=lambda: store,
    )
    app = FastAPI()
    app.include_router(users_api.router)
    attach_application_container(app, container)  # type: ignore[arg-type]
    app.dependency_overrides[get_current_user] = lambda: _user()
    app.dependency_overrides[get_user_service_dependencies] = lambda: SimpleNamespace(
        configuration=SimpleNamespace(
            security=SimpleNamespace(user_directory="keycloak")
        ),
        create_keycloak_admin_client=lambda: _Identity(),
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.delete("/users/alice")

    assert response.status_code == 204
    assert not await store.is_dismissed(announcement_id=note.id, user_id="alice")
    assert await store.is_dismissed(announcement_id=note.id, user_id="bob")


@pytest.mark.asyncio
async def test_patch_note_routes_reject_an_unauthenticated_caller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.app.dependencies import (
        get_application_container_from_app,
    )
    from control_plane_backend.main import create_app
    from fred_core.security import oidc
    from httpx import ASGITransport, AsyncClient

    app = create_app()
    monkeypatch.setattr(oidc, "KEYCLOAK_ENABLED", True)
    get_application_container_from_app(app).configuration.security.user.enabled = True

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        read = await client.get("/control-plane/v1/announcements/patch-note")
        dismiss = await client.put("/control-plane/v1/announcements/x/dismissal")
        history = await client.get(
            "/control-plane/v1/admin/platform/announcements/activation-history"
        )

    assert (read.status_code, dismiss.status_code, history.status_code) == (
        401,
        401,
        401,
    )
