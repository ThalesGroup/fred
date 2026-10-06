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

"""Profile pictures: shared upload validation, self-only routes, object cleanup
on replace/delete/account deletion, and URLs attached outside the name cache."""

from __future__ import annotations

import logging
from io import BytesIO
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from control_plane_backend.app.dependencies import attach_application_container
from control_plane_backend.common.avatar_image import (
    MAX_AVATAR_FILE_SIZE_BYTES,
    AvatarUploadError,
    read_avatar_upload,
)
from control_plane_backend.main import create_app
from control_plane_backend.teams import api as teams_api
from control_plane_backend.users import api as users_api
from control_plane_backend.users import service as users_service
from control_plane_backend.users.dependencies import get_user_service_dependencies
from control_plane_backend.users.schemas import UserSummary
from fastapi import FastAPI, UploadFile
from fred_core import KeycloakUser, get_current_user
from httpx import ASGITransport, AsyncClient
from starlette.datastructures import Headers

_PNG = b"\x89PNG\r\n\x1a\n" + b"png-body"
_JPEG = b"\xff\xd8\xff" + b"jpeg-body"
_WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"webp-body"


class _FakeUserStore:
    """In-memory `swap_avatar_key` / `get_avatar_keys`."""

    def __init__(self, keys: dict[str, str] | None = None) -> None:
        self.keys = dict(keys or {})
        self.key_reads = 0

    async def swap_avatar_key(self, user_id: UUID, key: str | None, session=None):
        previous = self.keys.pop(str(user_id), None)
        if key is not None:
            self.keys[str(user_id)] = key
        return previous

    async def get_avatar_keys(self, user_ids, session=None) -> dict[str, str]:
        self.key_reads += 1
        return {uid: self.keys[uid] for uid in user_ids if uid in self.keys}


class _FakeContentStore:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.presigned: list[str] = []
        self.fail_delete = False
        self.fail_presign = False

    def put_object(self, key: str, stream, *, content_type: str) -> None:
        self.objects[key] = stream.read()

    def delete_object(self, key: str) -> None:
        if self.fail_delete:
            raise PermissionError("AccessDenied")
        self.deleted.append(key)
        self.objects.pop(key, None)

    def get_presigned_url(self, key: str, expires=None) -> str:
        if self.fail_presign:
            raise RuntimeError("signing refused")
        self.presigned.append(key)
        return f"https://objects.test/{key}?sig=1"


def _upload(payload: bytes, content_type: str, filename: str = "me.png") -> UploadFile:
    return UploadFile(
        file=BytesIO(payload),
        filename=filename,
        headers=Headers({"content-type": content_type}),
    )


@pytest.fixture
def user_store(monkeypatch: pytest.MonkeyPatch) -> _FakeUserStore:
    store = _FakeUserStore()
    monkeypatch.setattr(users_service, "get_user_store", lambda: store)
    return store


@pytest.fixture
def content_store() -> _FakeContentStore:
    return _FakeContentStore()


# --- shared validation ------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "content_type", "message"),
    [
        (b"", "image/png", "Empty file upload is not allowed"),
        (
            b"\x89PNG\r\n\x1a\n" + b"a" * MAX_AVATAR_FILE_SIZE_BYTES,
            "image/png",
            "File too large:",
        ),
        (b"GIF89a-body", "image/gif", "Invalid content type: image/gif"),
        (_JPEG, "image/png", "doesn't match declared content type: image/jpeg"),
        (b"not-an-image", "image/png", "doesn't match allowed image formats"),
    ],
    ids=["empty", "oversize", "gif", "mismatch", "unknown-bytes"],
)
async def test_read_avatar_upload_rejects(
    payload: bytes, content_type: str, message: str
) -> None:
    with pytest.raises(AvatarUploadError) as exc:
        await read_avatar_upload(_upload(payload, content_type))
    assert message in exc.value.message


@pytest.mark.asyncio
async def test_read_avatar_upload_falls_back_to_the_mime_extension() -> None:
    payload, content_type, extension = await read_avatar_upload(
        _upload(_WEBP, "image/webp", filename="blob")
    )

    assert (payload, content_type, extension) == (_WEBP, "image/webp", ".webp")


# --- URLs on summaries ------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_batch_gets_a_url_only_for_the_person_with_a_key(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    alice, bob = str(uuid4()), str(uuid4())
    user_store.keys[alice] = f"users/{alice}/avatar-1.png"
    summaries = {
        alice: UserSummary(id=alice),
        bob: UserSummary(id=bob),
        "unknown": UserSummary(id="unknown"),
    }

    result = await users_service.attach_avatar_urls(summaries, lambda: content_store)

    assert set(result) == {alice, bob, "unknown"}
    assert result[alice].avatar_image_url == (
        f"https://objects.test/users/{alice}/avatar-1.png?sig=1"
    )
    assert result[bob].avatar_image_url is None
    assert result["unknown"].avatar_image_url is None
    assert user_store.key_reads == 1
    assert content_store.presigned == [f"users/{alice}/avatar-1.png"]
    # The input (possibly the name cache's own object) is never mutated.
    assert summaries[alice].avatar_image_url is None


@pytest.mark.asyncio
async def test_a_failed_presign_omits_the_url_and_logs_no_url(
    user_store: _FakeUserStore,
    content_store: _FakeContentStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    alice = str(uuid4())
    user_store.keys[alice] = "users/a/avatar.png"
    content_store.fail_presign = True

    with caplog.at_level(logging.WARNING):
        result = await users_service.attach_avatar_urls(
            {alice: UserSummary(id=alice, username="alice")}, lambda: content_store
        )

    assert result[alice].avatar_image_url is None
    assert alice in caplog.text
    assert "https://" not in caplog.text
    assert "alice@" not in caplog.text


@pytest.mark.asyncio
async def test_a_picture_change_is_visible_despite_the_name_cache(
    monkeypatch: pytest.MonkeyPatch,
    user_store: _FakeUserStore,
    content_store: _FakeContentStore,
) -> None:
    alice = str(uuid4())
    calls: list[str] = []

    class _Admin:
        async def a_get_user(self, user_id: str) -> dict:
            calls.append(user_id)
            return {"id": user_id, "username": "alice"}

    users_service._USER_SUMMARY_CACHE.delete(alice)
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            security=SimpleNamespace(user_directory="keycloak")
        ),
        create_keycloak_admin_client=lambda: _Admin(),
        get_content_store=lambda: content_store,
    )

    first = await users_service.get_users_by_ids([alice], cast(Any, deps))
    user_store.keys[alice] = "users/a/avatar-2.png"
    second = await users_service.get_users_by_ids([alice], cast(Any, deps))

    assert calls == [alice], "the display name must come from the cache"
    assert first[alice].avatar_image_url is None
    assert second[alice].avatar_image_url == (
        "https://objects.test/users/a/avatar-2.png?sig=1"
    )
    users_service._USER_SUMMARY_CACHE.delete(alice)


@pytest.mark.asyncio
async def test_bootstrap_current_user_carries_the_picture_url(
    monkeypatch: pytest.MonkeyPatch,
    user_store: _FakeUserStore,
    content_store: _FakeContentStore,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_content_store",
        lambda _self: content_store,
    )
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")
    app = create_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        without = await client.get("/control-plane/v1/frontend/bootstrap")
        user_store.keys["admin"] = "users/admin/avatar.png"
        with_picture = await client.get("/control-plane/v1/frontend/bootstrap")

    assert without.status_code == 200
    assert without.json()["current_user"].get("avatar_image_url") is None
    assert with_picture.json()["current_user"]["avatar_image_url"] == (
        "https://objects.test/users/admin/avatar.png?sig=1"
    )


# --- self-service routes ----------------------------------------------------


def _app(caller: str, content_store: _FakeContentStore) -> FastAPI:
    app = FastAPI()
    app.include_router(users_api.router)
    users_api.register_exception_handlers(app)
    teams_api.register_exception_handlers(app)
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid=caller, username="caller", roles=[]
    )
    app.dependency_overrides[get_user_service_dependencies] = lambda: SimpleNamespace(
        get_content_store=lambda: content_store
    )
    return app


async def _post_avatar(app: FastAPI, payload: bytes, content_type: str):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/users/me/avatar", files={"file": ("me.png", payload, content_type)}
        )


async def _delete_avatar(app: FastAPI):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.delete("/users/me/avatar")


@pytest.mark.asyncio
async def test_upload_sets_the_key_then_replace_deletes_the_previous_object(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    caller = str(uuid4())
    app = _app(caller, content_store)

    first = await _post_avatar(app, _PNG, "image/png")
    first_key = user_store.keys[caller]
    second = await _post_avatar(app, _JPEG, "image/jpeg")
    second_key = user_store.keys[caller]

    assert (first.status_code, second.status_code) == (204, 204)
    assert first_key.startswith(f"users/{caller}/avatar-")
    assert first_key.endswith(".png")
    assert second_key != first_key
    assert content_store.deleted == [first_key]
    assert set(content_store.objects) == {second_key}


@pytest.mark.asyncio
async def test_invalid_upload_changes_nothing(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    caller = str(uuid4())
    user_store.keys[caller] = "users/c/avatar-old.png"

    response = await _post_avatar(_app(caller, content_store), _JPEG, "image/png")

    assert response.status_code == 400
    assert user_store.keys == {caller: "users/c/avatar-old.png"}
    assert content_store.objects == {}
    assert content_store.deleted == []


@pytest.mark.asyncio
async def test_old_object_delete_failure_still_succeeds_without_logging_urls(
    user_store: _FakeUserStore,
    content_store: _FakeContentStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caller = str(uuid4())
    user_store.keys[caller] = "users/c/avatar-old.png"
    content_store.fail_delete = True

    with caplog.at_level(logging.WARNING):
        response = await _post_avatar(_app(caller, content_store), _PNG, "image/png")

    assert response.status_code == 204
    assert user_store.keys[caller] != "users/c/avatar-old.png"
    assert caller in caplog.text
    assert "https://" not in caplog.text


@pytest.mark.asyncio
async def test_service_account_cannot_upload(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    response = await _post_avatar(
        _app("service-account", content_store), _PNG, "image/png"
    )

    assert response.status_code == 400
    assert content_store.objects == {}


@pytest.mark.asyncio
async def test_delete_clears_the_key_and_object_then_is_idempotent(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    caller = str(uuid4())
    user_store.keys[caller] = "users/c/avatar.png"
    content_store.objects["users/c/avatar.png"] = _PNG
    app = _app(caller, content_store)

    first = await _delete_avatar(app)
    second = await _delete_avatar(app)

    assert (first.status_code, second.status_code) == (204, 204)
    assert user_store.keys == {}
    assert content_store.objects == {}
    assert content_store.deleted == ["users/c/avatar.png"]


# --- account deletion -------------------------------------------------------


def _delete_user_app(content_store: _FakeContentStore, calls: list[str]) -> FastAPI:
    async def root() -> str:
        return "synthetic-root"

    async def no_favorites(_user_id: str) -> None:
        calls.append("delete_favorites")

    class _Identity:
        async def a_delete_user(self, _user_id: str) -> dict:
            calls.append("delete_identity_account")
            return {}

    rebac = SimpleNamespace(
        requires_active_accounts=False,
        check_user_permission_or_raise=lambda *_a, **_k: _noop(),
    )
    container = SimpleNamespace(
        get_rebac_engine=lambda: rebac,
        get_platform_bootstrap_store=lambda: SimpleNamespace(get_completed_by=root),
        get_prompt_store=lambda: SimpleNamespace(
            delete_favorites_for_user=no_favorites
        ),
    )
    app = FastAPI()
    app.include_router(users_api.router)
    users_api.register_exception_handlers(app)
    attach_application_container(app, container)  # type: ignore[arg-type]
    app.dependency_overrides[get_current_user] = lambda: KeycloakUser(
        uid="synthetic-admin", username="synthetic-admin", roles=[]
    )
    app.dependency_overrides[get_user_service_dependencies] = lambda: SimpleNamespace(
        configuration=SimpleNamespace(
            security=SimpleNamespace(user_directory="keycloak")
        ),
        create_keycloak_admin_client=lambda: _Identity(),
        get_content_store=lambda: content_store,
    )
    return app


async def _noop() -> None:
    return None


@pytest.mark.asyncio
async def test_account_deletion_removes_the_picture_before_the_identity(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    person = str(uuid4())
    user_store.keys[person] = "users/p/avatar.png"
    calls: list[str] = []

    async with AsyncClient(
        transport=ASGITransport(app=_delete_user_app(content_store, calls)),
        base_url="http://test",
    ) as client:
        response = await client.delete(f"/users/{person}")

    assert response.status_code == 204
    assert user_store.keys == {}
    assert content_store.deleted == ["users/p/avatar.png"]
    assert calls == ["delete_favorites", "delete_identity_account"]


@pytest.mark.asyncio
async def test_account_deletion_without_picture_makes_no_store_call(
    user_store: _FakeUserStore, content_store: _FakeContentStore
) -> None:
    calls: list[str] = []

    async with AsyncClient(
        transport=ASGITransport(app=_delete_user_app(content_store, calls)),
        base_url="http://test",
    ) as client:
        response = await client.delete(f"/users/{uuid4()}")

    assert response.status_code == 204
    assert content_store.deleted == []
