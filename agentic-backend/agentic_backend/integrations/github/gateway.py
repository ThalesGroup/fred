from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import List

import requests

logger = logging.getLogger(__name__)


@dataclass
class GithubIssue:
    number: int
    title: str
    url: str
    state: str


class GithubGateway:
    """
    Thin wrapper over the GitHub REST API v3 for a few common actions.
    Keep it synchronous; tools/adapters can run it in an executor.
    """

    def __init__(self, token: str, base_url: str = "https://api.github.com"):
        if not token:
            raise ValueError("GitHub token is required")
        self._token = token
        self._base = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "agentic-backend-github-adapter",
            }
        )

    @classmethod
    def from_env(cls, var: str = "GITHUB_TOKEN") -> "GithubGateway":
        token = os.getenv(var)
        if not token:
            raise RuntimeError(f"Missing GitHub token in environment variable {var}")
        return cls(token=token)

    def create_issue(
        self, *, owner: str, repo: str, title: str, body: str | None = None
    ) -> GithubIssue:
        url = f"{self._base}/repos/{owner}/{repo}/issues"
        payload = {"title": title}
        if body:
            payload["body"] = body
        resp = self._session.post(url, json=payload, timeout=15)
        self._raise_for_status(resp)
        data = resp.json()
        return GithubIssue(
            number=data.get("number", 0),
            title=data.get("title", title),
            url=data.get("html_url", ""),
            state=data.get("state", "unknown"),
        )

    def comment_issue(
        self, *, owner: str, repo: str, issue_number: int, body: str
    ) -> GithubIssue:
        url = f"{self._base}/repos/{owner}/{repo}/issues/{issue_number}/comments"
        resp = self._session.post(url, json={"body": body}, timeout=15)
        self._raise_for_status(resp)
        # Return the parent issue lightweight summary (number/url)
        data = resp.json()
        issue_url = data.get("issue_url", "")
        return GithubIssue(
            number=issue_number,
            title=f"commented #{issue_number}",
            url=issue_url,
            state="commented",
        )

    def list_open_issues(
        self, *, owner: str, repo: str, limit: int = 5
    ) -> List[GithubIssue]:
        url = f"{self._base}/repos/{owner}/{repo}/issues"
        params = {"state": "open", "per_page": limit}
        resp = self._session.get(url, params=params, timeout=15)
        self._raise_for_status(resp)
        issues: List[GithubIssue] = []
        for item in resp.json():
            # Skip pull requests (they appear in this endpoint)
            if item.get("pull_request"):
                continue
            issues.append(
                GithubIssue(
                    number=item.get("number", 0),
                    title=item.get("title", ""),
                    url=item.get("html_url", ""),
                    state=item.get("state", "unknown"),
                )
            )
        return issues

    def _raise_for_status(self, resp: requests.Response) -> None:
        try:
            resp.raise_for_status()
        except Exception as exc:  # pragma: no cover
            logger.error("GitHub API error %s: %s", resp.status_code, resp.text.strip())
            raise exc
