from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import pytest_asyncio
from fred_pod.security.structure import KeycloakUser
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from knowledge_flow_backend.features.content.sandbox_scope import AuthorizedCorpusSource
from knowledge_flow_backend.features.content.sandbox_views import MAX_VIEW_REQUESTS_PER_MINUTE, SandboxViewStore
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
