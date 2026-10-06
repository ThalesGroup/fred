# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Fred-owned HTTPS egress service. No user identities or activity records live here."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import secrets
import socket
import ssl
import time
import unicodedata
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any, Protocol, TypeVar
from uuid import UUID

import httpcore
import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fred_sdk.contracts.web_research import (
    FetchArguments,
    FetchRequest,
    SafeSearch,
    WebPage,
    WebResearchError,
    WebResearchRequest,
    WebResearchResult,
    WebSearchRequest,
)
from httpcore._backends.auto import AutoBackend
from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class EgressConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_concurrency: int = Field(default=8, ge=1, le=32)
    max_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    timeout_seconds: float = Field(default=30, ge=1, le=60)
    retries: int = Field(default=1, ge=0, le=2)
    safesearch: SafeSearch = "on"
    host: str = "127.0.0.1"
    port: int = Field(default=8120, ge=1, le=65535)
    tls_certificate: str | None = None
    tls_key: str | None = None
    tls_client_ca: str | None = None


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


class SearchProvider(Protocol):
    async def search(
        self,
        request: WebSearchRequest,
        run: Callable[[Callable[[], list[WebPage]]], Awaitable[list[WebPage]]],
    ) -> list[WebPage]: ...


class DuckDuckGoProvider:
    """Bounded HTML search using the same pinned transport as page fetches."""

    def __init__(self, client: httpx.AsyncClient, max_bytes: int) -> None:
        self.client = client
        self.max_bytes = max_bytes

    async def search(
        self,
        request: WebSearchRequest,
        run: Callable[[Callable[[], list[WebPage]]], Awaitable[list[WebPage]]],
    ) -> list[WebPage]:
        payload = {
            "q": request.query,
            "kl": request.region,
            "kp": {"on": "1", "moderate": "-1", "off": "-2"}[request.safesearch],
        }
        if request.timelimit:
            payload["df"] = request.timelimit
        async with self.client.stream(
            "POST",
            "https://html.duckduckgo.com/html/",
            data=payload,
            headers={
                "Cookie": "",
                "Accept-Encoding": "identity",
                "User-Agent": "Fred-Web-Research/1.0",
            },
        ) as response:
            if (
                response.status_code != 200
                or response.headers.get("content-encoding", "identity") != "identity"
            ):
                raise WebResearchError("provider_failed")
            body = bytearray()
            async for chunk in response.aiter_raw():
                if len(body) + len(chunk) > self.max_bytes:
                    raise WebResearchError("provider_failed")
                body.extend(chunk)

        def parse() -> list[WebPage]:
            from urllib.parse import parse_qs, urlsplit

            import trafilatura

            html = trafilatura.load_html(bytes(body))
            if html is None:
                raise WebResearchError("provider_failed")
            pages = []
            for node in html.xpath(
                '//div[contains(concat(" ", normalize-space(@class), " "), " result ")]'
            ):
                links = node.xpath(
                    './/a[contains(concat(" ", normalize-space(@class), " "), " result__a ")]'
                )
                if not links:
                    continue
                link = links[0]
                url = str(link.get("href", ""))
                if url.startswith("//"):
                    url = "https:" + url
                parsed = urlsplit(url)
                if (
                    parsed.hostname in {"duckduckgo.com", "www.duckduckgo.com"}
                    and parsed.path == "/l/"
                ):
                    url = parse_qs(parsed.query).get("uddg", [""])[0]
                if any(
                    marker in url
                    for marker in ("bing.com/aclick", "duckduckgo.com/y.js")
                ):
                    continue
                try:
                    FetchArguments(url=url)
                except ValueError:
                    continue
                snippets = node.xpath(
                    './/*[contains(concat(" ", normalize-space(@class), " "), " result__snippet ")]'
                )
                pages.append(
                    WebPage(
                        url=url,
                        title=link.text_content().strip()[:512],
                        snippet=snippets[0].text_content().strip()[:2000]
                        if snippets
                        else "",
                    )
                )
                if len(pages) == request.max_results:
                    break
            if not pages and not html.xpath('//*[contains(@class, "no-results")]'):
                # Captchas/layout changes must never masquerade as empty searches.
                raise WebResearchError("provider_failed")
            return pages

        return await run(parse)


_T = TypeVar("_T")


class Egress:
    def __init__(
        self, config: EgressConfig, provider: SearchProvider, client: httpx.AsyncClient
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
                        await resolve_public(host, httpx.URL(page.url).port or 443)
                        return True
                    except WebResearchError:
                        return False

                checks = await asyncio.gather(*(public(page) for page in pages))
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
            except Exception:
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

                    def extract() -> tuple[str, str]:
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
                        lambda: (data.decode("utf-8", errors="replace"), "")
                    )
                else:
                    raise WebResearchError("unsupported_content")
                if request.focus:
                    content = await self.in_thread(
                        lambda: select_passages(
                            content, request.focus or "", request.max_passages
                        )
                    )
                return WebPage(
                    url=request.url,
                    final_url=url,
                    title=title,
                    status=response.status_code,
                    content_type=content_type[:128],
                    content=content[: request.max_chars],
                    truncated=truncated or len(content) > request.max_chars,
                )
        raise WebResearchError("too_many_redirects")

    async def execute(self, request: WebResearchRequest) -> WebResearchResult:
        if isinstance(request, FetchRequest):
            return WebResearchResult(results=[await self.fetch(request)])
        if isinstance(request, WebSearchRequest):
            return await self.search(request)
        found = await self.search(
            WebSearchRequest.model_validate(
                request.model_dump(
                    exclude={"operation", "max_passages", "max_chars_per_page"}
                )
            )
        )

        async def one(page: WebPage) -> WebPage:
            try:
                fetched = await self.fetch(
                    FetchRequest(
                        url=page.url,
                        focus=request.query,
                        max_passages=request.max_passages,
                        max_chars=request.max_chars_per_page,
                    )
                )
                return fetched.model_copy(
                    update={
                        "snippet": page.snippet,
                        "title": fetched.title or page.title,
                    }
                )
            except (WebResearchError, httpx.HTTPError) as exc:
                return page.model_copy(
                    update={
                        "error_code": exc.code
                        if isinstance(exc, WebResearchError)
                        else "unavailable"
                    }
                )

        return WebResearchResult(
            results=list(await asyncio.gather(*(one(page) for page in found.results))),
            safesearch=found.safesearch,
        )


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


def create_app(
    config: EgressConfig,
    *,
    token: str,
    provider: SearchProvider | None = None,
    client: httpx.AsyncClient | None = None,
) -> FastAPI:
    if len(token) < 32:
        raise RuntimeError("A service token of at least 32 characters is required.")
    # These libraries can log queries, URLs or extracted text. Their diagnostic
    # output is not a permitted telemetry stream in this service.
    for name in ("trafilatura", "httpx", "httpcore"):
        library_logger = logging.getLogger(name)
        library_logger.handlers = [logging.NullHandler()]
        library_logger.propagate = False
    outbound = client or httpx.AsyncClient(
        transport=PublicTransport(config.max_concurrency),
        timeout=config.timeout_seconds,
        follow_redirects=False,
        trust_env=False,
    )
    egress = Egress(
        config, provider or DuckDuckGoProvider(outbound, config.max_bytes), outbound
    )
    slots = asyncio.Semaphore(config.max_concurrency)
    registry = CollectorRegistry()
    requests = Counter(
        "fred_web_egress_requests_total",
        "Egress operations",
        ["operation", "outcome"],
        registry=registry,
    )
    duration = Histogram(
        "fred_web_egress_duration_seconds",
        "Egress latency",
        ["operation"],
        registry=registry,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield
        await outbound.aclose()

    app = FastAPI(title="Fred web egress", version="1", lifespan=lifespan)

    @app.middleware("http")
    async def authenticate_and_bound(request: Request, call_next: Any) -> Response:
        if not secrets.compare_digest(
            request.headers.get("authorization", "").encode(),
            f"Bearer {token}".encode(),
        ):
            return JSONResponse({"error_code": "rejected"}, status_code=401)
        # Bound the body before FastAPI/Pydantic parses it, including chunked requests.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16_384:
                return JSONResponse({"error_code": "rejected"}, status_code=413)
        request._body = bytes(body)
        return await call_next(request)

    @app.exception_handler(RequestValidationError)
    async def invalid_arguments(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse({"error_code": "rejected"}, status_code=422)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(
            generate_latest(registry), media_type="text/plain; version=0.0.4"
        )

    @app.post("/v1/research", response_model=WebResearchResult)
    async def research(
        request: WebResearchRequest, x_request_id: str = Header()
    ) -> Any:
        try:
            UUID(x_request_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid_correlation") from None
        if slots.locked():
            requests.labels(operation=request.operation, outcome="busy").inc()
            return JSONResponse({"error_code": "busy"}, status_code=429)
        started = time.monotonic()
        outcome = "failed"
        try:
            async with slots, asyncio.timeout(config.timeout_seconds):
                result = await egress.execute(request)
                outcome = "succeeded"
                return result
        except WebResearchError as exc:
            return JSONResponse(
                {"error_code": exc.code},
                status_code=400 if exc.code == "unsafe_destination" else 502,
            )
        except (TimeoutError, httpx.TimeoutException):
            return JSONResponse({"error_code": "timed_out"}, status_code=504)
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception:
            return JSONResponse({"error_code": "unavailable"}, status_code=502)
        finally:
            requests.labels(operation=request.operation, outcome=outcome).inc()
            duration.labels(operation=request.operation).observe(
                time.monotonic() - started
            )
            logger.info(
                "event=web_egress operation=%s outcome=%s request_id=%s duration_ms=%d",
                request.operation,
                outcome,
                x_request_id,
                int((time.monotonic() - started) * 1000),
            )

    return app


def main() -> None:
    import logging
    from pathlib import Path

    import uvicorn
    import yaml
    from fred_pod.common.config_files import ConfigFiles

    quiet = logging.getLogger("fred.web_egress.config")
    quiet.disabled = True
    files = ConfigFiles(logger=quiet)
    try:
        files.load_environment()
        config = EgressConfig.model_validate(
            yaml.safe_load(Path(files.resolve_config_file_path()).read_text()) or {}
        )
    except Exception:
        raise RuntimeError("Invalid web egress configuration.") from None
    app = create_app(config, token=os.getenv("WEB_RESEARCH_EGRESS_TOKEN", ""))
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        ssl_certfile=config.tls_certificate,
        ssl_keyfile=config.tls_key,
        ssl_ca_certs=config.tls_client_ca,
        ssl_cert_reqs=ssl.CERT_REQUIRED if config.tls_client_ca else ssl.CERT_NONE,
        access_log=False,
    )


if __name__ == "__main__":
    main()
