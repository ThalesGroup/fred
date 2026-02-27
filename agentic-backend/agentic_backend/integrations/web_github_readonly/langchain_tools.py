from __future__ import annotations

import json
import logging
from typing import Optional

from langchain_core.tools import tool

from .service import WebGithubReadonlyService

logger = logging.getLogger(__name__)


def _as_json(data) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:  # pragma: no cover
        logger.warning("[WebGithubReadonlyTools] JSON dump failed, falling back to str")
        return str(data)


class WebGithubReadonlyTools:
    """
    Local LangChain tools (in-process) for public web/GitHub read-only access.

    Intended for BasicReActAgent or any LangGraph agent that wants grounding
    without requiring an external MCP process.
    """

    def __init__(self, service: Optional[WebGithubReadonlyService] = None):
        self._service = service or WebGithubReadonlyService()

        @tool("web_fetch_url")
        async def web_fetch_url(url: str, max_chars: int = 12000) -> str:
            """Fetch a public URL and return extracted text/metadata (read-only)."""
            return _as_json(
                await self._service.web_fetch_url(url=url, max_chars=max_chars)
            )

        @tool("github_get_repo_metadata")
        async def github_get_repo_metadata(repo_or_url: str) -> str:
            """Fetch public GitHub repository metadata (read-only)."""
            return _as_json(
                await self._service.github_get_repo_metadata(repo_or_url=repo_or_url)
            )

        @tool("github_read_readme")
        async def github_read_readme(
            repo_or_url: str, ref: str = "", max_chars: int = 20000
        ) -> str:
            """Read a repository README through the GitHub API (read-only)."""
            return _as_json(
                await self._service.github_read_readme(
                    repo_or_url=repo_or_url,
                    ref=ref,
                    max_chars=max_chars,
                )
            )

        @tool("github_get_repo_tree")
        async def github_get_repo_tree(
            repo_or_url: str, ref: str = "", max_entries: int = 250
        ) -> str:
            """Return a recursive Git tree summary of a public repository (read-only)."""
            return _as_json(
                await self._service.github_get_repo_tree(
                    repo_or_url=repo_or_url,
                    ref=ref,
                    max_entries=max_entries,
                )
            )

        @tool("github_read_file")
        async def github_read_file(
            repo_or_url: str, path: str, ref: str = "", max_chars: int = 20000
        ) -> str:
            """Read a text file from a public GitHub repository (read-only)."""
            return _as_json(
                await self._service.github_read_file(
                    repo_or_url=repo_or_url,
                    path=path,
                    ref=ref,
                    max_chars=max_chars,
                )
            )

        self._tools = [
            web_fetch_url,
            github_get_repo_metadata,
            github_read_readme,
            github_get_repo_tree,
            github_read_file,
        ]

    def tools(self):
        return list(self._tools)

    async def aclose(self) -> None:
        await self._service.aclose()
