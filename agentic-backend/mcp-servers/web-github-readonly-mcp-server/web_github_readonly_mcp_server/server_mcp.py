"""
web_github_readonly_mcp_server/server_mcp.py
-------------------------------------------
Minimal read-only MCP server for public web and GitHub repository inspection.

This server is intended for demo/general-purpose agents that need lightweight
grounding (e.g., inspect a GitHub repo before generating a Mermaid diagram).

Run:
  uvicorn web_github_readonly_mcp_server.server_mcp:app --host 127.0.0.1 --port 9799 --reload
  or: make server

Tools implemented:
  - web_fetch_url(url, max_chars)
  - github_get_repo_metadata(repo_or_url)
  - github_read_readme(repo_or_url, ref, max_chars)
  - github_get_repo_tree(repo_or_url, ref, max_entries)
  - github_read_file(repo_or_url, path, ref, max_chars)
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from html.parser import HTMLParser
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

try:
    from mcp.server import FastMCP
except Exception as e:  # pragma: no cover - helpful import error at startup
    raise ImportError(
        "The 'mcp' package is required for web_github_readonly_mcp_server.\n"
        'Install it via: pip install "mcp[fastapi]"\n'
        f"Import error: {e}"
    )


_DEFAULT_TIMEOUT_SEC = 15
_MAX_HTTP_BYTES = 1_000_000
_MAX_TEXT_CHARS = 40_000
_GITHUB_API_BASE = "https://api.github.com"
_USER_AGENT = "fred-web-github-readonly-mcp/1.0"


server = FastMCP(name="web-github-readonly-mcp")


class _TextHTMLExtractor(HTMLParser):
    """Very small HTML -> text extractor for grounding (not full fidelity)."""

    def __init__(self) -> None:
        super().__init__()
        self._title: list[str] = []
        self._chunks: list[str] = []
        self._tag_stack: list[str] = []
        self._skip_depth = 0
        self._capture_title = False

    @property
    def title(self) -> str:
        return " ".join("".join(self._title).split())

    @property
    def text(self) -> str:
        text = "".join(self._chunks)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        self._tag_stack.append(tag)
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._capture_title = True
        if tag in {"p", "div", "section", "article", "main", "header", "footer"}:
            self._chunks.append("\n")
        if tag in {"br", "li"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack:
            self._tag_stack.pop()
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._capture_title = False
        if tag in {"p", "div", "section", "article", "main"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if not data.strip():
            return
        if self._capture_title:
            self._title.append(data)
            return
        self._chunks.append(data)
        self._chunks.append(" ")


def _safe_text_slice(text: str, max_chars: int) -> tuple[str, bool]:
    limit = max(200, min(int(max_chars), _MAX_TEXT_CHARS))
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _build_headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "*/*",
    }
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"
    if extra:
        headers.update(extra)
    return headers


def _http_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
    max_bytes: int = _MAX_HTTP_BYTES,
) -> Dict[str, Any]:
    req = Request(url, headers=_build_headers(headers))
    try:
        with urlopen(req, timeout=timeout_sec) as resp:
            body = resp.read(max_bytes + 1)
            over_limit = len(body) > max_bytes
            if over_limit:
                body = body[:max_bytes]
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            return {
                "ok": True,
                "status": getattr(resp, "status", 200),
                "url": resp.geturl(),
                "headers": resp_headers,
                "body": body,
                "over_limit": over_limit,
            }
    except HTTPError as e:
        body = b""
        try:
            body = e.read()
        except Exception:
            pass
        return {
            "ok": False,
            "status": getattr(e, "code", 0),
            "url": url,
            "error": f"HTTPError {getattr(e, 'code', '?')}: {e.reason}",
            "body": body,
            "headers": {},
            "over_limit": False,
        }
    except URLError as e:
        return {
            "ok": False,
            "status": 0,
            "url": url,
            "error": f"URLError: {e.reason}",
            "body": b"",
            "headers": {},
            "over_limit": False,
        }


def _json_from_http(resp: Dict[str, Any]) -> Dict[str, Any]:
    if not resp["ok"]:
        detail = None
        body = resp.get("body") or b""
        if body:
            try:
                detail = json.loads(body.decode("utf-8", errors="replace"))
            except Exception:
                detail = body.decode("utf-8", errors="replace")[:500]
        return {
            "ok": False,
            "status": resp.get("status"),
            "error": resp.get("error", "HTTP request failed"),
            "detail": detail,
        }
    try:
        data = json.loads((resp.get("body") or b"").decode("utf-8", errors="replace"))
        return {
            "ok": True,
            "status": resp.get("status"),
            "url": resp.get("url"),
            "headers": resp.get("headers", {}),
            "data": data,
            "truncated_bytes": bool(resp.get("over_limit")),
        }
    except Exception as e:
        return {
            "ok": False,
            "status": resp.get("status"),
            "error": f"Invalid JSON response: {e}",
        }


def _normalize_repo(repo_or_url: str) -> Tuple[str, str]:
    value = (repo_or_url or "").strip()
    if not value:
        raise ValueError("repo_or_url is required")

    if value.startswith(("http://", "https://")):
        parsed = urlparse(value)
        if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
            raise ValueError("Only github.com repository URLs are supported")
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) < 2:
            raise ValueError("GitHub repository URL must include /owner/repo")
        owner, repo = parts[0], parts[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        return owner, repo

    if "/" not in value:
        raise ValueError("Repository must be in 'owner/repo' format")
    owner, repo = value.split("/", 1)
    repo = repo[:-4] if repo.endswith(".git") else repo
    if not owner or not repo:
        raise ValueError("Invalid repo_or_url")
    return owner, repo


def _github_api_url(path: str, **query: Any) -> str:
    q = {k: v for k, v in query.items() if v not in (None, "", False)}
    base = f"{_GITHUB_API_BASE.rstrip('/')}/{path.lstrip('/')}"
    if not q:
        return base
    from urllib.parse import urlencode

    return f"{base}?{urlencode(q, doseq=True)}"


def _github_json(path: str, **query: Any) -> Dict[str, Any]:
    return _json_from_http(
        _http_get(
            _github_api_url(path, **query),
            headers={"Accept": "application/vnd.github+json"},
        )
    )


def _github_get_default_branch(owner: str, repo: str) -> Dict[str, Any]:
    info = _github_json(f"/repos/{owner}/{repo}")
    if not info["ok"]:
        return info
    data = info["data"]
    return {
        "ok": True,
        "repo_data": data,
        "default_branch": data.get("default_branch") or "main",
    }


def _decode_github_content(item: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if item.get("encoding") != "base64":
        return None, "Unsupported encoding (expected base64)"
    raw = item.get("content", "")
    if not isinstance(raw, str):
        return None, "Invalid GitHub content payload"
    cleaned = raw.replace("\n", "")
    try:
        blob = base64.b64decode(cleaned)
    except Exception as e:
        return None, f"Base64 decode error: {e}"
    if b"\x00" in blob:
        return None, "Binary file content is not supported by this read-only demo tool"
    return blob.decode("utf-8", errors="replace"), None


@server.tool()
async def web_fetch_url(url: str, max_chars: int = 12000) -> Dict[str, Any]:
    """Fetch a public web URL (GET, read-only) and return normalized text."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return {"ok": False, "error": "Only http:// and https:// URLs are supported"}

    resp = _http_get(url)
    if not resp["ok"]:
        out = {
            "ok": False,
            "url": url,
            "status": resp.get("status"),
            "error": resp.get("error", "HTTP request failed"),
        }
        body = resp.get("body") or b""
        if body:
            out["body_preview"] = body.decode("utf-8", errors="replace")[:500]
        return out

    content_type = (resp.get("headers", {}).get("content-type") or "").lower()
    body = resp.get("body") or b""
    if not any(
        t in content_type
        for t in (
            "text/",
            "application/json",
            "application/xml",
            "application/xhtml+xml",
            "application/javascript",
        )
    ):
        return {
            "ok": False,
            "url": resp.get("url", url),
            "status": resp.get("status"),
            "content_type": content_type or None,
            "error": "Unsupported content type for text extraction",
        }

    charset = "utf-8"
    if "charset=" in content_type:
        charset = (
            content_type.split("charset=", 1)[1].split(";", 1)[0].strip() or "utf-8"
        )
    text = body.decode(charset, errors="replace")

    title = None
    normalized_text = text
    if "text/html" in content_type or "application/xhtml+xml" in content_type:
        parser = _TextHTMLExtractor()
        parser.feed(text)
        title = parser.title or None
        normalized_text = parser.text

    preview, truncated_chars = _safe_text_slice(normalized_text, max_chars)
    return {
        "ok": True,
        "url": resp.get("url", url),
        "requested_url": url,
        "status": resp.get("status"),
        "content_type": content_type or None,
        "title": title,
        "text": preview,
        "truncated_chars": truncated_chars,
        "truncated_bytes": bool(resp.get("over_limit")),
        "fetched_at_ts": int(time.time()),
    }


@server.tool()
async def github_get_repo_metadata(repo_or_url: str) -> Dict[str, Any]:
    """Fetch public GitHub repository metadata (read-only)."""
    try:
        owner, repo = _normalize_repo(repo_or_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    resp = _github_json(f"/repos/{owner}/{repo}")
    if not resp["ok"]:
        return resp
    data = resp["data"]
    return {
        "ok": True,
        "repo": f"{owner}/{repo}",
        "name": data.get("name"),
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "private": data.get("private"),
        "default_branch": data.get("default_branch"),
        "language": data.get("language"),
        "topics": data.get("topics", []),
        "stargazers_count": data.get("stargazers_count"),
        "forks_count": data.get("forks_count"),
        "open_issues_count": data.get("open_issues_count"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "homepage": data.get("homepage"),
        "html_url": data.get("html_url"),
        "pushed_at": data.get("pushed_at"),
        "updated_at": data.get("updated_at"),
    }


@server.tool()
async def github_read_readme(
    repo_or_url: str,
    ref: str = "",
    max_chars: int = 20000,
) -> Dict[str, Any]:
    """Read the repository README via the GitHub API (read-only)."""
    try:
        owner, repo = _normalize_repo(repo_or_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    resp = _github_json(f"/repos/{owner}/{repo}/readme", ref=ref or None)
    if not resp["ok"]:
        return resp

    item = resp["data"]
    content, err = _decode_github_content(item)
    if err:
        return {"ok": False, "error": err}
    preview, truncated = _safe_text_slice(content or "", max_chars)
    return {
        "ok": True,
        "repo": f"{owner}/{repo}",
        "ref": ref or None,
        "path": item.get("path"),
        "name": item.get("name"),
        "sha": item.get("sha"),
        "html_url": item.get("html_url"),
        "download_url": item.get("download_url"),
        "content": preview,
        "truncated": truncated,
        "size_bytes": item.get("size"),
    }


@server.tool()
async def github_get_repo_tree(
    repo_or_url: str,
    ref: str = "",
    max_entries: int = 250,
) -> Dict[str, Any]:
    """Return a (recursive) Git tree summary for a public GitHub repository."""
    try:
        owner, repo = _normalize_repo(repo_or_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    resolved_ref = ref
    repo_info: Optional[Dict[str, Any]] = None
    if not resolved_ref:
        meta = _github_get_default_branch(owner, repo)
        if not meta["ok"]:
            return meta
        resolved_ref = meta["default_branch"]
        repo_info = meta["repo_data"]

    resp = _github_json(
        f"/repos/{owner}/{repo}/git/trees/{quote(resolved_ref, safe='')}", recursive=1
    )
    if not resp["ok"]:
        return resp

    tree = resp["data"].get("tree", [])
    max_entries = max(20, min(int(max_entries), 2000))
    entries = []
    for item in tree[:max_entries]:
        entries.append(
            {
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size"),
                "sha": item.get("sha"),
            }
        )
    return {
        "ok": True,
        "repo": f"{owner}/{repo}",
        "ref": resolved_ref,
        "truncated": len(tree) > len(entries),
        "entry_count": len(tree),
        "entries": entries,
        "default_branch": (repo_info or {}).get("default_branch"),
    }


@server.tool()
async def github_read_file(
    repo_or_url: str,
    path: str,
    ref: str = "",
    max_chars: int = 20000,
) -> Dict[str, Any]:
    """Read a text file from a public GitHub repository (read-only)."""
    if not path or not path.strip():
        return {"ok": False, "error": "path is required"}

    try:
        owner, repo = _normalize_repo(repo_or_url)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    clean_path = path.strip().lstrip("/")
    api_path = f"/repos/{owner}/{repo}/contents/{quote(clean_path, safe='/')}"
    resp = _github_json(api_path, ref=ref or None)
    if not resp["ok"]:
        return resp

    item = resp["data"]
    if isinstance(item, list):
        return {
            "ok": False,
            "error": "Provided path is a directory, not a file",
            "path": clean_path,
        }

    content, err = _decode_github_content(item)
    if err:
        return {"ok": False, "error": err, "path": clean_path}

    preview, truncated = _safe_text_slice(content or "", max_chars)
    return {
        "ok": True,
        "repo": f"{owner}/{repo}",
        "path": clean_path,
        "ref": ref or None,
        "name": item.get("name"),
        "sha": item.get("sha"),
        "size_bytes": item.get("size"),
        "html_url": item.get("html_url"),
        "download_url": item.get("download_url"),
        "content": preview,
        "truncated": truncated,
    }


app = server.streamable_http_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "web_github_readonly_mcp_server.server_mcp:app",
        host="127.0.0.1",
        port=9799,
        reload=False,
    )
