# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
import asyncio
import base64
import ipaddress
import socket
import ssl
import subprocess

import httpx
import pytest
from fred_runtime.app.web_research_engine import ProxyTransport, create_engine
from fred_sdk.contracts.web_research import (
    FetchRequest,
    WebPage,
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)
from httpcore._backends.auto import AutoBackend

PROXY = "http://proxy.dmz:3128"


@pytest.mark.asyncio
async def test_proxy_preflight_refuses_private_target_before_transport(monkeypatch):
    called = False

    async def send(self, request):
        nonlocal called
        called = True
        raise AssertionError("must not dispatch")

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


@pytest.fixture
def no_dns(monkeypatch):
    """A network without external DNS: name lookups fail and are recorded.

    Numeric hosts still resolve, as libc does without querying any DNS server.
    """
    lookups = []

    def lookup(host, port, *args, **kwargs):
        try:
            ip = ipaddress.ip_address(str(host).strip("[]"))
        except ValueError:
            lookups.append(host)
            raise OSError("no DNS") from None
        family = socket.AF_INET6 if ip.version == 6 else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 6, "", (str(ip), port))]

    async def loop_lookup(self, host, port, *args, **kwargs):
        return lookup(host, port)

    monkeypatch.setattr(asyncio.base_events.BaseEventLoop, "getaddrinfo", loop_lookup)
    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    return lookups


@pytest.fixture
def connections(monkeypatch):
    destinations = []

    async def failed(self, host, port, *args, **kwargs):
        destinations.append((host, port))
        raise httpx.ConnectError("proxy down")

    monkeypatch.setattr(AutoBackend, "connect_tcp", failed)
    return destinations


async def fetch(url: str, proxy_url: str | None = PROXY) -> None:
    engine = create_engine(
        WebResearchDeploymentConfig(enabled=True, proxy_url=proxy_url)
    )
    try:
        await engine.execute(FetchRequest(url=url))
    finally:
        await engine.client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("url", ["https://example.com/", "http://93.184.215.14/"])
async def test_proxy_forwards_names_and_public_literals_without_dns(
    no_dns, connections, url
):
    with pytest.raises(httpx.ConnectError):
        await fetch(url)
    assert connections == [("proxy.dmz", 3128)]
    assert no_dns == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.1/",
        "http://127.0.0.1/",
        "http://169.254.169.254/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://[::ffff:10.0.0.1]/",
    ],
)
async def test_proxy_refuses_private_literals_locally(no_dns, connections, url):
    with pytest.raises(WebResearchError, match="unsafe_destination"):
        await fetch(url)
    assert connections == []
    assert no_dns == []


class Results:
    trusted = False

    async def search(self, request, run):
        return [
            WebPage(url=url)
            for url in (
                "https://example.com/a",
                "https://docs.python.org/b",
                "http://10.0.0.1/c",
            )
        ]


async def search(proxy_url: str | None) -> list[str]:
    engine = create_engine(
        WebResearchDeploymentConfig(enabled=True, proxy_url=proxy_url)
    )
    engine.provider = Results()
    try:
        result = await engine.execute(WebSearchRequest(query="fred"))
        return [page.url for page in result.results]
    finally:
        await engine.client.aclose()


@pytest.mark.asyncio
async def test_proxy_search_keeps_names_and_drops_private_literals(no_dns):
    assert await search(PROXY) == [
        "https://example.com/a",
        "https://docs.python.org/b",
    ]
    assert no_dns == []


@pytest.mark.asyncio
async def test_direct_mode_still_requires_dns(no_dns, connections):
    with pytest.raises(WebResearchError, match="unavailable"):
        await fetch("https://example.com/", proxy_url=None)
    assert await search(None) == []
    assert connections == []
    assert no_dns
