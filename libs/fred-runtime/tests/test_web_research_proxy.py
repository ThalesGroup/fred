# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
import ssl
import subprocess

import httpx
import pytest
from fred_runtime.app.web_research_engine import ProxyTransport, create_engine
from fred_sdk.contracts.web_research import (
    FetchRequest,
    WebResearchDeploymentConfig,
    WebResearchError,
)


@pytest.mark.asyncio
async def test_proxy_preflight_refuses_private_target_before_transport(monkeypatch):
    called = False

    async def reject(host, port):
        raise WebResearchError("unsafe_destination")

    async def send(self, request):
        nonlocal called
        called = True
        raise AssertionError("must not dispatch")

    monkeypatch.setattr("fred_runtime.app.web_research_engine.resolve_public", reject)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", send)
    async with ProxyTransport(proxy="http://127.0.0.1:3128") as transport:
        with pytest.raises(WebResearchError, match="unsafe_destination"):
            await transport.handle_async_request(
                httpx.Request("GET", "http://10.0.0.1/")
            )
    assert not called


# Opens a real local TLS proxy socket, which `make test` forbids.
@pytest.mark.integration
@pytest.mark.asyncio
async def test_actual_https_proxy_trust_routing_and_credentials(tmp_path, monkeypatch):
    cert, key = tmp_path / "cert.pem", tmp_path / "key.pem"
    await asyncio.to_thread(
        subprocess.run,
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,IP:127.0.0.1",
            "-keyout",
            str(key),
            "-out",
            str(cert),
        ],
        check=True,
        capture_output=True,
    )
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(cert, key)
    requests = []

    async def proxy(reader, writer):
        try:
            data = await reader.readuntil(b"\r\n\r\n")
            requests.append(data)
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 8\r\nConnection: close\r\n\r\nevidence"
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    async def public(host, port):
        assert host == "example.com"
        return "8.8.8.8"

    monkeypatch.setattr("fred_runtime.app.web_research_engine.resolve_public", public)
    monkeypatch.setenv("TEST_PROXY_AUTH", "fred:synthetic-password")
    server = await asyncio.start_server(proxy, "127.0.0.1", 0, ssl=tls)
    port = server.sockets[0].getsockname()[1]
    config = WebResearchDeploymentConfig(
        enabled=True,
        proxy_url=f"https://localhost:{port}",
        proxy_auth_env="TEST_PROXY_AUTH",
        proxy_ca_file=str(cert),
    )
    engine = create_engine(config)
    try:
        result = await engine.execute(FetchRequest(url="http://example.com/"))
        assert result.results[0].content == "evidence"
        assert requests[0].startswith(b"GET http://example.com/ HTTP/1.1")
        expected = base64.b64encode(b"fred:synthetic-password")
        assert b"Proxy-Authorization: Basic " + expected in requests[0]
        assert b"\r\nAuthorization:" not in requests[0]
        assert "proxy-authorization" not in engine.client.headers
        untrusted = create_engine(config.model_copy(update={"proxy_ca_file": None}))
        try:
            with pytest.raises(httpx.ConnectError):
                await untrusted.execute(FetchRequest(url="http://example.com/"))
            assert len(requests) == 1
        finally:
            await untrusted.client.aclose()
    finally:
        await engine.client.aclose()
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_unavailable_proxy_never_connects_direct(monkeypatch):
    from httpcore._backends.auto import AutoBackend

    destinations = []

    async def public(host, port):
        return "8.8.8.8"

    async def failed(self, host, port, *args, **kwargs):
        destinations.append((host, port))
        raise httpx.ConnectError("proxy down")

    monkeypatch.setattr("fred_runtime.app.web_research_engine.resolve_public", public)
    monkeypatch.setattr(AutoBackend, "connect_tcp", failed)
    engine = create_engine(
        WebResearchDeploymentConfig(enabled=True, proxy_url="http://proxy.dmz:3128")
    )
    try:
        with pytest.raises(httpx.ConnectError):
            await engine.execute(FetchRequest(url="https://example.com/"))
        assert destinations == [("proxy.dmz", 3128)]
    finally:
        await engine.client.aclose()


@pytest.mark.parametrize(
    "values",
    [
        {"proxy_url": "socks5://proxy"},
        {"proxy_url": "http://proxy/path"},
        {"proxy_url": "http://proxy?secret=x"},
        {"proxy_url": "http://proxy:invalid"},
        {"proxy_url": "http://proxy", "proxy_ca_file": "ca.pem"},
        {"proxy_auth_env": "AUTH"},
    ],
)
def test_invalid_proxy_configuration_fails_closed(values):
    with pytest.raises(ValueError):
        WebResearchDeploymentConfig.model_validate(values)
