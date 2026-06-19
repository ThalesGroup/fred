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
from control_plane_backend.sessions.attachment_store import (
    SessionAttachmentRecord,
    SessionAttachmentStore,
)
from control_plane_backend.sessions.store import (
    SessionMetadataRecord,
    SessionMetadataStore,
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
    - RFC Part 3 makes chat context a 0..N ordered association managed by full-set
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

        assert await store.delete("s1", TeamId("fredlab"), "alice") is True

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
