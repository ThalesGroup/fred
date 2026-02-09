from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from langchain_core.tools import tool

from .gateway import GithubGateway

logger = logging.getLogger(__name__)


def _split_repo(repo: str) -> tuple[str, str]:
    if "/" not in repo:
        raise ValueError("Repository must be in 'owner/repo' format")
    owner, name = repo.split("/", 1)
    return owner, name


class GithubTools:
    """LLM tools built on top of GithubGateway."""

    def __init__(self, gateway: GithubGateway, default_repo: Optional[str] = None):
        self._gateway = gateway
        self._default_repo = default_repo

        @tool("github_create_issue", return_direct=True)
        async def create_issue(
            title: str, body: str = "", repo: Optional[str] = None
        ) -> str:
            owner, name = _split_repo(repo or self._require_repo())
            issue = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._gateway.create_issue(
                    owner=owner, repo=name, title=title, body=body or None
                ),
            )
            return _as_json(issue.__dict__)

        @tool("github_comment", return_direct=True)
        async def comment(
            issue_number: int, body: str, repo: Optional[str] = None
        ) -> str:
            owner, name = _split_repo(repo or self._require_repo())
            res = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._gateway.comment_issue(
                    owner=owner, repo=name, issue_number=issue_number, body=body
                ),
            )
            return _as_json(res.__dict__)

        @tool("github_list_issues", return_direct=True)
        async def list_issues(limit: int = 5, repo: Optional[str] = None) -> str:
            owner, name = _split_repo(repo or self._require_repo())
            issues = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: self._gateway.list_open_issues(
                    owner=owner, repo=name, limit=limit
                ),
            )
            return _as_json([iss.__dict__ for iss in issues])

        self._create_tool = create_issue
        self._comment_tool = comment
        self._list_tool = list_issues

    def tools(self):
        return [self._create_tool, self._comment_tool, self._list_tool]

    def _require_repo(self) -> str:
        if not self._default_repo:
            raise ValueError("No default repo configured; pass repo='owner/name'.")
        return self._default_repo


def _as_json(data) -> str:
    try:
        return json.dumps(data, ensure_ascii=False)
    except Exception:  # pragma: no cover
        logger.warning("[GithubTools] JSON dump failed, falling back to str")
        return str(data)
