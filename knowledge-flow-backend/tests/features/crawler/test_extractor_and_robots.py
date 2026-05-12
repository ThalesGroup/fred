import httpx
import pytest

from knowledge_flow_backend.features.crawler.extractor import extract_html
from knowledge_flow_backend.features.crawler.robots import RobotsCache


def test_extract_html_returns_title_text_markdown_and_links():
    page = extract_html(
        """
        <html><head><title>Example</title><script>bad()</script></head>
        <body><h1>Hello</h1><p>Readable text.</p><a href="/next">Next</a></body></html>
        """,
        "https://example.com",
    )

    assert page.title == "Example"
    assert "Readable text." in page.text
    assert "# Example" in page.markdown
    assert "/next" in page.links
    assert "bad()" not in page.text


@pytest.mark.asyncio
async def test_robots_cache_blocks_disallowed_paths():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/robots.txt"
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")

    cache = RobotsCache()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await cache.allowed(client, "https://example.com/public")
        assert not await cache.allowed(client, "https://example.com/private/report")
