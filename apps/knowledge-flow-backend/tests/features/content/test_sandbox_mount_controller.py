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
    )
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
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(uid="u1", username="u1", roles=[])
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
        selected = await client.post(binding, json=payload, headers={"X-Fred-Sandbox-Bind": bind_signature})
        assert selected.status_code == 200 and selected.json()["path"] == "/inputs/corpus/doc-1/report.txt"
        assert (await client.request("PROPFIND", root)).status_code == 401
        headers = {"Authorization": f"Bearer {bearer}"}
        listing = await client.request("PROPFIND", root, headers={**headers, "Depth": "1"})
        assert listing.status_code == 207
        assert "corpus/" in listing.text
        store.sources.append(MountedSource("corpus/doc-2/new.txt", "corpus", "doc-2", "new.txt", 6))
        refreshed = await client.request("PROPFIND", root, headers={**headers, "Depth": "1"})
        second_level = await client.request("PROPFIND", root + "corpus/", headers={**headers, "Depth": "1"})
        assert refreshed.status_code == 207 and "doc-2/" in second_level.text
        result = await client.get(file_url, headers={**headers, "Range": "bytes=1-3"})
        assert result.status_code == 206 and result.content == b"bcd"
        assert store.reserved == [3]
        assert (await client.put(file_url, headers=headers, content=b"overwrite")).status_code == 405
        assert (await client.delete(f"/sandbox-mount/views/{KEY}", headers={"Authorization": f"Bearer {revoke}"})).status_code == 204
        assert (await client.get(file_url, headers=headers)).status_code == 404
