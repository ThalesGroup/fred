from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from fred_core import AuthorizationError, KeycloakUser
from fred_core.security.models import Resource

from knowledge_flow_backend.features.filesystem import mcp_fs_controller as controller_module
from knowledge_flow_backend.features.filesystem.mcp_fs_controller import McpFilesystemController
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import FileReadPage


def _user() -> KeycloakUser:
    return KeycloakUser(
        uid="u-1",
        username="tester",
        email="tester@example.com",
        roles=["admin"],
    )


class _ServiceStub:
    async def read_file(self, user, path, *, offset=0, limit=None, max_chars=None):
        del user, path, offset, limit, max_chars
        raise FileNotFoundError("Path not found")

    async def read_file_page(self, user, path, *, offset=0, limit=None, max_chars=None):
        del user, path, offset, limit, max_chars
        raise FileNotFoundError("Path not found")

    async def ls(self, user, path="/"):
        del user, path
        return []

    async def stat(self, user, path):
        del user, path
        raise FileNotFoundError("Path not found")

    async def write(self, user, path, data):
        del user, path, data
        return None

    async def read_bytes(self, user, path):
        del user, path
        raise FileNotFoundError("Path not found")

    async def write_bytes(self, user, path, data):
        del user, path, data
        return None

    async def delete(self, user, path):
        del user, path
        return None

    async def edit_file(self, user, path, *, old_string, new_string, replace_all=False):
        del user, path, old_string, new_string, replace_all
        return {"path": "/workspace/report.md", "occurrences": 1}

    async def glob(self, user, pattern, path="/"):
        del user, pattern, path
        return []

    async def grep(self, user, pattern, path="/"):
        del user, pattern, path
        return []

    async def mkdir(self, user, path):
        del user, path
        return None


def _build_filesystem_app(monkeypatch, service: object | None = None) -> TestClient:
    router = APIRouter(prefix="/knowledge-flow/v1")
    monkeypatch.setattr(controller_module.McpFilesystemController, "__init__", _controller_init(service or _ServiceStub()))
    McpFilesystemController(router)
    app = FastAPI()
    app.dependency_overrides[controller_module.get_current_user] = _user
    app.include_router(router)
    return TestClient(app)


def _controller_init(service: object):
    def _init(self, router: APIRouter):
        self.service = service
        self._register_routes(router)

    return _init


def test_fs_cat_returns_400_for_limit_above_max(app_context, monkeypatch) -> None:
    service = _ServiceStub()

    async def fake_read_file(user, path, *, offset=0, limit=None, max_chars=None):
        del user, path, offset, max_chars
        if limit == 501:
            raise ValueError("limit must be <= 500")
        return ""

    service.read_file = fake_read_file

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get("/knowledge-flow/v1/fs/cat/workspace/report.md", params={"limit": 501})

    assert response.status_code == 400
    assert "limit must be <= 500" in response.text


def test_fs_cat_returns_400_for_max_chars_above_max(app_context, monkeypatch) -> None:
    service = _ServiceStub()

    async def fake_read_file(user, path, *, offset=0, limit=None, max_chars=None):
        del user, path, offset, limit
        if max_chars == 50001:
            raise ValueError("max_chars must be <= 50000")
        return ""

    service.read_file = fake_read_file

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get("/knowledge-flow/v1/fs/cat/workspace/report.md", params={"max_chars": 50001})

    assert response.status_code == 400
    assert "max_chars must be <= 50000" in response.text


def test_fs_cat_returns_422_for_negative_offset(app_context, monkeypatch) -> None:
    with _build_filesystem_app(monkeypatch) as client:
        response = client.get("/knowledge-flow/v1/fs/cat/workspace/report.md", params={"offset": -1})

    assert response.status_code == 422


def test_fs_cat_returns_404_for_unknown_path(app_context, monkeypatch) -> None:
    with _build_filesystem_app(monkeypatch) as client:
        response = client.get("/knowledge-flow/v1/fs/cat/workspace/missing.txt")

    assert response.status_code == 404


def test_fs_page_returns_403_for_permission_error(app_context, monkeypatch) -> None:
    service = _ServiceStub()

    async def fake_read_file_page(user, path, *, offset=0, limit=None, max_chars=None):
        del user, path, offset, limit, max_chars
        raise PermissionError("Forbidden")

    service.read_file_page = fake_read_file_page

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get("/knowledge-flow/v1/fs/page/workspace/report.md")

    assert response.status_code == 403
    assert "Forbidden" in response.text


def test_fs_ls_returns_403_for_authorization_error(app_context, monkeypatch) -> None:
    """AuthorizationError must map to 403, not fall through to the generic
    500 branch (previously it did — `_handle_exception` only special-cased
    `PermissionError`, so a real ReBAC denial from `rebac_engine.py` crashed
    instead of being reported as a routine 403 auth failure)."""
    service = _ServiceStub()

    async def fake_ls(user, path="/"):
        del user, path
        raise AuthorizationError("u-1", "can_read", Resource.TEAM, "Not authorized")

    service.ls = fake_ls

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get("/knowledge-flow/v1/fs/list", params={"path": "/team/personal-u-1"})

    assert response.status_code == 403
    assert "Not authorized" in response.text


def test_fs_page_returns_structured_payload(app_context, monkeypatch) -> None:
    service = _ServiceStub()

    async def fake_read_file_page(user, path, *, offset=0, limit=None, max_chars=None):
        del user, limit, max_chars
        return FileReadPage(
            path=f"/{path}",
            content="1 | alpha",
            start_line=offset,
            end_line=offset,
            returned_lines=1,
            total_lines=3,
            has_more=True,
            next_offset=offset + 1,
            truncated=True,
        )

    service.read_file_page = fake_read_file_page

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get(
            "/knowledge-flow/v1/fs/page/corpus/documents/doc-1/preview.md",
            params={"offset": 0, "limit": 40, "max_chars": 20000},
        )

    assert response.status_code == 200
    assert response.json()["next_offset"] == 1
    assert response.json()["truncated"] is True


def test_fs_upload_returns_metadata_and_download_href(app_context, monkeypatch) -> None:
    service = _ServiceStub()
    captured: list[tuple[str, bytes]] = []

    async def fake_write_bytes(user, path, data):
        del user
        captured.append((path, data))

    service.write_bytes = fake_write_bytes

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.post(
            "/knowledge-flow/v1/fs/upload/teams/acme/shared/templates/deck.pptx",
            files={"file": ("deck.pptx", b"\x00\x01\x02", "application/octet-stream")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["path"] == "/teams/acme/shared/templates/deck.pptx"
    assert body["size"] == 3
    assert body["download_url"] == "/knowledge-flow/v1/fs/download/teams/acme/shared/templates/deck.pptx"
    assert captured == [("teams/acme/shared/templates/deck.pptx", b"\x00\x01\x02")]


def test_fs_download_streams_bytes(app_context, monkeypatch) -> None:
    service = _ServiceStub()

    async def fake_read_bytes(user, path):
        del user, path
        return b"\x89PNG\r\n"

    service.read_bytes = fake_read_bytes

    with _build_filesystem_app(monkeypatch, service) as client:
        response = client.get("/knowledge-flow/v1/fs/download/teams/acme/shared/logo.png")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n"
    assert response.headers["content-type"] == "image/png"


def test_fs_download_returns_404_for_unknown_path(app_context, monkeypatch) -> None:
    with _build_filesystem_app(monkeypatch) as client:
        response = client.get("/knowledge-flow/v1/fs/download/teams/acme/shared/missing.bin")

    assert response.status_code == 404


def test_openapi_exposes_read_file_and_read_file_page(app_context, monkeypatch) -> None:
    with _build_filesystem_app(monkeypatch) as client:
        schema = client.get("/openapi.json").json()

    read_file_operation = schema["paths"]["/knowledge-flow/v1/fs/cat/{path}"]["get"]
    read_file_page_operation = schema["paths"]["/knowledge-flow/v1/fs/page/{path}"]["get"]

    assert read_file_operation["operationId"] == "read_file"
    assert read_file_page_operation["operationId"] == "read_file_page"
    assert {parameter["name"] for parameter in read_file_page_operation["parameters"]} == {"path", "offset", "limit", "max_chars"}
    assert read_file_page_operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/FileReadPage")
