from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fred_core import KeycloakUser, get_current_user

from knowledge_flow_backend.features.content.sandbox_mount_controller import SandboxMountController
from knowledge_flow_backend.features.content.sandbox_scope import AuthorizedCorpusSource
from knowledge_flow_backend.features.content.sandbox_views import MountedSource

KEY = "a" * 64
SECRET = "gateway-secret-" + "x" * 32  # pragma: allowlist secret


class _Store:
    def __init__(self):
        self.sources = [MountedSource("corpus/doc-1/report.txt", "corpus", "doc-1", "report.txt", 6)]
        self.revoked = False
        self.reserved = []
        self.page_count = 1

    async def list_sources(self, key):
        assert key == KEY
        if self.revoked:
            return None, []
        return SimpleNamespace(session_id="chat-1", user_id="u1", team_id="team-1"), self.sources

    async def _check_session(self, session_id, user_id, team_id):
        assert (session_id, user_id, team_id) == ("chat-1", "u1", "team-1")

    async def reserve_bytes(self, key, count):
        self.reserved.append(count)

    async def revoke(self, key):
        self.revoked = True

    async def bind_corpus(self, **kwargs):
        assert kwargs["session_id"] == "chat-1"
        return self.sources[0]

    async def ensure_view(self, **kwargs):
        assert kwargs["session_id"] == "chat-1"

    async def corpus_sources(self, user, team_id, **kwargs):
        return self.sources

    async def corpus_libraries(self, user, team_id, **kwargs):
        return {"team-tag"}

    async def corpus_page_count(self, user, team_id, tag_id, **kwargs):
        assert tag_id == "team-tag"
        return self.page_count

    async def corpus_page(self, user, team_id, tag_id, page, *, base_path, context):
        assert (tag_id, page) == ("team-tag", 0)
        return [
            MountedSource(
                f"{base_path}/{item.uid}--{item.name}",
                "corpus",
                item.uid,
                item.name,
                item.size,
            )
            for item in self.sources
        ], len(self.sources)

    async def attachment_sources(self, session_id, user_id):
        return []


@pytest.mark.asyncio
async def test_webdav_read_is_scoped_read_only_and_revocable(monkeypatch) -> None:
    store = _Store()

    async def active(user_id):
        assert user_id == "u1"

    async def team_read(user, permission, team_id):
        assert (user.uid, team_id) == ("u1", "team-1")

    async def authorize(user, team_id, uid, **kwargs):
        assert (user.uid, team_id) == ("u1", "team-1")
        return AuthorizedCorpusSource(uid, "report.txt" if uid == "doc-1" else "new.txt", 6)

    context = SimpleNamespace(
        get_pg_async_engine=lambda: None,
        get_rebac_engine=lambda: SimpleNamespace(
            require_active_account=active,
            check_user_team_permission_or_raise=team_read,
        ),
        get_content_store=lambda: SimpleNamespace(get_content_range=lambda uid, start, length: BytesIO(b"abcdef"[start : start + length])),
        get_metadata_store=lambda: SimpleNamespace(get_metadata_by_uid=lambda uid: _metadata(uid)),
    )

    async def _metadata(uid):
        return SimpleNamespace(tags=SimpleNamespace(tag_ids=["team-tag"]))

    monkeypatch.setenv("SANDBOX_FILE_GATEWAY_SECRET", SECRET)
    monkeypatch.setattr(
        "knowledge_flow_backend.features.content.sandbox_mount_controller.ApplicationContext.get_instance",
        lambda: context,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.content.sandbox_mount_controller.SandboxViewStore",
        lambda engine: store,
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.features.content.sandbox_mount_controller.authorize_corpus_source",
        authorize,
    )
    app = FastAPI()
    bind_router = APIRouter()
    mount_router = APIRouter()
    SandboxMountController(bind_router, mount_router)
    app.include_router(bind_router)
    app.include_router(mount_router)

    async def fake_user():
        return KeycloakUser(uid="u1", username="u1", roles=[])

    app.dependency_overrides[get_current_user] = fake_user
    import hashlib
    import hmac

    bearer = hmac.new(SECRET.encode(), b"fred-sandbox-files-v1\0" + KEY.encode(), hashlib.sha256).hexdigest()
    revoke = hmac.new(SECRET.encode(), b"fred-sandbox-files-revoke-v1\0" + KEY.encode(), hashlib.sha256).hexdigest()
    root = f"/sandbox-mount/{KEY}/"
    file_url = root + "corpus/doc-1/report.txt"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        binding = f"/sandbox-mount/views/{KEY}/corpus"
        payload = {"session_id": "chat-1", "team_id": "team-1", "document_uid": "doc-1"}
        assert (await client.post(binding, json=payload)).status_code == 401
        bind_signature = hmac.new(
            SECRET.encode(),
            b"\0".join((b"fred-sandbox-files-bind-v1", KEY.encode(), b"chat-1", b"u1", b"team-1")),
            hashlib.sha256,
        ).hexdigest()
        opened = await client.post(
            f"/sandbox-mount/views/{KEY}",
            json={"session_id": "chat-1", "team_id": "team-1"},
            headers={"X-Fred-Sandbox-Bind": bind_signature},
        )
        assert opened.status_code == 200 and opened.json()["path"] == "/inputs"
        selected = await client.post(binding, json=payload, headers={"X-Fred-Sandbox-Bind": bind_signature})
        assert selected.status_code == 200 and selected.json()["path"] == "/inputs/corpus/doc-1/report.txt"
        assert (await client.request("PROPFIND", root)).status_code == 401
        headers = {"Authorization": f"Bearer {bearer}"}
        listing = await client.request("PROPFIND", root, headers={**headers, "Depth": "1"})
        assert listing.status_code == 207
        assert "corpus/" in listing.text and "attachments/" in listing.text
        store.sources.append(MountedSource("corpus/doc-2/new.txt", "corpus", "doc-2", "new.txt", 6))
        refreshed = await client.request("PROPFIND", root, headers={**headers, "Depth": "1"})
        second_level = await client.request("PROPFIND", root + "corpus/", headers={**headers, "Depth": "1"})
        libraries = await client.request("PROPFIND", root + "corpus/libraries/", headers={**headers, "Depth": "1"})
        pages = await client.request("PROPFIND", root + "corpus/libraries/team-tag/", headers={**headers, "Depth": "1"})
        page_root = root + "corpus/libraries/team-tag/pages/"
        page_list = await client.request("PROPFIND", page_root, headers={**headers, "Depth": "1"})
        inner = page_root + "block-00/block-00/"
        inner_list = await client.request("PROPFIND", inner, headers={**headers, "Depth": "1"})
        page = await client.request("PROPFIND", inner + "page-0000/", headers={**headers, "Depth": "1"})
        assert refreshed.status_code == 207 and "libraries/" in second_level.text
        assert "team-tag/" in libraries.text and "pages/" in pages.text
        assert "block-00/" in page_list.text and "page-0000/" in inner_list.text
        assert "doc-2--new.txt" in page.text
        store.page_count = 2
        expanded = await client.request("PROPFIND", inner, headers={**headers, "Depth": "1"})
        assert "page-0001/" in expanded.text
        assert (await client.request("PROPFIND", inner + "page-00001/", headers=headers)).status_code == 404
        assert (await client.request("PROPFIND", inner + "page-999999999999999999/", headers=headers)).status_code == 404
        store.page_count = 100
        stable_path = inner + "page-0000/doc-1--report.txt"
        assert (await client.get(stable_path, headers=headers)).status_code == 200
        store.page_count = 101
        assert (await client.get(stable_path, headers=headers)).status_code == 200
        grouped = await client.request("PROPFIND", page_root + "block-00/", headers={**headers, "Depth": "1"})
        assert "block-00/" in grouped.text and "block-01/" in grouped.text
        group_page = await client.request("PROPFIND", inner + "page-0000/", headers={**headers, "Depth": "1"})
        assert group_page.status_code == 207 and "doc-1--report.txt" in group_page.text
        assert (await client.request("PROPFIND", page_root + "block-00/block-01/page-0000/", headers=headers)).status_code == 404
        store.page_count = 10001
        nested = await client.request("PROPFIND", page_root, headers={**headers, "Depth": "1"})
        assert nested.status_code == 207 and "block-01/" in nested.text
        assert (await client.request("PROPFIND", page_root + "block-01/block-00/page-0000/", headers=headers)).status_code == 404
        store.page_count = 101
        result = await client.get(file_url, headers={**headers, "Range": "bytes=1-3"})
        assert result.status_code == 206 and result.content == b"bcd"
        paged = await client.get(stable_path, headers=headers)
        assert paged.status_code == 200 and paged.content == b"abcdef"
        assert store.reserved == [6, 6, 3, 6]
        assert (await client.put(file_url, headers=headers, content=b"overwrite")).status_code == 405
        assert (await client.delete(f"/sandbox-mount/views/{KEY}", headers={"Authorization": f"Bearer {revoke}"})).status_code == 204
        assert (await client.get(file_url, headers=headers)).status_code == 404
