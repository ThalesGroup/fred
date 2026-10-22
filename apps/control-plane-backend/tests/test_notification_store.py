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

"""Notification store: dedupe by group, resolve, caller scope, expiry."""

from __future__ import annotations

from datetime import timedelta

import pytest
import pytest_asyncio
from control_plane_backend.models.base import utcnow
from control_plane_backend.models.notification_models import NotificationRow
from control_plane_backend.notifications.store import (
    NotificationDraft,
    NotificationStore,
    PageCursor,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine


@pytest_asyncio.fixture
async def store(control_plane_sql_engine: AsyncEngine) -> NotificationStore:
    return NotificationStore(control_plane_sql_engine)


def _draft(
    recipient: str = "alice",
    group: str = "agent_republish:e1",
    *,
    editor: str = "Bob",
    team: str | None = "alpha",
) -> NotificationDraft:
    return NotificationDraft(
        recipient_id=recipient,
        type="agent.republish_needed",
        group_key=group,
        payload={"editor_name": editor},
        team_id=team,
    )


async def _expire(engine: AsyncEngine, notification_id: str) -> None:
    async with engine.begin() as conn:
        await conn.execute(
            update(NotificationRow)
            .where(NotificationRow.id == notification_id)
            .values(expires_at=utcnow() - timedelta(seconds=1))
        )


async def _only(store: NotificationStore, recipient: str = "alice"):
    rows, _ = await store.list_page(recipient, limit=50)
    assert len(rows) == 1
    return rows[0]


@pytest.mark.asyncio
async def test_a_repeat_emission_updates_the_payload_without_rebadging(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft(editor="Bob")])
    first = await _only(store)
    assert await store.mark_seen("alice", first.id)
    assert await store.mark_read("alice", first.id)

    await store.upsert([_draft(editor="Carol")])

    again = await _only(store)
    assert again.id == first.id
    assert again.payload == {"editor_name": "Carol"}
    assert again.seen_at is not None and again.read_at is not None
    assert await store.unseen_count("alice") == 0


@pytest.mark.asyncio
async def test_one_statement_may_carry_the_same_subject_twice(
    store: NotificationStore,
) -> None:
    assert await store.upsert([_draft(editor="Bob"), _draft(editor="Carol")]) == 1
    assert (await _only(store)).payload == {"editor_name": "Carol"}


@pytest.mark.asyncio
async def test_a_resolved_group_accepts_a_new_notification(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft("alice"), _draft("dave")])
    await store.resolve(
        ["agent_republish:e1"], actor_uid="dave", actor_name="Dave", outcome="done"
    )

    handled = await _only(store, "alice")
    assert handled.handled_by == "dave" and handled.handled_by_name == "Dave"
    assert handled.handled_outcome == "done"
    # The actor's own row is gone.
    assert (await store.list_page("dave", limit=50))[0] == []

    await store.upsert([_draft("alice")])
    rows, _ = await store.list_page("alice", limit=50)
    assert len(rows) == 2
    assert [row.handled_at is None for row in rows] == [True, False]


@pytest.mark.asyncio
async def test_resolving_without_an_actor_marks_every_row_handled(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft("alice")])
    await store.resolve(
        ["agent_republish:e1"], actor_uid=None, actor_name=None, outcome="removed"
    )
    assert (await _only(store)).handled_outcome == "removed"


@pytest.mark.asyncio
async def test_every_caller_query_is_scoped_to_the_recipient(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft("alice"), _draft("bob")])
    alice = await _only(store, "alice")

    assert not await store.mark_read("bob", alice.id)
    assert not await store.mark_seen("bob", alice.id)
    assert not await store.delete("bob", alice.id)
    await store.delete_all("bob")

    still = await _only(store, "alice")
    assert still.read_at is None and still.seen_at is None
    assert await store.unseen_count("alice") == 1


@pytest.mark.asyncio
async def test_expired_rows_are_neither_listed_counted_nor_changed(
    store: NotificationStore, control_plane_sql_engine: AsyncEngine
) -> None:
    await store.upsert([_draft()])
    row = await _only(store)
    await _expire(control_plane_sql_engine, row.id)

    assert (await store.list_page("alice", limit=50))[0] == []
    assert await store.unseen_count("alice") == 0
    assert not await store.mark_read("alice", row.id)
    assert not await store.delete("alice", row.id)


@pytest.mark.asyncio
async def test_an_expired_open_row_is_replaced_by_a_new_emission(
    store: NotificationStore, control_plane_sql_engine: AsyncEngine
) -> None:
    await store.upsert([_draft()])
    old = await _only(store)
    await _expire(control_plane_sql_engine, old.id)

    await store.upsert([_draft(editor="Carol")])

    fresh = await _only(store)
    assert fresh.id != old.id and fresh.seen_at is None
    assert await store.unseen_count("alice") == 1


@pytest.mark.asyncio
async def test_pages_are_newest_first_with_a_cursor(store: NotificationStore) -> None:
    for index in range(5):
        await store.upsert([_draft(group=f"g{index}")])

    first, cursor = await store.list_page("alice", limit=2)
    assert cursor is not None
    second, cursor2 = await store.list_page(
        "alice", limit=2, before=PageCursor.decode(cursor.encode())
    )
    third, cursor3 = await store.list_page("alice", limit=2, before=cursor2)

    groups = [row.group_key for row in [*first, *second, *third]]
    assert groups == ["g4", "g3", "g2", "g1", "g0"]
    assert cursor3 is None


def test_a_malformed_cursor_is_refused() -> None:
    for value in ("", "123", "abc.id", f"{10**30}.id"):
        with pytest.raises(ValueError):
            PageCursor.decode(value)


@pytest.mark.asyncio
async def test_seen_stops_at_the_listed_notification(store: NotificationStore) -> None:
    await store.upsert([_draft(group="old")])
    listed = await _only(store)
    await store.upsert([_draft(group="arrived-later")])

    assert await store.mark_seen("alice", listed.id)

    assert await store.unseen_count("alice") == 1
    rows, _ = await store.list_page("alice", limit=50)
    assert {row.group_key: row.seen_at is None for row in rows} == {
        "arrived-later": True,
        "old": False,
    }


@pytest.mark.asyncio
async def test_reading_a_notification_also_marks_it_seen(
    store: NotificationStore,
) -> None:
    await store.upsert([_draft()])
    row = await _only(store)

    assert await store.mark_read("alice", row.id)

    read = await _only(store)
    assert read.read_at is not None and read.seen_at is not None


@pytest.mark.asyncio
async def test_delete_expired_is_bounded(
    store: NotificationStore, control_plane_sql_engine: AsyncEngine
) -> None:
    for index in range(3):
        await store.upsert([_draft(group=f"g{index}")])
    await store.upsert([_draft(group="live")])
    rows, _ = await store.list_page("alice", limit=50)
    for row in rows:
        if row.group_key != "live":
            await _expire(control_plane_sql_engine, row.id)

    assert await store.delete_expired(limit=2) == 2
    assert await store.delete_expired(limit=2) == 1
    assert await store.delete_expired(limit=2) == 0
    assert (await _only(store)).group_key == "live"


@pytest.mark.asyncio
async def test_user_and_team_deletion_remove_their_rows(
    store: NotificationStore,
) -> None:
    await store.upsert(
        [
            _draft("alice", "a", team="alpha"),
            _draft("alice", "b", team="beta"),
            _draft("bob", "c", team="beta"),
        ]
    )

    await store.delete_for_team("beta")
    assert [row.group_key for row in (await store.list_page("alice", limit=50))[0]] == [
        "a"
    ]
    assert (await store.list_page("bob", limit=50))[0] == []

    await store.delete_for_user("alice")
    assert await store.unseen_count("alice") == 0


@pytest.mark.asyncio
async def test_leaving_a_team_removes_only_that_members_rows_about_it(
    store: NotificationStore,
) -> None:
    await store.upsert(
        [
            _draft("alice", "a", team="alpha"),
            _draft("alice", "b", team="beta"),
            _draft("bob", "c", team="alpha"),
        ]
    )

    await store.delete_for_member("alice", "alpha")

    assert [row.group_key for row in (await store.list_page("alice", limit=50))[0]] == [
        "b"
    ]
    assert (await _only(store, "bob")).group_key == "c"
