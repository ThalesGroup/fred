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

"""Announcement store CRUD.

The distinctions these tests pin: `list_enabled` is the delivery surface and
must never leak a disabled row, and `set_enabled` writes exactly the
`content_version` it is handed. The store never decides that value — whether a
toggle expires the dismissals users have stored against it is the service's
call, and keeping it out of here is what stops the rule living in two places.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from control_plane_backend.announcements.store import (
    AnnouncementStore,
    StoredActivationEvent,
)
from control_plane_backend.models.table_ownership import OWNED_TABLES
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture
async def store(control_plane_sql_engine: AsyncEngine) -> AnnouncementStore:
    return AnnouncementStore(control_plane_sql_engine)


async def _make(
    store: AnnouncementStore,
    announcement_id: str,
    *,
    severity: str = "info",
    enabled: bool = False,
    dismissible: bool = True,
    long: dict[str, str] | None = None,
):
    return await store.create(
        announcement_id=announcement_id,
        severity=severity,
        title={"en": f"Title {announcement_id}", "fr": f"Titre {announcement_id}"},
        description_short={"en": "Short", "fr": "Court"},
        description_long=long if long is not None else {},
        enabled=enabled,
        dismissible=dismissible,
        created_by="admin@example.com",
    )


@pytest.mark.asyncio
async def test_create_then_get_round_trips_every_field(
    store: AnnouncementStore,
) -> None:
    created = await _make(
        store, "a1", severity="warning", dismissible=False, long={"en": "Long body"}
    )

    assert created.content_version == 1
    assert created.created_by == "admin@example.com"

    fetched = await store.get("a1")
    assert fetched is not None
    assert fetched.severity == "warning"
    assert fetched.title == {"en": "Title a1", "fr": "Titre a1"}
    assert fetched.description_short == {"en": "Short", "fr": "Court"}
    assert fetched.description_long == {"en": "Long body"}
    assert fetched.enabled is False
    assert fetched.dismissible is False


@pytest.mark.asyncio
async def test_get_unknown_id_returns_none(store: AnnouncementStore) -> None:
    assert await store.get("nope") is None


@pytest.mark.asyncio
async def test_list_all_returns_every_announcement(store: AnnouncementStore) -> None:
    await _make(store, "a1")
    await _make(store, "a2", enabled=True)

    assert {a.id for a in await store.list_all()} == {"a1", "a2"}


@pytest.mark.asyncio
async def test_list_enabled_excludes_disabled(store: AnnouncementStore) -> None:
    await _make(store, "off", enabled=False)
    await _make(store, "on", enabled=True)

    assert [a.id for a in await store.list_enabled()] == ["on"]


@pytest.mark.asyncio
async def test_update_overwrites_fields_and_writes_the_given_version(
    store: AnnouncementStore,
) -> None:
    await _make(store, "a1")

    updated = await store.update(
        announcement_id="a1",
        severity="error",
        title={"en": "New"},
        description_short={"en": "New short"},
        description_long={"en": "New long"},
        dismissible=False,
        content_version=7,
        updated_by="other@example.com",
    )

    assert updated is not None
    assert updated.severity == "error"
    assert updated.title == {"en": "New"}
    assert updated.description_long == {"en": "New long"}
    # Delivery is not content: only `set_enabled` changes it.
    assert updated.enabled is False
    assert updated.dismissible is False
    assert updated.content_version == 7
    assert updated.updated_by == "other@example.com"
    # The store must not decide the version — it wrote exactly what it was given.
    assert (await store.get("a1")).content_version == 7  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_update_unknown_id_returns_none(store: AnnouncementStore) -> None:
    assert (
        await store.update(
            announcement_id="nope",
            severity="info",
            title={"en": "x"},
            description_short={"en": "x"},
            description_long={},
            dismissible=True,
            content_version=2,
            updated_by=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_set_enabled_writes_the_content_version_it_is_given(
    store: AnnouncementStore,
) -> None:
    created = await _make(store, "a1", enabled=False)

    toggled = await store.set_enabled(
        announcement_id="a1",
        enabled=True,
        content_version=created.content_version + 1,
        updated_by="admin@example.com",
    )

    assert toggled is not None
    assert toggled.enabled is True
    assert toggled.content_version == created.content_version + 1
    # Only delivery and the version move: the wording is untouched.
    assert toggled.title == created.title


@pytest.mark.asyncio
async def test_set_enabled_unknown_id_returns_none(store: AnnouncementStore) -> None:
    assert (
        await store.set_enabled(
            announcement_id="nope",
            enabled=True,
            content_version=1,
            updated_by=None,
        )
        is None
    )


@pytest.mark.asyncio
async def test_delete_removes_the_row_and_reports_whether_it_did(
    store: AnnouncementStore,
) -> None:
    await _make(store, "a1")

    deleted = await store.delete("a1")
    assert deleted is True
    assert await store.get("a1") is None
    deleted_again = await store.delete("a1")
    assert deleted_again is False


# ---------------------------------------------------------------------------
# Patch notes, dismissals and the activation history
# ---------------------------------------------------------------------------


async def _make_patch_note(
    store: AnnouncementStore, announcement_id: str, *, enabled: bool = False
):
    return await store.create(
        announcement_id=announcement_id,
        kind="patch_note",
        severity="info",
        title={"en": f"Release {announcement_id}"},
        description_short={},
        description_long={"en": f"# Release {announcement_id}"},
        enabled=enabled,
        dismissible=True,
        created_by="admin",
    )


def _event(
    event_id: str, minute: int, severity: str | None = "error"
) -> StoredActivationEvent:
    return StoredActivationEvent(
        id=event_id,
        announcement_id="a1",
        kind="banner",
        label={"en": "Title"},
        action="activated",
        actor_uid="admin",
        occurred_at=datetime(2026, 10, 9, 12, minute, tzinfo=timezone.utc),
        severity=severity,
    )


def test_new_tables_are_owned_by_control_plane() -> None:
    assert {
        "platform_announcement",
        "platform_announcement_dismissal",
        "platform_announcement_activation_event",
    } <= OWNED_TABLES


@pytest.mark.asyncio
async def test_second_enabled_patch_note_violates_the_unique_index(
    store: AnnouncementStore,
) -> None:
    # The service disables the previous one first; the index is the backstop
    # for two concurrent activations.
    await _make_patch_note(store, "p1", enabled=True)
    await _make_patch_note(store, "p2", enabled=False)
    await _make(store, "b1", enabled=True)

    with pytest.raises(IntegrityError):
        await store.set_enabled(
            announcement_id="p2",
            enabled=True,
            content_version=2,
            updated_by=None,
        )


@pytest.mark.asyncio
async def test_list_enabled_returns_banners_only(store: AnnouncementStore) -> None:
    await _make(store, "banner", enabled=True)
    await _make_patch_note(store, "note", enabled=True)

    assert [a.id for a in await store.list_enabled()] == ["banner"]
    note = await store.get_enabled_patch_note()
    assert note is not None and note.kind == "patch_note"


@pytest.mark.asyncio
async def test_disable_other_patch_notes_returns_what_it_disabled(
    store: AnnouncementStore,
) -> None:
    await _make_patch_note(store, "p1", enabled=True)
    await _make(store, "b1", enabled=True)

    async with store.transaction() as session:
        disabled = await store.disable_other_patch_notes(
            except_id="p2", updated_by="admin", session=session
        )

    assert [a.id for a in disabled] == ["p1"]
    assert disabled[0].enabled is True  # as stored before the change
    assert (await store.get("p1")).enabled is False  # type: ignore[union-attr]
    assert (await store.get("b1")).enabled is True  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_add_dismissal_is_idempotent(store: AnnouncementStore) -> None:
    await _make_patch_note(store, "p1")

    await store.add_dismissal(announcement_id="p1", user_id="alice")
    await store.add_dismissal(announcement_id="p1", user_id="alice")

    assert await store.is_dismissed(announcement_id="p1", user_id="alice")
    assert not await store.is_dismissed(announcement_id="p1", user_id="bob")
    assert await store.count_dismissals() == {"p1": 1}


@pytest.mark.asyncio
async def test_count_dismissals_per_note(store: AnnouncementStore) -> None:
    await _make_patch_note(store, "p1")
    await _make_patch_note(store, "p2")
    for uid in ("alice", "bob"):
        await store.add_dismissal(announcement_id="p1", user_id=uid)
    await store.add_dismissal(announcement_id="p2", user_id="alice")

    assert await store.count_dismissals() == {"p1": 2, "p2": 1}


@pytest.mark.asyncio
async def test_delete_dismissals_spares_other_notes(store: AnnouncementStore) -> None:
    await _make_patch_note(store, "p1")
    await _make_patch_note(store, "p2")
    for note in ("p1", "p2"):
        await store.add_dismissal(announcement_id=note, user_id="alice")

    await store.delete_dismissals("p1")

    assert await store.count_dismissals() == {"p2": 1}


@pytest.mark.asyncio
async def test_add_dismissal_for_a_deleted_note_raises(
    store: AnnouncementStore, control_plane_sql_engine: AsyncEngine
) -> None:
    # SQLite only enforces foreign keys per connection, when asked to.
    event.listen(
        control_plane_sql_engine.sync_engine,
        "connect",
        lambda conn, _record: conn.execute("PRAGMA foreign_keys=ON"),
    )
    await control_plane_sql_engine.dispose()

    with pytest.raises(IntegrityError):
        await store.add_dismissal(announcement_id="ghost", user_id="alice")


@pytest.mark.asyncio
async def test_delete_removes_dismissals(store: AnnouncementStore) -> None:
    await _make_patch_note(store, "p1")
    await store.add_dismissal(announcement_id="p1", user_id="alice")

    assert await store.delete("p1") is True
    assert not await store.is_dismissed(announcement_id="p1", user_id="alice")


@pytest.mark.asyncio
async def test_delete_dismissals_for_user(store: AnnouncementStore) -> None:
    await _make_patch_note(store, "p1")
    await _make_patch_note(store, "p2")
    for note in ("p1", "p2"):
        await store.add_dismissal(announcement_id=note, user_id="alice")
    await store.add_dismissal(announcement_id="p1", user_id="bob")

    await store.delete_dismissals_for_user("alice")

    assert await store.count_dismissals() == {"p1": 1}
    assert await store.is_dismissed(announcement_id="p1", user_id="bob")


@pytest.mark.asyncio
async def test_activation_events_newest_first_and_capped(
    store: AnnouncementStore,
) -> None:
    await store.append_activation_events([_event(f"e{m}", m) for m in range(5)])

    latest = await store.list_activation_events(limit=3)

    assert [e.id for e in latest] == ["e4", "e3", "e2"]
    assert latest[0].label == {"en": "Title"}
    assert latest[0].severity == "error"


@pytest.mark.asyncio
async def test_activation_event_severity_may_be_null(store: AnnouncementStore) -> None:
    await store.append_activation_events([_event("e1", 0, severity=None)])

    [event] = await store.list_activation_events(limit=1)

    assert event.severity is None
