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

from __future__ import annotations

import httpx
import pytest

from fred_core.model.factory import _GcpTokenAuth, _patch_vertex_maas_auth


class _FakeCredentials:
    def __init__(self) -> None:
        self.valid = False
        self.token: str | None = None
        self.refresh_count = 0

    def refresh(self, _request: object) -> None:
        self.refresh_count += 1
        self.valid = True
        self.token = f"token-{self.refresh_count}"


class _FakeVertexModel:
    def __init__(
        self,
        *,
        credentials: _FakeCredentials,
        client: httpx.Client,
        async_client: httpx.AsyncClient,
    ) -> None:
        self.credentials = credentials
        self.client = client
        self.async_client = async_client


def _has_auth_header(headers: httpx.Headers) -> bool:
    return any(key.lower() == "authorization" for key in headers.keys())


def test_gcp_token_auth_refreshes_when_expired_sync() -> None:
    credentials = _FakeCredentials()
    auth = _GcpTokenAuth(credentials=credentials, request_adapter=object())
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        auth=auth,
    ) as client:
        for _ in range(4):
            credentials.valid = False
            client.get("/predict")

    assert seen_auth == [
        "Bearer token-1",
        "Bearer token-2",
        "Bearer token-3",
        "Bearer token-4",
    ]
    assert credentials.refresh_count == 4


@pytest.mark.asyncio
async def test_gcp_token_auth_refreshes_when_expired_async() -> None:
    credentials = _FakeCredentials()
    auth = _GcpTokenAuth(credentials=credentials, request_adapter=object())
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        auth=auth,
    ) as client:
        for _ in range(4):
            credentials.valid = False
            await client.post("/streamRawPredict", json={"input": "hello"})

    assert seen_auth == [
        "Bearer token-1",
        "Bearer token-2",
        "Bearer token-3",
        "Bearer token-4",
    ]
    assert credentials.refresh_count == 4


@pytest.mark.asyncio
async def test_patch_vertex_maas_auth_endurance_simulation() -> None:
    """
    Mini endurance simulation:
    - force token expiration before every request
    - alternate sync and async requests on patched model clients
    - assert requests keep working with refreshed tokens
    """

    credentials = _FakeCredentials()
    seen_sync: list[str | None] = []
    seen_async: list[str | None] = []

    def sync_handler(request: httpx.Request) -> httpx.Response:
        seen_sync.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"ok": True})

    def async_handler(request: httpx.Request) -> httpx.Response:
        seen_async.append(request.headers.get("Authorization"))
        return httpx.Response(200, json={"ok": True})

    sync_client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(sync_handler),
        headers={"Authorization": "Bearer stale-token"},
    )
    async_client = httpx.AsyncClient(
        base_url="https://example.test",
        transport=httpx.MockTransport(async_handler),
        headers={"Authorization": "Bearer stale-token"},
    )
    model = _FakeVertexModel(
        credentials=credentials,
        client=sync_client,
        async_client=async_client,
    )

    try:
        _patch_vertex_maas_auth(model)
        assert not _has_auth_header(model.client.headers)
        assert not _has_auth_header(model.async_client.headers)

        rounds = 8
        for _ in range(rounds):
            credentials.valid = False
            model.client.post("/rawPredict", json={"input": "sync"})
            credentials.valid = False
            await model.async_client.post("/streamRawPredict", json={"input": "async"})

        assert len(seen_sync) == rounds
        assert len(seen_async) == rounds
        assert all(
            value is not None and value.startswith("Bearer token-")
            for value in seen_sync
        )
        assert all(
            value is not None and value.startswith("Bearer token-")
            for value in seen_async
        )
        assert credentials.refresh_count >= rounds * 2
    finally:
        model.client.close()
        await model.async_client.aclose()


def test_patch_vertex_maas_auth_ignores_incompatible_model() -> None:
    class _Incompatible:
        pass

    # Must not raise if a model does not expose httpx clients.
    _patch_vertex_maas_auth(_Incompatible())
