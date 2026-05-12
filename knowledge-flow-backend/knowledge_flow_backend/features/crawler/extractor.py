from __future__ import annotations

import re
from dataclasses import dataclass

from bs4 import BeautifulSoup


@dataclass(frozen=True)
class ExtractedPage:
    title: str | None
    text: str
    markdown: str
    links: list[str]


def extract_html(html: str, base_url: str) -> ExtractedPage:
    """
    Extract crawlable content and links from HTML without LLMs.

    Why this exists:
    - the crawler should produce deterministic Markdown/text for the existing
      ingestion pipeline and discover links from ordinary server-rendered pages.

    How to use:
    - call with response HTML and its final URL.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "template", "svg"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else None
    links = [a.get("href", "") for a in soup.find_all("a", href=True)]
    text = re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True)).strip()

    markdown_lines: list[str] = []
    if title:
        markdown_lines.append(f"# {title}")
        markdown_lines.append("")
    for heading in soup.find_all(["h1", "h2", "h3"]):
        level = int(heading.name[1])
        value = heading.get_text(" ", strip=True)
        if value:
            markdown_lines.append(f"{'#' * level} {value}")
            markdown_lines.append("")
    for paragraph in soup.find_all(["p", "li"]):
        value = paragraph.get_text(" ", strip=True)
        if value:
            prefix = "- " if paragraph.name == "li" else ""
            markdown_lines.append(f"{prefix}{value}")
            markdown_lines.append("")
    markdown = "\n".join(markdown_lines).strip() or text
    return ExtractedPage(title=title, text=text, markdown=markdown, links=links)
