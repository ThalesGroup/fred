# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
DuckDuckGo web search inprocess toolkit.

Provides a single `web_search` LangChain tool that searches the web via
DuckDuckGo. No API key or account required. Registered as provider
"web_search_google" so existing mcp_catalog.yaml and agent definitions
need no change.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import BaseTool, tool

logger = logging.getLogger(__name__)


def _ddg_search(query: str, num_results: int = 5) -> str:
    try:
        from ddgs import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=num_results))
    except Exception as exc:
        logger.warning("DuckDuckGo search error: %s", exc)
        return f"Web search failed: {exc}"

    if not results:
        return f"No results found for: {query}"

    formatted = [
        {"title": r.get("title"), "link": r.get("href"), "snippet": r.get("body")}
        for r in results
    ]
    return json.dumps(formatted, ensure_ascii=False, indent=2)


@tool
def web_search(query: str, num_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo and return titles, URLs, and snippets.

    Use this tool to find current information, news, recent events, or any topic
    that benefits from live web results. Returns up to num_results results.

    Args:
        query: The search query string.
        num_results: Number of results to return (1-10, default 5).
    """
    return _ddg_search(query, num_results=min(max(num_results, 1), 10))


class GoogleSearchToolkit:
    """Inprocess toolkit that exposes the Google Custom Search tool."""

    def tools(self) -> list[BaseTool]:
        return [web_search]


def inprocess_toolkit_factory(provider: str | None) -> GoogleSearchToolkit | None:
    """
    Map inprocess provider names to toolkit instances.

    How to use it:
    - pass this as `inprocess_toolkit_factory` to `create_agent_app` in main.py
    - add new providers here as the pod grows
    """
    if provider == "web_search_google":
        return GoogleSearchToolkit()
    return None
