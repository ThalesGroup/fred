# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Turn returned web pages into citation links shown under the agent's answer."""

from __future__ import annotations

from urllib.parse import urlsplit

from fred_sdk.contracts.context import LinkKind, LinkPart
from fred_sdk.contracts.web_research import WebResearchResult


def citation_parts(result: WebResearchResult) -> tuple[LinkPart, ...]:
    """One citation per distinct public page the model received, in result order."""
    parts: list[LinkPart] = []
    seen: set[str] = set()
    for page in result.results:
        href = page.final_url or page.url
        if (
            page.error_code
            or href in seen
            or urlsplit(href).scheme not in {"http", "https"}
        ):
            continue
        seen.add(href)
        parts.append(
            LinkPart(
                href=href,
                title=page.title or urlsplit(href).hostname,
                kind=LinkKind.citation,
                rel="noopener noreferrer",
            )
        )
    return tuple(parts)
