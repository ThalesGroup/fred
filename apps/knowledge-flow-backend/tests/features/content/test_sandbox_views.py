from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fred_core.common import OwnerFilter
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.content.sandbox_scope import AuthorizedCorpusSource
from knowledge_flow_backend.features.content.sandbox_views import MAX_VIEW_REQUESTS_PER_MINUTE, MountedSource, SandboxViewStore
from knowledge_flow_backend.models.sandbox_view_models import SandboxAttachmentOriginalRow, SandboxViewRow

KEY = "a" * 64
USER = KeycloakUser(uid="user-1", username="user-1", roles=[])


@pytest_asyncio.fixture
async def store():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(SandboxViewRow.__table__.create)
        await connection.run_sync(SandboxAttachmentOriginalRow.__table__.create)
        await connection.execute(text("CREATE TABLE session_metadata (session_id TEXT PRIMARY KEY, user_id TEXT, team_id TEXT, deleted_at TIMESTAMP)"))
        await connection.execute(text("CREATE TABLE session_attachments (session_id TEXT, attachment_id TEXT, name TEXT, document_uid TEXT)"))
        await connection.execute(text("INSERT INTO session_metadata (session_id, user_id, team_id) VALUES ('chat-1', 'user-1', 'team-1')"))
    yield SandboxViewStore(engine)
    await engine.dispose()


@pytest.mark.asyncio
async def test_view_rejects_cross_user_or_cross_team_binding(store, monkeypatch) -> None:
    async def authorize(user, team_id, uid, **kwargs):
        return AuthorizedCorpusSource(uid, "report.txt", 5)

    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.authorize_corpus_source", authorize)
    with pytest.raises(PermissionError):
        await store.bind_corpus(
            key=KEY,
            session_id="chat-1",
            team_id="other-team",
            user=USER,
            document_uid="doc-1",
        )
    with pytest.raises(PermissionError):
        await store.bind_corpus(
            key=KEY,
            session_id="chat-1",
            team_id="team-1",
            user=KeycloakUser(uid="other-user", username="other-user", roles=[]),
            document_uid="doc-1",
        )


@pytest.mark.asyncio
async def test_open_view_requires_conversation_owner_and_starts_empty(store) -> None:
    async def active(user_id):
        assert user_id == USER.uid

    async def team_read(user, permission, team_id):
        assert (user.uid, team_id) == (USER.uid, "team-1")

    context = SimpleNamespace(
        get_rebac_engine=lambda: SimpleNamespace(
            require_active_account=active,
            check_user_team_permission_or_raise=team_read,
        )
    )
    with pytest.raises(PermissionError):
        await store.ensure_view(key=KEY, session_id="chat-1", team_id="other-team", user=USER, context=context)
    await store.ensure_view(key=KEY, session_id="chat-1", team_id="team-1", user=USER, context=context)
    row, sources = await store.list_sources(KEY)
    assert row.user_id == USER.uid
    assert sources == []


@pytest.mark.asyncio
async def test_reopening_view_preserves_owner_and_existing_sources(store) -> None:
    source = MountedSource(path="corpus/doc-1/report.txt", kind="corpus", uid="doc-1", name="report.txt", size=5)
    await store._bind(KEY, "chat-1", "team-1", USER.uid, source)
    await store._bind(KEY, "chat-1", "team-1", USER.uid, None)
    row, sources = await store.list_sources(KEY)
    assert row is not None and row.session_id == "chat-1"
    assert sources == [source]

    with pytest.raises(PermissionError):
        await store._bind(KEY, "other-chat", "team-1", USER.uid, None)
    with pytest.raises(PermissionError):
        await store._bind(KEY, "chat-1", "other-team", USER.uid, None)


@pytest.mark.asyncio
async def test_attachment_listing_updates_and_excludes_other_users(store) -> None:
    async with store._sessions() as session:
        async with session.begin():
            session.add_all(
                [
                    SandboxAttachmentOriginalRow(
                        document_uid="own-doc",
                        session_id="chat-1",
                        user_id=USER.uid,
                        name="own.xlsx",
                        size=128,
                        object_key="own-key",
                    ),
                    SandboxAttachmentOriginalRow(
                        document_uid="other-doc",
                        session_id="chat-1",
                        user_id="other-user",
                        name="other.xlsx",
                        size=128,
                        object_key="other-key",
                    ),
                ]
            )
            await session.execute(text("INSERT INTO session_attachments VALUES ('chat-1', 'own', 'own.xlsx', 'own-doc')"))
            await session.execute(text("INSERT INTO session_attachments VALUES ('chat-1', 'other', 'other.xlsx', 'other-doc')"))
    sources = await store.attachment_sources("chat-1", USER.uid)
    assert [item.path for item in sources] == ["attachments/own/own.xlsx"]
    assert await store.attachment_sources("another-chat", USER.uid) == []


@pytest.mark.asyncio
async def test_corpus_listing_uses_team_scoped_tags_and_document_reads(store, monkeypatch) -> None:
    calls = []

    async def tags(user, team_id, *, context):
        calls.append((user.uid, OwnerFilter.TEAM, team_id))
        return {"team-tag"}

    class Metadata:
        async def filter_readable_document_uids(self, user, uids):
            assert user.uid == USER.uid and uids == ["allowed", "denied", "fast"]
            return {"allowed", "fast"}

    async def browse(tag_id, *, offset, limit, sort_by, sort_order):
        assert (tag_id, offset, limit, sort_by, sort_order) == ("team-tag", 0, 128, "created", "asc")
        return [
            SimpleNamespace(document_uid=uid, document_name="report.txt", source=SimpleNamespace(source_tag=source))
            for uid, source in (("allowed", "upload"), ("denied", "upload"), ("fast", "fast_ingest"))
        ], 3

    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.scoped_authorized_tag_ids", tags)
    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.MetadataService", Metadata)
    context = SimpleNamespace(
        get_metadata_store=lambda: SimpleNamespace(browse_metadata_in_tag=browse),
        get_content_store=lambda: SimpleNamespace(
            get_file_metadata=lambda uid: SimpleNamespace(size=12),
        ),
    )
    sources, total = await store.corpus_page(USER, "team-1", "team-tag", 0, base_path="corpus/libraries/team-tag/pages/page-0000", context=context)
    assert total == 3
    assert [item.path for item in sources] == ["corpus/libraries/team-tag/pages/page-0000/allowed--report.txt"]
    assert calls == [(USER.uid, OwnerFilter.TEAM, "team-1")]


@pytest.mark.asyncio
async def test_corpus_page_bounds_document_reads(store, monkeypatch) -> None:
    async def tags(*_, **__):
        return {"team-tag"}

    class Metadata:
        async def filter_readable_document_uids(self, user, uids):
            assert len(uids) == 128
            return set(uids)

    async def browse(tag_id, *, offset, limit, sort_by, sort_order):
        assert (offset, limit) == (128, 128)
        return [
            SimpleNamespace(
                document_uid=f"doc-{index:03}",
                document_name="report.txt",
                source=SimpleNamespace(source_tag="upload"),
            )
            for index in range(128, 256)
        ], 300

    reads = []

    def metadata(uid):
        reads.append(uid)
        return SimpleNamespace(size=12)

    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.scoped_authorized_tag_ids", tags)
    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.MetadataService", Metadata)
    context = SimpleNamespace(
        get_metadata_store=lambda: SimpleNamespace(browse_metadata_in_tag=browse),
        get_content_store=lambda: SimpleNamespace(get_file_metadata=metadata),
    )
    sources, total = await store.corpus_page(USER, "team-1", "team-tag", 1, base_path="corpus/libraries/team-tag/pages/page-0001", context=context)
    assert total == 300 and len(sources) == 128
    assert len(reads) == 128 and reads[0] == "doc-128" and reads[-1] == "doc-255"


@pytest.mark.asyncio
async def test_new_selection_appears_in_existing_view_and_revoke_removes_it(store, monkeypatch) -> None:
    async def authorize(user, team_id, uid, **kwargs):
        return AuthorizedCorpusSource(uid, f"{uid}.txt", 5)

    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.authorize_corpus_source", authorize)
    await store.bind_corpus(key=KEY, session_id="chat-1", team_id="team-1", user=USER, document_uid="one")
    _, first = await store.list_sources(KEY)
    await store.bind_corpus(key=KEY, session_id="chat-1", team_id="team-1", user=USER, document_uid="two")
    _, second = await store.list_sources(KEY)
    assert {source.path for source in first} == {"corpus/one/one.txt"}
    assert {source.path for source in second} == {"corpus/one/one.txt", "corpus/two/two.txt"}
    await store.revoke(KEY)
    assert (await store.list_sources(KEY))[1] == []


@pytest.mark.asyncio
async def test_attachment_requires_persisted_session_and_original_uploader(store) -> None:
    async with store._sessions() as session:
        async with session.begin():
            session.add(
                SandboxAttachmentOriginalRow(
                    document_uid="attachment-doc",
                    session_id="chat-1",
                    user_id="other-user",
                    name="sheet.xlsx",
                    size=128,
                    object_key="sandbox-attachments/attachment-doc/original",
                )
            )
            await session.execute(text("INSERT INTO session_attachments VALUES ('chat-1', 'attachment-1', 'sheet.xlsx', 'attachment-doc')"))
    context = SimpleNamespace(get_rebac_engine=lambda: SimpleNamespace(require_active_account=_active))
    with pytest.raises(FileNotFoundError):
        await store.bind_attachment(
            key=KEY,
            session_id="chat-1",
            team_id="team-1",
            user=USER,
            attachment_id="attachment-1",
            context=context,
        )
    async with store._sessions() as session:
        async with session.begin():
            row = await session.get(SandboxAttachmentOriginalRow, "attachment-doc")
            row.user_id = USER.uid
    source = await store.bind_attachment(
        key=KEY,
        session_id="chat-1",
        team_id="team-1",
        user=USER,
        attachment_id="attachment-1",
        context=context,
    )
    assert source.path == "attachments/attachment-1/sheet.xlsx"


@pytest.mark.asyncio
async def test_original_delete_is_idempotent_after_object_disappears(store) -> None:
    async with store._sessions() as session:
        async with session.begin():
            session.add(
                SandboxAttachmentOriginalRow(
                    document_uid="attachment-doc",
                    session_id="chat-1",
                    user_id=USER.uid,
                    name="sheet.xlsx",
                    size=128,
                    object_key="sandbox-attachments/attachment-doc/original",
                )
            )

    def missing_object(key):
        raise FileNotFoundError(key)

    context = SimpleNamespace(get_content_store=lambda: SimpleNamespace(delete_object=missing_object))
    await store.delete_attachment_original(
        context=context,
        document_uid="attachment-doc",
        user_id=USER.uid,
        platform_bypass=False,
    )
    await store.delete_attachment_original(
        context=context,
        document_uid="attachment-doc",
        user_id=USER.uid,
        platform_bypass=False,
    )
    async with store._sessions() as session:
        assert await session.get(SandboxAttachmentOriginalRow, "attachment-doc") is None


@pytest.mark.asyncio
async def test_view_request_rate_is_bounded(store, monkeypatch) -> None:
    async def authorize(user, team_id, uid, **kwargs):
        return AuthorizedCorpusSource(uid, "report.txt", 5)

    monkeypatch.setattr("knowledge_flow_backend.features.content.sandbox_views.authorize_corpus_source", authorize)
    await store.bind_corpus(key=KEY, session_id="chat-1", team_id="team-1", user=USER, document_uid="doc-1")
    async with store._sessions() as session:
        async with session.begin():
            row = await session.get(SandboxViewRow, KEY)
            row.request_window_count = MAX_VIEW_REQUESTS_PER_MINUTE
    with pytest.raises(PermissionError, match="request rate"):
        await store.list_sources(KEY)
    async with store._sessions() as session:
        async with session.begin():
            row = await session.get(SandboxViewRow, KEY)
            row.request_window_started_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    assert (await store.list_sources(KEY))[1][0].uid == "doc-1"


async def _active(user_id: str) -> None:
    assert user_id == USER.uid
