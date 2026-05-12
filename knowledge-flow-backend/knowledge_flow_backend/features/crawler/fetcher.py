from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from knowledge_flow_backend.features.crawler.url_utils import url_host


@dataclass(frozen=True)
class FetchResult:
    url: str
    content: str
    content_type: str
    etag: str | None
    last_modified: str | None


class HostRateLimiter:
    """Minimal per-host async rate limiter for HTTP-first crawling."""

    def __init__(self, delay_seconds: float = 0.5) -> None:
        """
        Create a per-host limiter.

        Why this exists:
        - website crawlers should avoid hammering one origin even when pages are
          processed in batches.

        How to use:
        - await `wait(url)` immediately before issuing a request.
        """
        self.delay_seconds = delay_seconds
        self._next_by_host: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def wait(self, url: str) -> None:
        """Sleep until `url`'s host is eligible for another request."""
        host = url_host(url)
        async with self._lock:
            now = datetime.now(timezone.utc)
            eligible = self._next_by_host.get(host, now)
            wait_for = max((eligible - now).total_seconds(), 0)
            self._next_by_host[host] = max(now, eligible) + timedelta(seconds=self.delay_seconds)
        if wait_for > 0:
            await asyncio.sleep(wait_for)


class HttpFetcher:
    """Async HTTP fetcher with retries, timeouts, redirects, and HTML filtering."""

    TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}

    def __init__(self, *, timeout_seconds: float = 20.0, max_attempts: int = 3) -> None:
        """
        Build the crawler fetcher.

        Why this exists:
        - all crawler network I/O must be HTTP-first via httpx with predictable
          retry behavior and content-type filtering.

        How to use:
        - create once per run and call `fetch(client, url)`.
        """
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max_attempts

    async def fetch(self, client: httpx.AsyncClient, url: str) -> FetchResult:
        """Fetch one HTML page or raise a concrete failure."""
        last_exc: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = await client.get(url, follow_redirects=True, timeout=self.timeout_seconds)
                if response.status_code in self.TRANSIENT_STATUS_CODES:
                    raise httpx.HTTPStatusError("transient status", request=response.request, response=response)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "text/html" not in content_type.lower():
                    raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")
                return FetchResult(
                    url=str(response.url),
                    content=response.text,
                    content_type=content_type,
                    etag=response.headers.get("etag"),
                    last_modified=response.headers.get("last-modified"),
                )
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_exc = exc
                if attempt >= self.max_attempts - 1:
                    break
                await asyncio.sleep(0.5 * (2**attempt))
        if last_exc:
            raise last_exc
        raise RuntimeError("Fetch failed without an exception")
