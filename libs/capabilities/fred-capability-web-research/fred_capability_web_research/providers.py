# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Search providers selected by deployment configuration behind one contract."""

from __future__ import annotations

import html as html_entities
import json
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

import httpx
from fred_sdk.contracts.web_research import (
    FetchArguments,
    WebPage,
    WebResearchDeploymentConfig,
    WebResearchError,
    WebSearchRequest,
)

Run = Callable[[Callable[[], list[WebPage]]], Awaitable[list[WebPage]]]


class SearchProvider(Protocol):
    # Trusted results (operator fixtures) skip the engine's public-DNS vetting.
    trusted: bool

    async def search(self, request: WebSearchRequest, run: Run) -> list[WebPage]: ...


async def read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Reject failed, compressed or oversized provider responses."""
    if (
        response.status_code != 200
        or response.headers.get("content-encoding", "identity") != "identity"
    ):
        raise WebResearchError("provider_failed")
    body = bytearray()
    async for chunk in response.aiter_raw():
        if len(body) + len(chunk) > max_bytes:
            raise WebResearchError("provider_failed")
        body.extend(chunk)
    return bytes(body)


def public_page(url: str, title: str, snippet: str) -> WebPage | None:
    try:
        FetchArguments(url=url)
    except ValueError:
        return None
    return WebPage(url=url, title=title.strip()[:512], snippet=snippet.strip()[:2000])


class DuckDuckGoProvider:
    """Keyless bounded HTML search; no SLA, intended for local use."""

    trusted = False

    def __init__(self, client: httpx.AsyncClient, max_bytes: int) -> None:
        self.client = client
        self.max_bytes = max_bytes

    async def search(self, request: WebSearchRequest, run: Run) -> list[WebPage]:
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
            body = await read_bounded(response, self.max_bytes)

        def parse() -> list[WebPage]:
            from urllib.parse import parse_qs, urlsplit

            import trafilatura

            html = trafilatura.load_html(body)
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
                snippets = node.xpath(
                    './/*[contains(concat(" ", normalize-space(@class), " "), " result__snippet ")]'
                )
                page = public_page(
                    url,
                    link.text_content(),
                    snippets[0].text_content() if snippets else "",
                )
                if page is not None:
                    pages.append(page)
                if len(pages) == request.max_results:
                    break
            if not pages and not html.xpath('//*[contains(@class, "no-results")]'):
                # Captchas/layout changes must never masquerade as empty searches.
                raise WebResearchError("provider_failed")
            return pages

        return await run(parse)


class BraveProvider:
    """Brave Search API: keyed, with SLA; the key only reaches its fixed endpoint."""

    endpoint = "https://api.search.brave.com/res/v1/web/search"
    trusted = False

    def __init__(self, client: httpx.AsyncClient, max_bytes: int, key: str) -> None:
        self.client = client
        self.max_bytes = max_bytes
        self.key = key

    async def search(self, request: WebSearchRequest, run: Run) -> list[WebPage]:
        country = request.region.split("-")[0]
        params = {
            "q": request.query,
            "count": str(min(request.max_results, 20)),
            "safesearch": {"on": "strict", "moderate": "moderate", "off": "off"}[
                request.safesearch
            ],
            "country": "ALL"
            if len(country) != 2 or country == "wt"
            else country.upper(),
        }
        if request.timelimit:
            params["freshness"] = f"p{request.timelimit}"
        async with self.client.stream(
            "GET",
            self.endpoint,
            params=params,
            headers={
                "X-Subscription-Token": self.key,
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Cookie": "",
            },
        ) as response:
            body = await read_bounded(response, self.max_bytes)

        def parse() -> list[WebPage]:
            try:
                items = json.loads(body).get("web", {}).get("results", [])
            except (ValueError, AttributeError):
                raise WebResearchError("provider_failed") from None
            pages = []
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                # Brave highlights matches with inline tags and HTML entities.
                snippet = html_entities.unescape(
                    re.sub(r"<[^>]+>", "", str(item.get("description", "")))
                )
                page = public_page(
                    str(item.get("url", "")), str(item.get("title", "")), snippet
                )
                if page is not None:
                    pages.append(page)
                if len(pages) == request.max_results:
                    break
            return pages

        return await run(parse)


DEFAULT_FIXTURE = (
    (
        "https://www.python.org/",
        "Welcome to Python.org",
        "The official home of the Python programming language.",
    ),
    (
        "https://en.wikipedia.org/wiki/Web_search_engine",
        "Search engine - Wikipedia",
        "A search engine is a software system that finds web pages matching a query.",
    ),
    (
        "https://example.com/",
        "Example Domain",
        "This domain is for use in documentation examples.",
    ),
)


class FixtureProvider:
    """Offline results for development and CI; never contacts a search service."""

    trusted = True

    def __init__(self, pages: list[WebPage]) -> None:
        self.pages = pages

    @classmethod
    def load(cls, path: str | None) -> FixtureProvider:
        if path is None:
            return cls(
                [WebPage(url=u, title=t, snippet=s) for u, t, s in DEFAULT_FIXTURE]
            )
        items = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls([WebPage.model_validate(item) for item in items])

    async def search(self, request: WebSearchRequest, run: Run) -> list[WebPage]:
        del run
        return self.pages[: request.max_results]


def build_provider(
    config: WebResearchDeploymentConfig, client: httpx.AsyncClient
) -> SearchProvider:
    """Startup fails here, not at the first question, when a provider is misconfigured."""
    if config.provider == "fixture":
        return FixtureProvider.load(config.fixture_file)
    if config.provider == "brave":
        key = os.getenv(config.provider_key_env or "", "").strip()
        if not key:
            raise RuntimeError("Configured web research provider key is missing.")
        return BraveProvider(client, config.max_bytes, key)
    return DuckDuckGoProvider(client, config.max_bytes)
