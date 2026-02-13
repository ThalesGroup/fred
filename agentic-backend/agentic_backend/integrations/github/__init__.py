"""
Minimal GitHub adapter: gateway + LLM tools.

Intended usage:
- programmatic: instantiate `GithubGateway` (ideally via `from_env()`);
- LLM: wrap with `GithubTools` to expose create/comment/list issue helpers.
"""

from .gateway import GithubGateway, GithubIssue  # noqa: F401
from .tools import GithubTools  # noqa: F401
