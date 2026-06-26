from __future__ import annotations

import urllib.robotparser
from urllib.parse import urlsplit, urlunsplit

import httpx

from knowledge_flow_backend.features.crawler.url_utils import url_host


class RobotsCache:
    """Fetch and cache robots.txt rules by host."""

    def __init__(self, *, user_agent: str = "FredCrawler") -> None:
        """
        Build an in-memory robots cache for one crawler execution.

        Why this exists:
        - robots.txt is host-scoped and should be fetched at most once per run.

        How to use:
        - call `allowed(client, url)` before fetching a page.
        """
        self.user_agent = user_agent
        self._rules: dict[str, urllib.robotparser.RobotFileParser] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str) -> bool:
        """Return whether `url` is allowed for this crawler user-agent."""
        host = url_host(url)
        parser = self._rules.get(host)
        if parser is None:
            parser = urllib.robotparser.RobotFileParser()
            scheme = urlsplit(url).scheme or "https"
            robots_url = urlunsplit((scheme, host, "/robots.txt", "", ""))
            try:
                response = await client.get(robots_url, follow_redirects=True)
                parser.parse(response.text.splitlines() if response.status_code < 400 else [])
            except httpx.HTTPError:
                parser.parse([])
            self._rules[host] = parser
        return parser.can_fetch(self.user_agent, url)
