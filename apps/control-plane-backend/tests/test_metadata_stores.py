from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fred_core.common import TeamId
from fred_core.models import Base as CoreBase
from fred_core.teams.metadata_store import (
    TeamMetadataPatch,
    TeamMetadataStore,
)
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from control_plane_backend.models.base import Base
from control_plane_backend.prompts.store import (
    PromptAlreadyExistsError,
    PromptRecord,
    PromptStore,
)
from control_plane_backend.scheduler.queue_store import PurgeQueueStore
from control_plane_backend.sessions.attachment_store import (
    SessionAttachmentRecord,
    SessionAttachmentStore,
)
from control_plane_backend.sessions.store import (
    SessionMetadataRecord,
    SessionMetadataStore,
)
from control_plane_backend.teams.policy_override_store import (
    TeamPolicyOverrideStore,
)


async def _make_sqlite_engine(tmp_path: Path, filename: str) -> AsyncEngine:
    """
    Create one file-backed SQLite async engine with the control-plane schema.

    Why this helper exists:
    - store tests should exercise the real ORM tables offline, without relying
      on Postgres or hand-written DDL in every test

    How to use it:
    - pass the temporary test directory and a per-test database filename

    Example:
    - `engine = await _make_sqlite_engine(tmp_path, "sessions.sqlite3")`
    """

    db_path = tmp_path / filename
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(CoreBase.metadata.create_all)
    return engine


def test_team_metadata_patch_supports_legacy_banner_field() -> None:
    """
    Verify legacy `banner_image_url` still maps to the stored banner key field.

    Why this test exists:
    - existing callers may still send the pre-migration field name while the
      store contract has already converged on `banner_object_storage_key`

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    patch = TeamMetadataPatch(banner_image_url="teams/fredlab/banner.png")

    assert patch.to_store_values() == {
        "banner_object_storage_key": "teams/fredlab/banner.png"
    }


@pytest.mark.asyncio
async def test_team_metadata_store_empty_upsert_returns_default_without_write(
    tmp_path: Path,
) -> None:
    """
    Verify an empty team-metadata upsert returns the default projection only.

    Why this test exists:
    - no-op updates should stay cheap and must not create a DB row

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "team-empty.sqlite3")

    try:
        store = TeamMetadataStore(engine)
        result = await store.upsert(TeamId("fredlab"), TeamMetadataPatch())

        assert result.id == "fredlab"
        assert result.description is None
        assert result.is_private is True
        assert result.banner_object_storage_key is None
        assert await store.get_by_team_id(TeamId("fredlab")) is None
        assert await store.get_by_team_ids([]) == {}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_team_metadata_store_upsert_persists_and_updates_records(
    tmp_path: Path,
) -> None:
    """
    Verify team metadata persists and later updates merge on the same record.

    Why this test exists:
    - team settings such as description, privacy, and banner key are mutated
      incrementally and must round-trip through the DB store

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "team-update.sqlite3")

    try:
        store = TeamMetadataStore(engine)
        created = await store.upsert(
            TeamId("fredlab"),
            TeamMetadataPatch(
                description="Operations team",
                is_private=False,
                banner_object_storage_key="teams/fredlab/banner-v1.png",
            ),
        )
        updated = await store.upsert(
            TeamId("fredlab"),
            TeamMetadataPatch(banner_image_url="teams/fredlab/banner-v2.png"),
        )
        fetched = await store.get_by_team_ids([TeamId("fredlab"), TeamId("missing")])

        assert created.description == "Operations team"
        assert created.is_private is False
        assert created.banner_object_storage_key == "teams/fredlab/banner-v1.png"
        assert updated.description == "Operations team"
        assert updated.is_private is False
        assert updated.banner_object_storage_key == "teams/fredlab/banner-v2.png"
        assert fetched == {
            TeamId("fredlab"): updated,
        }
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_metadata_store_create_list_update_and_delete(
    tmp_path: Path,
) -> None:
    """
    Verify session metadata supports the full offline CRUD and ordering cycle.

    Why this test exists:
    - the session sidebar depends on this store for creation, recency ordering,
      activity refresh, and deletion

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "sessions.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        older = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        newer = datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc)
        newest = datetime(2026, 1, 1, 10, 10, tzinfo=timezone.utc)

        created_first = await store.create(
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("fredlab"),
                agent_instance_id="instance-1",
                user_id="alice",
                title="First chat",
                created_at=older,
                updated_at=older,
            )
        )
        created_second = await store.create(
            SessionMetadataRecord(
                session_id="session-2",
                team_id=TeamId("fredlab"),
                agent_instance_id="instance-1",
                user_id="alice",
                title="Second chat",
                created_at=newer,
                updated_at=newer,
            )
        )

        initial_list = await store.list_by_team(TeamId("fredlab"))
        updated_first = await store.update_last_activity(
            "session-1",
            TeamId("fredlab"),
            newest,
        )
        reordered_list = await store.list_by_team(TeamId("fredlab"), limit=1)
        deleted = await store.delete("session-2", TeamId("fredlab"), "alice")
        missing_delete = await store.delete("session-2", TeamId("fredlab"), "alice")

        assert created_first.session_id == "session-1"
        assert created_second.session_id == "session-2"
        assert [item.session_id for item in initial_list] == ["session-2", "session-1"]
        assert updated_first is not None
        assert updated_first.updated_at == newest.replace(tzinfo=None)
        assert [item.session_id for item in reordered_list] == ["session-1"]
        assert deleted is True
        assert missing_delete is False
        assert await store.get("session-2") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_metadata_store_delete_is_user_scoped(
    tmp_path: Path,
) -> None:
    """
    Verify session deletion is denied when the owner does not match user_id.

    Why this test exists:
    - PATCH/DELETE ownership hardening must fail closed within one team so
      users cannot remove another user's session metadata

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "sessions-delete-owned.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        await store.create(
            SessionMetadataRecord(
                session_id="session-1",
                team_id=TeamId("fredlab"),
                agent_instance_id="instance-1",
                user_id="alice",
                title="Alice session",
            )
        )

        denied = await store.delete("session-1", TeamId("fredlab"), "bob")
        allowed = await store.delete("session-1", TeamId("fredlab"), "alice")

        assert denied is False
        assert allowed is True
        assert await store.get("session-1") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_team_policy_override_store_upsert_then_get_round_trips(
    tmp_path: Path,
) -> None:
    """Verify the per-team retention override round-trips and re-upserts in place.

    Why this test exists:
    - the override is one row per team (PK = team_id); the first upsert inserts
      it, a second upsert must update the *same* row (new values, new
      ``updated_at`` / ``updated_by``) rather than create a duplicate.

    How to use it:
    - run with the offline `control-plane-backend` test suite
    """

    engine = await _make_sqlite_engine(tmp_path, "team-policy-override.sqlite3")

    try:
        store = TeamPolicyOverrideStore(engine)

        assert await store.get("swiftpost") is None

        created = await store.upsert(
            "swiftpost",
            team_delete_grace="P7D",
            max_idle="P30D",
            updated_by="alice",
        )
        fetched = await store.get("swiftpost")

        updated = await store.upsert(
            "swiftpost",
            team_delete_grace="P1D",
            max_idle=None,
            updated_by="bob",
        )
        refetched = await store.get("swiftpost")

        assert created.team_delete_grace == "P7D"
        assert created.max_idle == "P30D"
        assert created.updated_by == "alice"
        assert created.updated_at is not None

        assert fetched is not None
        assert fetched.team_delete_grace == "P7D"
        assert fetched.max_idle == "P30D"

        # Second upsert mutates the single row: new values, updated audit fields.
        assert updated.team_delete_grace == "P1D"
        assert updated.max_idle is None
        assert updated.updated_by == "bob"
        assert updated.updated_at is not None
        assert updated.updated_at > created.updated_at

        # get() reflects the latest write — still exactly one row for the team.
        assert refetched is not None
        assert refetched.team_delete_grace == "P1D"
        assert refetched.updated_by == "bob"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_metadata_soft_delete_hides_from_list_but_get_still_returns(
    tmp_path: Path,
) -> None:
    """mark_deleted hides a session from list_by_team, yet get() still returns it.

    Why this test exists:
    - the deferred-delete window (CTRLP-12 A5) soft-hides a conversation from the
      sidebar (`list_by_team` filters `deleted_at IS NULL`) while the row survives
      until erase-at-expiry. get() intentionally does NOT filter deleted_at — the
      row stays directly fetchable by id during the window (post-incident /
      evaluation read; CTRLP-12 finding 5). This is exercised at the real DB layer
      (previously only an in-memory fake covered the hide filter).
    """

    engine = await _make_sqlite_engine(tmp_path, "sessions-soft-delete.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        await store.create(
            SessionMetadataRecord(
                session_id="s1",
                team_id=TeamId("fredlab"),
                agent_instance_id="inst-1",
                user_id="alice",
                title="Chat",
            )
        )

        hidden = await store.mark_deleted(
            "s1",
            TeamId("fredlab"),
            "alice",
            datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        )

        assert hidden is True
        # Hidden from the sidebar list…
        assert await store.list_by_team(TeamId("fredlab")) == []
        # …but still directly fetchable by id during the grace window.
        still = await store.get("s1")
        assert still is not None
        assert still.session_id == "s1"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_purge_queue_enqueue_is_idempotent_for_pending_sessions(
    tmp_path: Path,
) -> None:
    """A repeated enqueue of a still-pending session must not postpone erasure.

    Why this test exists:
    - the queue PK is session_id; a naive merge() of a replayed delete would
      reset the pending row's due_at to a later time, letting an API replay push
      the scheduled erasure out indefinitely (CTRLP-12). The first pending
      entry's due_at must be preserved. A DONE row, however, may be re-scheduled.
    """

    engine = await _make_sqlite_engine(tmp_path, "purge-queue.sqlite3")

    try:
        store = PurgeQueueStore(engine)
        t1 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)  # strictly later

        await store.enqueue(
            session_id="s1", team_id="fredlab", user_id="alice", due_at=t1
        )
        # Replayed delete with a LATER due_at — must be a no-op (no postponement).
        await store.enqueue(
            session_id="s1", team_id="fredlab", user_id="alice", due_at=t2
        )

        due = await store.list_due(limit=10)
        assert len(due) == 1  # exactly one row, not duplicated
        assert due[0].due_at == t1.replace(tzinfo=None)  # original due_at kept

        # After the entry is processed (DONE), a genuinely new deferred delete for
        # the same session id may be re-scheduled.
        await store.mark_done(session_id="s1")
        await store.enqueue(
            session_id="s1", team_id="fredlab", user_id="alice", due_at=t2
        )
        rescheduled = await store.list_due(limit=10)
        assert len(rescheduled) == 1
        assert rescheduled[0].due_at == t2.replace(tzinfo=None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_attachment_store_save_list_count_and_delete(
    tmp_path: Path,
) -> None:
    """
    Verify persisted session attachments round-trip through the DB store.

    Why this test exists:
    - the chat drawer relies on the `main`-style session attachment store for
      reload-safe metadata, summary previews, and delete operations

    How to use it:
    - run with the offline `control-plane-backend` test suite
    """

    engine = await _make_sqlite_engine(tmp_path, "session-attachments.sqlite3")

    try:
        store = SessionAttachmentStore(engine)
        created_at = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)

        await store.save(
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes.md",
                mime="text/markdown",
                size_bytes=321,
                summary_md="# Notes",
                document_uid="doc-1",
                storage_key="uploads/notes.md",
                created_at=created_at,
                updated_at=created_at,
            )
        )
        await store.save(
            SessionAttachmentRecord(
                session_id="session-2",
                attachment_id="attachment-2",
                name="slides.pptx",
                mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                size_bytes=1024,
                summary_md="Slides",
                document_uid="doc-2",
            )
        )
        # Same attachment id should merge/update, matching main-branch semantics.
        await store.save(
            SessionAttachmentRecord(
                session_id="session-1",
                attachment_id="attachment-1",
                name="notes-v2.md",
                mime="text/markdown",
                size_bytes=654,
                summary_md="# Notes v2",
                document_uid="doc-1b",
                storage_key="uploads/notes-v2.md",
                created_at=created_at,
                updated_at=created_at,
            )
        )

        session_rows = await store.list_for_session("session-1")
        count = await store.count_for_sessions(["session-1", "session-2"])

        assert len(session_rows) == 1
        assert session_rows[0].name == "notes-v2.md"
        assert session_rows[0].document_uid == "doc-1b"
        assert session_rows[0].storage_key == "uploads/notes-v2.md"
        assert count == 2

        await store.delete("session-1", "attachment-1")
        assert await store.list_for_session("session-1") == []

        await store.delete_for_session("session-2")
        assert await store.count_for_sessions(["session-2"]) == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_session_metadata_store_update_last_activity_returns_none_for_missing_row(
    tmp_path: Path,
) -> None:
    """
    Verify missing sessions do not raise during last-activity refresh.

    Why this test exists:
    - control-plane receives activity refreshes after runtime turns, and stale
      or deleted session ids should degrade safely

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "sessions-missing.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        result = await store.update_last_activity(
            "missing-session",
            TeamId("fredlab"),
            datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        )

        assert result is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_replace_context_prompts_full_set_lifecycle(
    tmp_path: Path,
) -> None:
    """Verify add / reorder / remove / clear and first-attach detection (PROMPT-05).

    Why this test exists:
    - PROMPTS.md §5 makes chat context a 0..N ordered association managed by full-set
      replacement; ordering, idempotent re-send, and first-attach accounting are
      all user-visible and must hold at the store boundary.
    """

    engine = await _make_sqlite_engine(tmp_path, "ctx-prompts.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        await store.create(
            SessionMetadataRecord(
                session_id="s1",
                team_id=TeamId("fredlab"),
                agent_instance_id="inst-1",
                user_id="alice",
                title="Chat",
            )
        )

        # Initial attach in a chosen order — both ids are newly attached.
        first = await store.replace_context_prompts(
            "s1", TeamId("fredlab"), "alice", ["p2", "p1"]
        )
        assert first is not None
        record, newly = first
        assert record.context_prompt_ids == ["p2", "p1"]
        assert sorted(newly) == ["p1", "p2"]

        # Reorder + add p3: only p3 is newly attached.
        second = await store.replace_context_prompts(
            "s1", TeamId("fredlab"), "alice", ["p1", "p2", "p3"]
        )
        assert second is not None
        record, newly = second
        assert record.context_prompt_ids == ["p1", "p2", "p3"]
        assert newly == ["p3"]

        # Hydration through get() reflects the latest ordered set.
        fetched = await store.get("s1")
        assert fetched is not None
        assert fetched.context_prompt_ids == ["p1", "p2", "p3"]

        # Duplicate ids are de-duplicated, order preserved.
        third = await store.replace_context_prompts(
            "s1", TeamId("fredlab"), "alice", ["p3", "p3", "p1"]
        )
        assert third is not None
        record, newly = third
        assert record.context_prompt_ids == ["p3", "p1"]
        assert newly == []

        # Empty list clears the set.
        cleared = await store.replace_context_prompts(
            "s1", TeamId("fredlab"), "alice", []
        )
        assert cleared is not None
        assert cleared[0].context_prompt_ids == []
        refetched = await store.get("s1")
        assert refetched is not None
        assert refetched.context_prompt_ids == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_replace_context_prompts_is_owner_scoped(
    tmp_path: Path,
) -> None:
    """A non-owner cannot replace another user's chat-context prompts."""

    engine = await _make_sqlite_engine(tmp_path, "ctx-prompts-owner.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        await store.create(
            SessionMetadataRecord(
                session_id="s1",
                team_id=TeamId("fredlab"),
                agent_instance_id="inst-1",
                user_id="alice",
                title="Chat",
            )
        )

        assert (
            await store.replace_context_prompts(
                "s1", TeamId("fredlab"), "mallory", ["p1"]
            )
            is None
        )
        owned = await store.get("s1")
        assert owned is not None
        assert owned.context_prompt_ids == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_delete_session_removes_context_prompt_association(
    tmp_path: Path,
) -> None:
    """Deleting a session also removes its context-prompt association rows."""

    engine = await _make_sqlite_engine(tmp_path, "ctx-prompts-delete.sqlite3")

    try:
        store = SessionMetadataStore(engine)
        await store.create(
            SessionMetadataRecord(
                session_id="s1",
                team_id=TeamId("fredlab"),
                agent_instance_id="inst-1",
                user_id="alice",
                title="Chat",
            )
        )
        await store.replace_context_prompts(
            "s1", TeamId("fredlab"), "alice", ["p1", "p2"]
        )

        deleted = await store.delete("s1", TeamId("fredlab"), "alice")
        assert deleted is True

        # Re-creating the same session id must not resurrect stale associations.
        await store.create(
            SessionMetadataRecord(
                session_id="s1",
                team_id=TeamId("fredlab"),
                agent_instance_id="inst-1",
                user_id="alice",
                title="Chat again",
            )
        )
        reborn = await store.get("s1")
        assert reborn is not None
        assert reborn.context_prompt_ids == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_store_create_list_update_and_delete(
    tmp_path: Path,
) -> None:
    """
    Verify the prompt store supports the full offline CRUD and ordering cycle.

    Why this test exists:
    - the prompt library must be a first-class control-plane storage surface
      before any frontend prompt-management screen is built

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "prompts.sqlite3")

    try:
        store = PromptStore(engine)
        older = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
        newer = datetime(2026, 1, 1, 10, 5, tzinfo=timezone.utc)

        created = await store.create(
            PromptRecord(
                prompt_id="prompt-1",
                team_id=TeamId("personal"),
                name="Daily brief",
                description="Ops baseline",
                text="Today is {today}.",
                created_by="alice",
                created_at=older,
                updated_at=older,
            )
        )
        second = await store.create(
            PromptRecord(
                prompt_id="prompt-2",
                team_id=TeamId("personal"),
                name="Follow-up",
                description=None,
                text="Respond in {response_language}.",
                created_by="alice",
                created_at=newer,
                updated_at=newer,
            )
        )

        listed = await store.list_by_team(TeamId("personal"))
        fetched = await store.get_for_team("prompt-1", TeamId("personal"))
        updated = await store.update(
            "prompt-1",
            TeamId("personal"),
            name="Daily brief v2",
            description="Refined",
            category="writing",
            emoji=None,
            tags=[],
            text="Today is {today}. Session: {session_id}.",
        )
        deleted = await store.delete("prompt-2", TeamId("personal"))
        missing_delete = await store.delete("prompt-2", TeamId("personal"))

        assert created.name == "Daily brief"
        assert second.name == "Follow-up"
        assert [item.prompt_id for item in listed] == ["prompt-2", "prompt-1"]
        assert fetched is not None
        assert fetched.text == "Today is {today}."
        assert updated is not None
        assert updated.name == "Daily brief v2"
        assert updated.description == "Refined"
        assert updated.text == "Today is {today}. Session: {session_id}."
        assert deleted is True
        assert missing_delete is False
        assert await store.get("prompt-2") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_prompt_store_rejects_duplicate_name_within_same_team(
    tmp_path: Path,
) -> None:
    """
    Verify prompt names stay unique per team while different teams may reuse them.

    Why this test exists:
    - the prompt library must avoid ambiguous team-local prompt labels without
      imposing a global naming registry

    How to use it:
    - run with the offline `control-plane-backend` test suite

    Example:
    - `pytest tests/test_metadata_stores.py -q`
    """

    engine = await _make_sqlite_engine(tmp_path, "prompts-unique.sqlite3")

    try:
        store = PromptStore(engine)
        await store.create(
            PromptRecord(
                prompt_id="prompt-1",
                team_id=TeamId("fredlab"),
                name="Shared name",
                description=None,
                text="Today is {today}.",
                created_by="alice",
            )
        )
        await store.create(
            PromptRecord(
                prompt_id="prompt-2",
                team_id=TeamId("other-team"),
                name="Shared name",
                description=None,
                text="Respond in {response_language}.",
                created_by="bob",
            )
        )

        with pytest.raises(PromptAlreadyExistsError):
            await store.create(
                PromptRecord(
                    prompt_id="prompt-3",
                    team_id=TeamId("fredlab"),
                    name="Shared name",
                    description="duplicate",
                    text="Session is {session_id}.",
                    created_by="alice",
                )
            )
    finally:
        await engine.dispose()
