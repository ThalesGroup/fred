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

import pytest
import pytest_asyncio
from control_plane_backend.announcements.store import AnnouncementStore
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
        enabled=True,
        dismissible=False,
        content_version=7,
        updated_by="other@example.com",
    )

    assert updated is not None
    assert updated.severity == "error"
    assert updated.title == {"en": "New"}
    assert updated.description_long == {"en": "New long"}
    assert updated.enabled is True
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
            enabled=False,
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
            announcement_id="nope", enabled=True, content_version=1, updated_by=None
        )
        is None
    )


@pytest.mark.asyncio
async def test_delete_removes_the_row_and_reports_whether_it_did(
    store: AnnouncementStore,
) -> None:
    await _make(store, "a1")

    assert await store.delete("a1") is True
    assert await store.get("a1") is None
    assert await store.delete("a1") is False
