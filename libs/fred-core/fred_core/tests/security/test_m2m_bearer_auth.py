from __future__ import annotations

import asyncio
import secrets

import httpx
import pytest

from fred_core.security.backend_to_backend_auth import (
    M2MAuthConfig,
    M2MBearerAuth,
    M2MTokenProvider,
)


def _provider(monkeypatch, endpoint, *, client_id: str = "workload"):
    secret_env = f"TEST_AUTH_CLIENT_SECRET_{secrets.token_hex(6).upper()}"
    monkeypatch.setenv(secret_env, secrets.token_urlsafe())
    return M2MTokenProvider(
        M2MAuthConfig(
            keycloak_realm_url="https://identity.invalid/realms/test",
            client_id=client_id,
            secret_env=secret_env,
        ),
        transport=httpx.MockTransport(endpoint),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected_attempts", "expected_refreshes"),
    [
        ([200], 1, 1),
        ([401, 200], 2, 2),
        ([401, 401], 2, 2),
        ([401, 403], 2, 2),
        ([403], 1, 1),
    ],
)
async def test_auth_response_matrix(
    monkeypatch, statuses, expected_attempts, expected_refreshes
) -> None:
    issued = 0
    received = []

    def token_endpoint(request):
        nonlocal issued
        issued += 1
        return httpx.Response(
            200,
            json={"access_token": f"token-{issued}", "expires_in": 120},
        )

    def api_endpoint(request):
        received.append(request.headers["Authorization"])
        return httpx.Response(statuses[len(received) - 1])

    async with httpx.AsyncClient(
        auth=M2MBearerAuth(_provider(monkeypatch, token_endpoint)),
        transport=httpx.MockTransport(api_endpoint),
    ) as client:
        response = await client.get("https://service.invalid/items")

    assert response.status_code == statuses[-1]
    assert len(received) == expected_attempts
    assert issued == expected_refreshes
    assert received == [f"Bearer token-{i + 1}" for i in range(expected_attempts)]


@pytest.mark.asyncio
async def test_auth_replays_multipart_request_and_preserves_response_stream(
    monkeypatch,
) -> None:
    issued = 0
    received = []
    stream_read = False

    class ResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            nonlocal stream_read
            stream_read = True
            yield b"streamed"

    def token_endpoint(request):
        nonlocal issued
        issued += 1
        return httpx.Response(
            200, json={"access_token": f"token-{issued}", "expires_in": 120}
        )

    def api_endpoint(request):
        received.append(
            (
                request.method,
                str(request.url),
                request.headers["X-Request"],
                request.headers["Content-Type"],
                request.content,
                request.extensions.get("timeout"),
                request.headers["Authorization"],
            )
        )
        if len(received) == 1:
            return httpx.Response(401)
        return httpx.Response(200, stream=ResponseStream())

    async with httpx.AsyncClient(
        auth=M2MBearerAuth(_provider(monkeypatch, token_endpoint)),
        transport=httpx.MockTransport(api_endpoint),
    ) as client:
        async with client.stream(
            "POST",
            "https://service.invalid/upload?person=p&run=r&agent=a",
            headers={"X-Request": "kept"},
            files={"file": ("fixture.txt", b"synthetic-content")},
            timeout=httpx.Timeout(7.0, connect=2.0),
        ) as response:
            assert response.status_code == 200
            assert stream_read is False
            assert await response.aread() == b"streamed"

    assert len(received) == 2
    assert received[0][:6] == received[1][:6]
    assert received[0][6] == "Bearer token-1"
    assert received[1][6] == "Bearer token-2"
    assert stream_read is True


@pytest.mark.asyncio
async def test_delayed_401_reuses_the_refresh_for_its_rejected_generation(
    monkeypatch,
) -> None:
    issued = 0
    first_arrivals = 0
    first_sent = asyncio.Event()
    both_sent = asyncio.Event()
    release_delayed = asyncio.Event()

    def token_endpoint(request):
        nonlocal issued
        issued += 1
        return httpx.Response(
            200,
            json={
                "access_token": f"token-{issued}",
                "expires_in": 30 if issued == 2 else 120,
            },
        )

    async def api_endpoint(request):
        nonlocal first_arrivals
        if request.headers["Authorization"] == "Bearer token-1":
            first_arrivals += 1
            arrival = first_arrivals
            if arrival == 1:
                first_sent.set()
                await asyncio.wait_for(both_sent.wait(), timeout=3)
            else:
                both_sent.set()
                await asyncio.wait_for(release_delayed.wait(), timeout=3)
            return httpx.Response(401)
        return httpx.Response(200)

    provider = _provider(monkeypatch, token_endpoint)
    async with httpx.AsyncClient(
        auth=M2MBearerAuth(provider), transport=httpx.MockTransport(api_endpoint)
    ) as client:
        first = asyncio.create_task(client.get("https://service.invalid/one"))
        await asyncio.wait_for(first_sent.wait(), timeout=3)
        second = asyncio.create_task(client.get("https://service.invalid/two"))
        await asyncio.wait_for(both_sent.wait(), timeout=3)
        assert (await asyncio.wait_for(first, timeout=3)).status_code == 200
        release_delayed.set()
        assert (await asyncio.wait_for(second, timeout=3)).status_code == 200

    assert issued == 2


@pytest.mark.asyncio
async def test_unbuffered_401_retries_a_consumed_async_upload(monkeypatch) -> None:
    issued = 0
    bodies = []

    def token_endpoint(request):
        nonlocal issued
        issued += 1
        return httpx.Response(
            200, json={"access_token": f"token-{issued}", "expires_in": 120}
        )

    class ResponseStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"refused"

    class Transport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            stream = request.stream
            assert isinstance(stream, httpx.AsyncByteStream)
            bodies.append(b"".join([chunk async for chunk in stream]))
            if len(bodies) == 1:
                return httpx.Response(401, stream=ResponseStream())
            return httpx.Response(200)

    async def upload():
        yield b"first-"
        yield b"second"

    async with httpx.AsyncClient(
        auth=M2MBearerAuth(_provider(monkeypatch, token_endpoint)),
        transport=Transport(),
    ) as client:
        response = await client.post("https://service.invalid/upload", content=upload())

    assert response.status_code == 200
    assert bodies == [b"first-second", b"first-second"]
    assert issued == 2


@pytest.mark.asyncio
async def test_cancelled_client_does_not_cancel_shared_401_renewal(monkeypatch) -> None:
    issued = 0
    renewal_started = asyncio.Event()
    finish_renewal = asyncio.Event()
    second_refusal = asyncio.Event()

    async def token_endpoint(request):
        nonlocal issued
        issued += 1
        if issued == 2:
            renewal_started.set()
            await asyncio.wait_for(finish_renewal.wait(), timeout=3)
        return httpx.Response(
            200, json={"access_token": f"token-{issued}", "expires_in": 120}
        )

    async def api_endpoint(request):
        if request.headers["Authorization"] == "Bearer token-1":
            if request.url.path == "/second":
                second_refusal.set()
            return httpx.Response(401)
        return httpx.Response(200)

    provider = _provider(monkeypatch, token_endpoint)
    transport = httpx.MockTransport(api_endpoint)
    async with (
        httpx.AsyncClient(auth=M2MBearerAuth(provider), transport=transport) as first,
        httpx.AsyncClient(auth=M2MBearerAuth(provider), transport=transport) as second,
    ):
        first_call = asyncio.create_task(first.get("https://service.invalid/first"))
        await asyncio.wait_for(renewal_started.wait(), timeout=3)
        second_call = asyncio.create_task(second.get("https://service.invalid/second"))
        await asyncio.wait_for(second_refusal.wait(), timeout=3)
        first_call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first_call
        finish_renewal.set()
        assert (await asyncio.wait_for(second_call, timeout=3)).status_code == 200

    assert issued == 2
