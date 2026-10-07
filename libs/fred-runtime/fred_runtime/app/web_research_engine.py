# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Internal asynchronous web research engine; no server or user activity storage."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import socket
import ssl
import unicodedata
from collections.abc import Callable
from typing import Any, TypeVar

import httpcore
import httpx
from fred_sdk.contracts.web_research import (
    FetchArguments,
    FetchRequest,
    WebPage,
    WebResearchDeploymentConfig,
    WebResearchError,
    WebResearchRequest,
    WebResearchResult,
    WebSearchRequest,
)
from httpcore._backends.auto import AutoBackend

from fred_runtime.app.web_research_providers import SearchProvider, build_provider

logger = logging.getLogger(__name__)


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if not ip.is_global or ip.is_multicast or ip.is_reserved:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None and not ip.ipv4_mapped.is_global:
            return False
        # Transition mechanisms can tunnel to destinations outside the address policy.
        if any(
            ip in network
            for network in (
                ipaddress.ip_network("64:ff9b::/96"),
                ipaddress.ip_network("64:ff9b:1::/48"),
                ipaddress.ip_network("2002::/16"),
                ipaddress.ip_network("2001::/32"),
            )
        ):
            return False
    return True


async def resolve_public(host: str, port: int) -> str:
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError:
        raise WebResearchError("unavailable") from None
    addresses = [str(record[4][0]) for record in records]
    if not addresses or any(not is_public(address) for address in addresses):
        raise WebResearchError("unsafe_destination")
    return addresses[0]


# Names that never designate a public site, judged without DNS.
_LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa", ".svc")
_NUMERIC_LABEL = re.compile(r"0x[0-9a-f]*|[0-9]+")


def check_literal(host: str) -> None:
    """Refuse without DNS what cannot be public; other names are left to the proxy."""
    name = host.strip("[]").rstrip(".").lower()
    try:
        address = ipaddress.ip_address(name)
    except ValueError:
        labels = name.split(".")
        # inet_aton (glibc, squid) reads 2130706433, 127.1 or 0x7f.0.0.1 as loopback.
        if (
            len(labels) < 2
            or name.endswith(_LOCAL_SUFFIXES)
            or all(_NUMERIC_LABEL.fullmatch(label) for label in labels)
        ):
            raise WebResearchError("unsafe_destination") from None
        return
    if not is_public(str(address)):
        raise WebResearchError("unsafe_destination")


class PublicNetworkBackend(AutoBackend):
    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        # httpcore preserves the original hostname for HTTP Host and TLS SNI.
        # Only the TCP connection uses this vetted numeric address, avoiding a second DNS lookup.
        address = await resolve_public(host, port)
        return await super().connect_tcp(
            address,
            port,
            timeout,
            local_address,
            socket_options,
        )


class PublicTransport(httpx.AsyncHTTPTransport):
    def __init__(self, connections: int) -> None:
        super().__init__(trust_env=False)
        # HTTPX has no public backend argument; keep its exception/stream adaptation
        # and supply a httpcore pool using the public network_backend interface.
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=ssl.create_default_context(),
            network_backend=PublicNetworkBackend(),
            max_connections=connections,
            max_keepalive_connections=connections,
        )


_T = TypeVar("_T")


class ResearchEngine:
    def __init__(
        self,
        config: WebResearchDeploymentConfig,
        provider: SearchProvider,
        client: httpx.AsyncClient,
    ) -> None:
        self.config = config
        self.provider = provider
        self.client = client
        self.workers = asyncio.Semaphore(config.max_concurrency)
        self.pending: set[asyncio.Task[Any]] = set()

    async def in_thread(self, function: Callable[[], _T]) -> _T:
        started = False

        async def work() -> _T:
            nonlocal started
            async with self.workers:
                started = True
                return await asyncio.to_thread(function)

        task = asyncio.create_task(work())
        self.pending.add(task)

        def completed(done: asyncio.Task[_T]) -> None:
            self.pending.discard(done)
            if not done.cancelled():
                done.exception()

        task.add_done_callback(completed)
        # Cancellation of the HTTP request must not release capacity while the
        # blocking provider/extractor still runs in its worker thread.
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            if not started:
                task.cancel()
            raise

    async def search(self, request: WebSearchRequest) -> WebResearchResult:
        levels = {"off": 0, "moderate": 1, "on": 2}
        effective = max(
            (request.safesearch, self.config.safesearch), key=levels.__getitem__
        )
        request = request.model_copy(update={"safesearch": effective})
        for attempt in range(self.config.retries + 1):
            try:
                pages = await self.provider.search(request, self.in_thread)

                async def public(page: WebPage) -> bool:
                    try:
                        host = httpx.URL(page.url).host
                        if self.config.proxy_url:
                            check_literal(host)
                        else:
                            await resolve_public(host, httpx.URL(page.url).port or 443)
                        return True
                    except WebResearchError:
                        return False

                checks = (
                    [True] * len(pages)
                    if self.provider.trusted
                    else await asyncio.gather(*(public(page) for page in pages))
                )
                return WebResearchResult(
                    results=[
                        page
                        for page, allowed in zip(pages, checks, strict=True)
                        if allowed
                    ],
                    safesearch=effective,
                )
            except WebResearchError:
                raise
            except Exception:  # noqa: BLE001 -- Provider failures must never expose queries or raw exceptions.
                if attempt == self.config.retries:
                    raise WebResearchError("provider_failed") from None
                await asyncio.sleep(0.5 * (attempt + 1))
        raise WebResearchError("provider_failed")

    async def fetch(self, request: FetchRequest) -> WebPage:
        url = request.url
        for _ in range(6):
            try:
                FetchArguments(url=url)
            except ValueError:
                raise WebResearchError("unsafe_destination") from None
            async with self.client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "Fred-Web-Research/1.0",
                    "Cookie": "",
                    "Accept-Encoding": "identity",
                    "Accept": "text/html,application/json,text/plain;q=0.9",
                },
            ) as response:
                if response.is_redirect and "location" in response.headers:
                    url = str(response.url.join(response.headers["location"]))
                    continue
                if not 200 <= response.status_code < 300:
                    raise WebResearchError("http_error")
                if response.headers.get("content-encoding", "identity") != "identity":
                    raise WebResearchError("unsupported_content")
                content_type = (
                    response.headers.get("content-type", "").split(";")[0].lower()
                )
                body = bytearray()
                truncated = False
                async for chunk in response.aiter_raw():
                    remaining = self.config.max_bytes - len(body)
                    body.extend(chunk[:remaining])
                    if len(chunk) > remaining:
                        truncated = True
                        break
                data = bytes(body)
                if "html" in content_type or (
                    not content_type and data.lstrip().startswith(b"<")
                ):

                    def extract(data: bytes = data, url: str = url) -> tuple[str, str]:
                        import trafilatura

                        html = trafilatura.load_html(data)
                        if html is None:
                            return "", ""
                        metadata = trafilatura.extract_metadata(html)
                        text = (
                            trafilatura.extract(
                                html,
                                url=url,
                                output_format="markdown",
                                include_links=request.include_links,
                                include_tables=True,
                            )
                            or ""
                        )
                        return text, str(metadata.title or "")[:512] if metadata else ""

                    content, title = await self.in_thread(extract)
                elif content_type.startswith("text/") or content_type in {
                    "application/json",
                    "application/xml",
                    "application/rss+xml",
                }:
                    content, title = await self.in_thread(
                        lambda data=data: (data.decode("utf-8", errors="replace"), "")
                    )
                else:
                    raise WebResearchError("unsupported_content")
                if request.focus:
                    content = await self.in_thread(
                        lambda content=content: select_passages(
                            content, request.focus or "", request.max_passages
                        )
                    )
                end = request.offset + request.max_chars
                return WebPage(
                    url=request.url,
                    final_url=url,
                    title=title,
                    status=response.status_code,
                    content_type=content_type[:128],
                    content=content[request.offset : end],
                    truncated=truncated or len(content) > end,
                    # A continuation point only exists in the full, unfocused text.
                    next_offset=end
                    if len(content) > end and not request.focus
                    else None,
                )
        raise WebResearchError("too_many_redirects")

    def capped(self, request: WebResearchRequest) -> WebResearchRequest:
        """Apply deployment ceilings so tool arguments cannot inflate model context."""
        if isinstance(request, FetchRequest):
            limit = min(request.max_chars, self.config.max_chars_per_page)
            return request.model_copy(update={"max_chars": limit})
        limit = min(request.max_results, self.config.max_results)
        return request.model_copy(update={"max_results": limit})

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        request = self.capped(request)
        if isinstance(request, FetchRequest):
            return WebResearchResult(results=[await self.fetch(request)])
        return await self.search(request)


def select_passages(content: str, focus: str, count: int) -> str:
    def terms(text: str) -> set[str]:
        folded = unicodedata.normalize("NFKD", text.lower())
        return set(
            re.findall(
                r"\w{3,}",
                "".join(char for char in folded if not unicodedata.combining(char)),
            )
        )

    query = terms(focus)
    blocks = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    scores = sorted(
        ((len(query & terms(block)), index) for index, block in enumerate(blocks)),
        key=lambda pair: (-pair[0], pair[1]),
    )[:count]
    indices = sorted(index for score, index in scores if score > 0)
    return "\n\n".join(blocks[index] for index in indices) if indices else content


class ProxyTransport(httpx.AsyncHTTPTransport):
    """Check only IP literals locally, without DNS: the proxy resolves names and
    MUST refuse private, non-global and metadata destinations."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            FetchArguments(url=str(request.url))
        except ValueError:
            raise WebResearchError("unsafe_destination") from None
        check_literal(request.url.host)
        return await super().handle_async_request(request)


def create_engine(
    config: WebResearchDeploymentConfig, client: httpx.AsyncClient | None = None
) -> ResearchEngine:
    """Build the engine; `client` replaces the guarded transport only in tests."""
    # Diagnostic libraries can include raw queries/URLs; only Fred's metadata
    # metrics and restricted activity store are authorized to observe requests.
    for name in ("trafilatura", "httpx", "httpcore"):
        library_logger = logging.getLogger(name)
        library_logger.handlers = [logging.NullHandler()]
        library_logger.propagate = False
    if client is not None:
        return ResearchEngine(config, build_provider(config, client), client)
    if config.proxy_url:
        credentials = None
        if config.proxy_auth_env:
            secret = os.getenv(config.proxy_auth_env, "")
            username, separator, password = secret.partition(":")
            if not separator or not username or not password:
                raise RuntimeError(
                    "Configured web research proxy credentials are missing or invalid."
                )
            credentials = (username, password)
        proxy_tls = (
            ssl.create_default_context(cafile=config.proxy_ca_file)
            if config.proxy_url.startswith("https://")
            else None
        )
        proxy = httpx.Proxy(config.proxy_url, auth=credentials, ssl_context=proxy_tls)
        transport: httpx.AsyncHTTPTransport = ProxyTransport(
            proxy=proxy,
            verify=ssl.create_default_context(),
            trust_env=False,
            limits=httpx.Limits(max_connections=config.max_concurrency),
        )
    else:
        transport = PublicTransport(config.max_concurrency)
    client = httpx.AsyncClient(
        transport=transport,
        timeout=config.timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    )
    return ResearchEngine(config, build_provider(config, client), client)
