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
from control_plane_backend.announcements.schemas import (
    AnnouncementWriteRequest,
    PatchNoteAnnounceRequest,
    PatchNoteOrderRequest,
)
from control_plane_backend.announcements.service import (
    announce_patch_notes,
    create_announcement,
    delete_announcement,
    get_patch_note_announcement,
    get_patch_note_history,
    get_patch_note_package,
    list_active_announcements,
    list_announcements,
    list_exposure_history,
    mark_patch_note_announcement_seen,
    set_announcement_enabled,
    set_patch_note_order,
    update_announcement,
    withdraw_patch_note_announcement,
)
from control_plane_backend.announcements.store import (
    AnnouncementStore,
    StoredExposure,
)
from control_plane_backend.models.announcement_models import (
    MAX_PATCH_NOTE_IDS,
    MAX_PATCH_NOTES_PER_ANNOUNCEMENT,
)
from control_plane_backend.models.base import utcnow
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
    note = await create_announcement(
        user=_user(), request=_patch_note(enabled=True), deps=deps
    )
    await set_patch_note_order(user=_user(), ordered_ids=[note.id], deps=deps)
    announced = await _announce(user=_user(), deps=deps)
    await get_patch_note_announcement(user=_user(), deps=deps)
    await get_patch_note_package(user=_user(), announcement_id=announced.id, deps=deps)
    await list_exposure_history(user=_user(), deps=deps)
    await withdraw_patch_note_announcement(user=_user(), deps=deps)

    assert rebac.asked == [OrganizationPermission.CAN_MANAGE_PLATFORM] * 12


@pytest.mark.asyncio
async def test_non_administrator_is_refused_every_mutation(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    existing = await create_announcement(user=_user(), request=_write(), deps=admin)
    notes = [
        await create_announcement(
            user=_user(), request=_patch_note(enabled=True), deps=admin
        )
        for _ in range(2)
    ]
    order_before = [n.id for n in await _patch_notes(admin)]
    announced = await _announce(user=_user(), deps=admin)
    deps = _deps(store, _nobody())

    for call in (
        lambda: list_announcements(user=_user("mallory"), deps=deps),
        lambda: set_patch_note_order(
            user=_user("mallory"), ordered_ids=[notes[0].id, notes[1].id], deps=deps
        ),
        lambda: _announce(user=_user("mallory"), deps=deps),
        lambda: withdraw_patch_note_announcement(user=_user("mallory"), deps=deps),
        lambda: get_patch_note_announcement(user=_user("mallory"), deps=deps),
        lambda: get_patch_note_package(
            user=_user("mallory"), announcement_id=announced.id, deps=deps
        ),
        lambda: list_exposure_history(user=_user("mallory"), deps=deps),
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
    assert [n.id for n in await _patch_notes(admin)] == order_before
    # Neither replaced nor withdrawn.
    current = await get_patch_note_announcement(user=_user(), deps=admin)
    assert current is not None and current.id == announced.id


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
        note = await create_announcement(
            user=_user(), request=_patch_note(enabled=True), deps=deps
        )
        await set_patch_note_order(user=_user(), ordered_ids=[note.id], deps=deps)
        await _announce(user=_user(), deps=deps)
        await withdraw_patch_note_announcement(user=_user(), deps=deps)

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
        "platform.announcement.created",
        "platform.announcement.patch_notes_reordered",
        "platform.announcement.patch_notes_announced",
        "platform.announcement.patch_notes_withdrawn",
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
    assert set(paths["/control-plane/v1/announcements/patch-notes"]) == {"get"}
    seen = paths[
        "/control-plane/v1/announcements/patch-note-announcements"
        "/{announcement_id}/seen"
    ]
    assert set(seen) == {"put"}
    admin_prefix = "/control-plane/v1/admin/platform/announcements"
    assert set(paths[f"{admin_prefix}/activation-history"]) == {"get"}
    assert set(paths[f"{admin_prefix}/patch-notes/order"]) == {"put"}
    assert set(paths[f"{admin_prefix}/patch-notes/announcement"]) == {
        "get",
        "post",
        "delete",
    }
    package = paths[f"{admin_prefix}/patch-notes/announcements/{{announcement_id}}"]
    assert set(package) == {"get"}
    assert "/control-plane/v1/announcements/patch-note" not in paths
    assert "/control-plane/v1/announcements/{announcement_id}/dismissal" not in paths


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
# Patch notes: the working area and its order
# ---------------------------------------------------------------------------


async def _history(deps: ProductServiceDependencies):
    return await list_exposure_history(user=_user(), deps=deps)


async def _patch_notes(deps: ProductServiceDependencies):
    """The admin list's patch notes, in the order it returns them."""
    listed = await list_announcements(user=_user(), deps=deps)
    return [a for a in listed if a.kind == "patch_note"]


async def _titled(deps: ProductServiceDependencies, title: str, *, enabled: bool):
    return await create_announcement(
        user=_user(),
        request=_patch_note(
            title={"en": title}, description_long={"en": f"# {title}"}, enabled=enabled
        ),
        deps=deps,
    )


async def _announce(*, user: KeycloakUser, deps: ProductServiceDependencies):
    """Announce what an administrator who just confirmed the list would send."""
    included = await deps.get_announcement_store().list_included_patch_notes()
    return await announce_patch_notes(
        user=user, expected_ids=[note.id for note in included], deps=deps
    )


async def _read(deps: ProductServiceDependencies, uid: str = "alice"):
    return await get_patch_note_history(user=_user(uid), deps=deps)


async def _pending(deps: ProductServiceDependencies, uid: str) -> str | None:
    return (await _read(deps, uid)).pending_announcement_id


async def _titles(deps: ProductServiceDependencies, uid: str = "alice") -> list[str]:
    return [note.title["en"] for note in (await _read(deps, uid)).patch_notes]


@pytest.mark.asyncio
async def test_a_patch_note_is_created_off_by_default(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())

    note = await create_announcement(
        user=_user(),
        request=AnnouncementWriteRequest(
            kind="patch_note",
            severity="info",
            title={"en": "3.4"},
            description_short={},
            description_long={"en": "# 3.4"},
        ),
        deps=deps,
    )

    assert note.enabled is False
    assert await _titles(deps) == []


@pytest.mark.asyncio
async def test_several_patch_notes_can_be_included_at_once(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=True)
    b = await _titled(deps, "B", enabled=False)

    await set_announcement_enabled(
        user=_user(), announcement_id=b.id, enabled=True, deps=deps
    )
    await _titled(deps, "C", enabled=True)

    assert all(n.enabled for n in await _patch_notes(deps))


@pytest.mark.asyncio
async def test_toggling_a_patch_note_leaves_banners_alone(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    banners = [
        await create_announcement(user=_user(), request=_write(enabled=True), deps=deps)
        for _ in range(2)
    ]
    note = await _titled(deps, "A", enabled=True)

    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=False, deps=deps
    )

    assert {x.id for x in await list_active_announcements(deps=deps)} == {
        banner.id for banner in banners
    }


@pytest.mark.asyncio
async def test_a_new_patch_note_goes_to_the_top(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    banner = await create_announcement(user=_user(), request=_write(), deps=deps)
    for title in ("A", "B", "C"):
        await _titled(deps, title, enabled=False)

    listed = await _patch_notes(deps)

    assert [n.title["en"] for n in listed] == ["C", "B", "A"]
    assert [n.position for n in listed] == [1, 2, 3]
    everything = await list_announcements(user=_user(), deps=deps)
    assert everything[0].id == banner.id and everything[0].position is None


@pytest.mark.asyncio
async def test_reordering_stores_the_given_order(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    a, b, c = [await _titled(deps, t, enabled=True) for t in ("A", "B", "C")]

    await set_patch_note_order(user=_user(), ordered_ids=[a.id, c.id, b.id], deps=deps)

    listed = await _patch_notes(deps)
    assert [n.id for n in listed] == [a.id, c.id, b.id]
    assert [n.position for n in listed] == [1, 2, 3]
    assert all(n.enabled for n in listed)


@pytest.mark.asyncio
async def test_a_reorder_that_is_not_the_current_set_is_refused(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    a, b = [await _titled(deps, t, enabled=False) for t in ("A", "B")]
    banner = await create_announcement(user=_user(), request=_write(), deps=deps)
    before = [n.id for n in await _patch_notes(deps)]

    for stale in (
        [a.id],  # another administrator created B meanwhile
        [a.id, b.id, "deleted-meanwhile"],
        [a.id, a.id],
        [a.id, banner.id],
        [],
    ):
        with pytest.raises(HTTPException) as exc:
            await set_patch_note_order(user=_user(), ordered_ids=stale, deps=deps)
        assert exc.value.status_code == 409

    assert [n.id for n in await _patch_notes(deps)] == before
    assert (await store.get(banner.id)).position is None  # type: ignore[union-attr]


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


# ---------------------------------------------------------------------------
# The exposure history: banners
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_banner_exposure_is_one_line_with_its_author(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(
        user=_user("alice"), request=_write(severity="warning"), deps=deps
    )

    await set_announcement_enabled(
        user=_user("alice"), announcement_id=x.id, enabled=True, deps=deps
    )
    [on_air] = await _history(deps)
    assert on_air.deactivated_at is None

    await set_announcement_enabled(
        user=_user("bob"), announcement_id=x.id, enabled=False, deps=deps
    )

    [line] = await _history(deps)
    assert (line.id, line.kind, line.announcement_id) == (on_air.id, "banner", x.id)
    assert line.label == {"en": "Title", "fr": "Titre"}
    # The severity is snapshotted so the history can colour the type.
    assert (line.severity, line.actor_uid, line.note_count) == (
        "warning",
        "alice",
        None,
    )
    assert line.deactivated_at is not None
    assert line.deactivated_at >= line.activated_at


@pytest.mark.asyncio
async def test_re_enabling_a_banner_starts_a_new_line(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(user=_user(), request=_write(enabled=True), deps=deps)
    for enabled in (False, True):
        await set_announcement_enabled(
            user=_user(), announcement_id=x.id, enabled=enabled, deps=deps
        )

    newer, older = await _history(deps)

    assert newer.deactivated_at is None and older.deactivated_at is not None


@pytest.mark.asyncio
async def test_no_op_toggle_writes_no_line(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(user=_user(), request=_write(), deps=deps)

    await set_announcement_enabled(
        user=_user(), announcement_id=x.id, enabled=False, deps=deps
    )
    assert await _history(deps) == []

    for _ in range(2):
        await set_announcement_enabled(
            user=_user(), announcement_id=x.id, enabled=True, deps=deps
        )
    assert len(await _history(deps)) == 1


@pytest.mark.asyncio
async def test_deleting_an_enabled_banner_ends_its_line_which_survives(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    x = await create_announcement(user=_user(), request=_write(enabled=True), deps=deps)

    await delete_announcement(user=_user("dave"), announcement_id=x.id, deps=deps)

    [line] = await _history(deps)
    assert line.deactivated_at is not None
    assert (line.label["en"], line.kind, line.actor_uid) == ("Title", "banner", "admin")


@pytest.mark.asyncio
async def test_working_on_patch_notes_writes_no_line(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    note = await _titled(deps, "A", enabled=True)
    other = await _titled(deps, "B", enabled=False)

    for enabled in (False, True):
        await set_announcement_enabled(
            user=_user(), announcement_id=note.id, enabled=enabled, deps=deps
        )
    await set_patch_note_order(user=_user(), ordered_ids=[note.id, other.id], deps=deps)
    await delete_announcement(user=_user(), announcement_id=note.id, deps=deps)

    assert await _history(deps) == []


@pytest.mark.asyncio
async def test_failed_toggle_writes_no_line(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = _deps(store, _platform_admin())
    banner = await create_announcement(user=_user(), request=_write(), deps=deps)

    async def _fails(*_args, **_kwargs):
        raise RuntimeError("storage went away")

    monkeypatch.setattr(store, "add_exposure", _fails)

    with pytest.raises(RuntimeError):
        await set_announcement_enabled(
            user=_user(), announcement_id=banner.id, enabled=True, deps=deps
        )

    monkeypatch.undo()
    assert (await store.get(banner.id)).enabled is False  # type: ignore[union-attr]
    assert await _history(deps) == []


# ---------------------------------------------------------------------------
# Announcing a package, withdrawing it, and what each user has seen
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_nothing_is_read_until_an_administrator_announces(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=True)

    history = await _read(deps)

    assert history.patch_notes == [] and history.pending_announcement_id is None
    assert await get_patch_note_announcement(user=_user(), deps=deps) is None


@pytest.mark.asyncio
async def test_announcing_freezes_the_included_notes_in_order(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    await _titled(admin, "C", enabled=True)
    await _titled(admin, "B", enabled=False)
    a = await create_announcement(
        user=_user(),
        request=_patch_note(
            title={"en": "A", "fr": "A (fr)"},
            description_long={"en": "# A", "fr": "# A en français"},
            enabled=True,
        ),
        deps=admin,
    )

    announced = await _announce(user=_user("alice"), deps=admin)

    rebac = _nobody()
    history = await _read(_deps(store, rebac), "bob")
    assert [n.title["en"] for n in history.patch_notes] == ["A", "C"]
    # Every language the note holds is frozen with it.
    assert history.patch_notes[0].model_dump() == {
        "id": a.id,
        "title": {"en": "A", "fr": "A (fr)"},
        "description_long": {"en": "# A", "fr": "# A en français"},
    }
    assert history.pending_announcement_id == announced.id
    # Authentication is the only gate on the read.
    assert rebac.asked == []
    current = await get_patch_note_announcement(user=_user(), deps=admin)
    assert current is not None
    assert (current.id, current.announced_by) == (announced.id, "alice")


@pytest.mark.asyncio
async def test_the_working_area_never_reaches_users(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    a = await _titled(deps, "A", enabled=True)
    b = await _titled(deps, "B", enabled=True)
    announced = await _announce(user=_user(), deps=deps)
    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=announced.id, deps=deps
    )
    before = await _read(deps, "bob")

    c = await _titled(deps, "C", enabled=True)
    await update_announcement(
        user=_user(),
        announcement_id=a.id,
        request=_patch_note(title={"en": "A2"}, description_long={"en": "Reworded"}),
        deps=deps,
    )
    await set_patch_note_order(user=_user(), ordered_ids=[a.id, c.id, b.id], deps=deps)
    await set_announcement_enabled(
        user=_user(), announcement_id=a.id, enabled=False, deps=deps
    )
    await delete_announcement(user=_user(), announcement_id=b.id, deps=deps)

    # Bob still reads the package as announced, and it is still pending for him.
    assert await _read(deps, "bob") == before
    assert await _titles(deps) == ["B", "A"]
    assert await _pending(deps, "alice") is None
    assert await store.get_seen_announcement_id("alice") == announced.id


@pytest.mark.asyncio
async def test_hiding_every_patch_note_withdraws_nothing(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    note = await _titled(deps, "A", enabled=True)
    announced = await _announce(user=_user(), deps=deps)

    await set_announcement_enabled(
        user=_user(), announcement_id=note.id, enabled=False, deps=deps
    )

    assert await _titles(deps) == ["A"]
    assert await _pending(deps, "bob") == announced.id


@pytest.mark.asyncio
async def test_announcing_with_nothing_included_is_refused(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=False)

    with pytest.raises(HTTPException) as exc:
        await _announce(user=_user(), deps=deps)

    assert exc.value.status_code == 409
    assert await _history(deps) == []


@pytest.mark.asyncio
async def test_announcing_freezes_only_the_confirmed_list(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    first = await _titled(deps, "A", enabled=True)
    second = await _titled(deps, "B", enabled=True)

    # Another administrator's change since the confirmation: order, then content.
    for confirmed in ([first.id, second.id], [second.id], [second.id, first.id, "x"]):
        with pytest.raises(HTTPException) as exc:
            await announce_patch_notes(user=_user(), expected_ids=confirmed, deps=deps)
        assert exc.value.status_code == 409
        assert "changed" in exc.value.detail
    assert await _history(deps) == []

    await announce_patch_notes(
        user=_user(), expected_ids=[second.id, first.id], deps=deps
    )
    assert await _titles(deps) == ["B", "A"]


@pytest.mark.asyncio
async def test_an_announcement_holds_a_bounded_number_of_patch_notes(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    notes = [
        await _titled(deps, f"N{index}", enabled=True)
        for index in range(MAX_PATCH_NOTES_PER_ANNOUNCEMENT + 1)
    ]

    with pytest.raises(HTTPException) as exc:
        await _announce(user=_user(), deps=deps)
    assert exc.value.status_code == 409
    assert str(MAX_PATCH_NOTES_PER_ANNOUNCEMENT) in exc.value.detail
    assert await _history(deps) == []

    await set_announcement_enabled(
        user=_user(), announcement_id=notes[0].id, enabled=False, deps=deps
    )
    await _announce(user=_user(), deps=deps)
    assert len(await _titles(deps)) == MAX_PATCH_NOTES_PER_ANNOUNCEMENT


def test_patch_note_id_lists_are_bounded() -> None:
    too_many = [str(index) for index in range(MAX_PATCH_NOTE_IDS + 1)]

    for request in (PatchNoteOrderRequest, PatchNoteAnnounceRequest):
        request(ids=too_many[:-1])
        with pytest.raises(ValidationError):
            request(ids=too_many)
    with pytest.raises(ValidationError):
        PatchNoteAnnounceRequest(ids=[])


@pytest.mark.asyncio
async def test_announce_and_withdraw_take_the_patch_note_lock(
    store: AnnouncementStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=True)
    locked: list[bool] = []

    async def _spy(*, session):
        locked.append(session.in_transaction())

    monkeypatch.setattr(store, "lock_patch_notes", _spy)

    await _announce(user=_user(), deps=deps)
    await withdraw_patch_note_announcement(user=_user(), deps=deps)

    assert locked == [True, True]


@pytest.mark.asyncio
async def test_announcing_again_replaces_the_package_for_everyone(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    a = await _titled(deps, "A", enabled=True)
    first = await _announce(user=_user("alice"), deps=deps)
    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=first.id, deps=deps
    )
    await update_announcement(
        user=_user(),
        announcement_id=a.id,
        request=_patch_note(title={"en": "A"}, description_long={"en": "No typo"}),
        deps=deps,
    )
    await _titled(deps, "B", enabled=True)

    second = await _announce(user=_user("bob"), deps=deps)

    history = await _read(deps, "alice")
    assert [n.title["en"] for n in history.patch_notes] == ["B", "A"]
    assert history.patch_notes[1].description_long == {"en": "No typo"}
    # Never a silent replace: it is pending again for who saw the first one.
    assert history.pending_announcement_id == second.id
    newer, older = await _history(deps)
    assert (newer.id, newer.actor_uid, newer.deactivated_at) == (second.id, "bob", None)
    assert (newer.label, newer.note_count, newer.kind) == ({"en": "B"}, 2, "patch_note")
    assert (older.id, older.actor_uid, older.note_count) == (first.id, "alice", 1)
    # Replaced at the very moment the next one started.
    assert older.deactivated_at == newer.activated_at
    assert newer.severity is None


@pytest.mark.asyncio
async def test_a_history_line_keeps_its_package(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    a = await _titled(deps, "A", enabled=True)
    first = await _announce(user=_user(), deps=deps)
    await delete_announcement(user=_user(), announcement_id=a.id, deps=deps)
    await _titled(deps, "B", enabled=True)
    await _announce(user=_user(), deps=deps)
    banner = await create_announcement(
        user=_user(), request=_write(enabled=True), deps=deps
    )
    [banner_line] = [line for line in await _history(deps) if line.kind == "banner"]

    package = await get_patch_note_package(
        user=_user(), announcement_id=first.id, deps=deps
    )

    # As users saw it, although replaced and its note deleted since.
    assert [(n.id, n.title, n.description_long) for n in package] == [
        (a.id, {"en": "A"}, {"en": "# A"})
    ]
    for no_package in ("ghost", banner.id, banner_line.id):
        with pytest.raises(HTTPException) as exc:
            await get_patch_note_package(
                user=_user(), announcement_id=no_package, deps=deps
            )
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_withdrawing_leaves_nothing_to_read(store: AnnouncementStore) -> None:
    deps = _deps(store, _platform_admin())
    note = await _titled(deps, "A", enabled=True)
    announced = await _announce(user=_user(), deps=deps)
    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=announced.id, deps=deps
    )

    await withdraw_patch_note_announcement(user=_user("bob"), deps=deps)

    for uid in ("alice", "bob"):
        history = await _read(deps, uid)
        assert history.patch_notes == [] and history.pending_announcement_id is None
    assert await get_patch_note_announcement(user=_user(), deps=deps) is None
    [line] = await _history(deps)
    assert line.id == announced.id and line.deactivated_at is not None
    # The working area is untouched, and the line still opens.
    assert (await store.get(note.id)).enabled is True  # type: ignore[union-attr]
    assert await get_patch_note_package(
        user=_user(), announcement_id=announced.id, deps=deps
    )

    with pytest.raises(HTTPException) as exc:
        await withdraw_patch_note_announcement(user=_user(), deps=deps)
    assert exc.value.status_code == 404

    again = await _announce(user=_user(), deps=deps)
    assert await _pending(deps, "alice") == again.id
    assert await _titles(deps, "bob") == ["A"]


@pytest.mark.asyncio
async def test_seen_is_per_user_idempotent_and_asks_no_permission(
    store: AnnouncementStore,
) -> None:
    admin = _deps(store, _platform_admin())
    await _titled(admin, "A", enabled=True)
    announced = await _announce(user=_user(), deps=admin)
    rebac = _nobody()
    deps = _deps(store, rebac)

    for _ in range(2):
        await mark_patch_note_announcement_seen(
            user=_user("alice"), announcement_id=announced.id, deps=deps
        )

    assert await _pending(deps, "alice") is None
    assert await _titles(deps, "alice") == ["A"]
    assert await _pending(deps, "bob") == announced.id
    assert rebac.asked == []


@pytest.mark.asyncio
async def test_an_announcement_made_meanwhile_stays_pending(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=True)
    shown = await _announce(user=_user(), deps=deps)
    newer = await _announce(user=_user(), deps=deps)

    # Alice closes the dialog that opened for the first one.
    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=shown.id, deps=deps
    )

    assert await _pending(deps, "alice") == newer.id


@pytest.mark.asyncio
async def test_a_late_record_does_not_move_a_user_back(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    await _titled(deps, "A", enabled=True)
    older = await _announce(user=_user(), deps=deps)
    newer = await _announce(user=_user(), deps=deps)
    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=newer.id, deps=deps
    )

    await mark_patch_note_announcement_seen(
        user=_user("alice"), announcement_id=older.id, deps=deps
    )

    assert await store.get_seen_announcement_id("alice") == newer.id
    assert await _pending(deps, "alice") is None


@pytest.mark.asyncio
async def test_seen_refuses_what_is_not_an_announced_package(
    store: AnnouncementStore,
) -> None:
    deps = _deps(store, _platform_admin())
    note = await _titled(deps, "A", enabled=True)
    await create_announcement(user=_user(), request=_write(enabled=True), deps=deps)
    [banner_line] = await _history(deps)

    for not_an_announcement in ("ghost", note.id, banner_line.id):
        with pytest.raises(HTTPException) as exc:
            await mark_patch_note_announcement_seen(
                user=_user("alice"),
                announcement_id=not_an_announcement,
                deps=deps,
            )
        assert exc.value.status_code == 404
    assert await store.get_seen_announcement_id("alice") is None


@pytest.mark.asyncio
async def test_a_package_that_does_not_open_the_dialog_is_still_read(
    store: AnnouncementStore,
) -> None:
    # What the upgrade leaves behind: readable, pending for nobody.
    deps = _deps(store, _platform_admin())
    await store.add_exposure(
        StoredExposure(
            id="upgrade",
            kind="patch_note",
            announcement_id="p1",
            label={"en": "A"},
            actor_uid=None,
            activated_at=utcnow(),
            note_count=1,
            package=[{"id": "p1", "title": {"en": "A"}, "description_long": {}}],
            opens_dialog=False,
        )
    )

    assert await _titles(deps, "alice") == ["A"]
    assert await _pending(deps, "alice") is None
    current = await get_patch_note_announcement(user=_user(), deps=deps)
    assert current is not None and current.announced_by is None


@pytest.mark.asyncio
async def test_history_requires_can_manage_platform(store: AnnouncementStore) -> None:
    rebac = _nobody()

    with pytest.raises(AuthorizationError):
        await list_exposure_history(user=_user("mallory"), deps=_deps(store, rebac))

    assert rebac.asked == [OrganizationPermission.CAN_MANAGE_PLATFORM]


@pytest.mark.asyncio
async def test_user_deletion_removes_what_the_user_has_seen(
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
    await _titled(admin, "A", enabled=True)
    announced = await _announce(user=_user(), deps=admin)
    for uid in ("alice", "bob"):
        await mark_patch_note_announcement_seen(
            user=_user(uid), announcement_id=announced.id, deps=admin
        )

    async def _nothing(*_args, **_kwargs) -> None:
        return None

    class _Identity:
        async def a_delete_user(self, _user_id: str) -> dict:
            return {}

    async def _root() -> str:
        return "synthetic-root"

    monkeypatch.setattr(users_api, "remove_user_avatar", _nothing)
    monkeypatch.setattr(users_api, "_mark_user_join_history_deleted", _nothing)
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
    app.dependency_overrides[get_current_user] = _user
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
    assert await store.get_seen_announcement_id("alice") is None
    assert await store.get_seen_announcement_id("bob") == announced.id


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
    user = "/control-plane/v1/announcements"
    admin = "/control-plane/v1/admin/platform/announcements"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.get(f"{user}/patch-notes"),
            await client.put(f"{user}/patch-note-announcements/x/seen"),
            await client.get(f"{admin}/activation-history"),
            await client.put(f"{admin}/patch-notes/order", json={"ids": []}),
            await client.get(f"{admin}/patch-notes/announcement"),
            await client.post(f"{admin}/patch-notes/announcement", json={"ids": ["x"]}),
            await client.delete(f"{admin}/patch-notes/announcement"),
            await client.get(f"{admin}/patch-notes/announcements/x"),
        ]

    assert [response.status_code for response in responses] == [401] * 8
