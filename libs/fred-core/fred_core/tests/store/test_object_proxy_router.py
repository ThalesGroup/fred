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

"""Offline tests for the signed object proxy route (CONTENT-URL-STRATEGY §2.4)."""

from __future__ import annotations

import io
import time
from typing import BinaryIO, Optional

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from fred_core.store.base_content_store import ObjectInfo
from fred_core.store.object_proxy_router import build_object_proxy_router
from fred_core.store.signed_token import make_signed_token

# Fake key: no real signing material is involved in these tests.
SECRET = "unit-test-signing-key"  # nosec B105  # pragma: allowlist secret
KEY = "teams/t1/banner.png"
PAYLOAD = bytes(range(256)) * 4  # 1024 bytes


class _FakeReader:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.closed = 0

    def stat_object(self, key: str) -> ObjectInfo:
        if key not in self.objects:
            raise FileNotFoundError(key)
        return ObjectInfo(
            key=key,
            size=len(self.objects[key]),
            content_type="image/png",
            etag="abc123",
        )

    def get_object_stream(
        self, key: str, *, start: Optional[int] = None, length: Optional[int] = None
    ) -> BinaryIO:
        if key not in self.objects:
            raise FileNotFoundError(key)
        data = self.objects[key]
        window = (
            data[start or 0 :]
            if length is None
            else data[(start or 0) : (start or 0) + length]
        )
        reader = self

        class _Stream(io.BytesIO):
            def close(self) -> None:
                reader.closed += 1
                super().close()

        return _Stream(window)


@pytest.fixture
def reader() -> _FakeReader:
    return _FakeReader({KEY: PAYLOAD})


@pytest.fixture
def client(reader: _FakeReader) -> TestClient:
    app = FastAPI()
    router = APIRouter(prefix="/control-plane/v1")
    router.include_router(build_object_proxy_router(reader=reader, secret=SECRET))
    app.include_router(router)
    return TestClient(app)


def _url(key: str = KEY, *, ttl: int = 60) -> str:
    token = make_signed_token([key], secret=SECRET, ttl_seconds=ttl)
    return f"/control-plane/v1/objects/{key}?token={token}"


def test_valid_token_serves_the_object(client: TestClient, reader: _FakeReader):
    response = client.get(_url())

    assert response.status_code == 200
    assert response.content == PAYLOAD
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["etag"] == '"abc123"'
    assert response.headers["cache-control"].startswith("private, max-age=")
    assert reader.closed == 1


def test_cache_control_never_outlives_the_token(client: TestClient):
    response = client.get(_url(ttl=30))

    max_age = int(response.headers["cache-control"].split("max-age=")[1])
    assert 0 < max_age <= 30


def test_missing_token_is_refused(client: TestClient):
    assert client.get(f"/control-plane/v1/objects/{KEY}").status_code == 403


def test_token_for_another_key_is_refused(client: TestClient):
    token = make_signed_token(["teams/t1/other.png"], secret=SECRET, ttl_seconds=60)
    assert (
        client.get(f"/control-plane/v1/objects/{KEY}?token={token}").status_code == 403
    )


def test_expired_token_is_refused(client: TestClient):
    token = make_signed_token(
        [KEY], secret=SECRET, ttl_seconds=1, now=int(time.time()) - 120
    )
    assert (
        client.get(f"/control-plane/v1/objects/{KEY}?token={token}").status_code == 403
    )


def test_traversal_key_is_refused_before_any_read(
    client: TestClient, reader: _FakeReader
):
    traversal = "../../etc/passwd"
    token = make_signed_token([traversal], secret=SECRET, ttl_seconds=60)

    response = client.get(f"/control-plane/v1/objects/{traversal}?token={token}")

    # Starlette may normalize the path away entirely (404) or the guard rejects it (400);
    # either way the reader is never asked for it.
    assert response.status_code in (400, 404)
    assert reader.closed == 0


def test_unknown_object_is_404(client: TestClient):
    assert client.get(_url("teams/t1/missing.png")).status_code == 404


def test_range_request_returns_206_with_content_range(client: TestClient):
    response = client.get(_url(), headers={"Range": "bytes=10-19"})

    assert response.status_code == 206
    assert response.headers["content-range"] == f"bytes 10-19/{len(PAYLOAD)}"
    assert "content-length" not in {header.lower() for header in response.headers}
    assert response.content == PAYLOAD[10:20]


def test_open_ended_range_runs_to_the_last_byte(client: TestClient):
    response = client.get(_url(), headers={"Range": "bytes=1000-"})

    assert response.status_code == 206
    assert (
        response.headers["content-range"]
        == f"bytes 1000-{len(PAYLOAD) - 1}/{len(PAYLOAD)}"
    )
    assert response.content == PAYLOAD[1000:]


def test_suffix_range_returns_the_tail(client: TestClient):
    response = client.get(_url(), headers={"Range": "bytes=-16"})

    assert response.status_code == 206
    assert response.content == PAYLOAD[-16:]


def test_out_of_bounds_range_is_416(client: TestClient):
    response = client.get(_url(), headers={"Range": "bytes=99999-"})

    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(PAYLOAD)}"


def test_route_is_absent_from_the_openapi_schema(client: TestClient):
    paths = client.get("/openapi.json").json()["paths"]

    assert not [path for path in paths if "/objects/" in path]
