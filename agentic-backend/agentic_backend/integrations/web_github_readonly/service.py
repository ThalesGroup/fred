from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import os
import re
import socket
import time
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import quote, urljoin, urlparse

import httpx

_DEFAULT_TIMEOUT_SEC = 15.0
_MAX_HTTP_BYTES = 1_000_000
_MAX_TEXT_CHARS = 40_000
_GITHUB_API_BASE = "https://api.github.com"
_USER_AGENT = "fred-web-github-readonly-tools/1.0"


class _TextHTMLExtractor(HTMLParser):
    """Small HTML -> text extractor for grounding (not full fidelity)."""

    def __init__(self) -> None:
        super().__init__()
        self._title: list[str] = []
        self._chunks: list[str] = []
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
        if tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
        if tag == "title":
            self._capture_title = True
        if tag in {"p", "div", "section", "article", "main", "header", "footer", "li"}:
            self._chunks.append("\n")
        if tag == "br":
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._capture_title = False
        if tag in {"p", "div", "section", "article", "main"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0 or not data.strip():
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


def _normalize_repo(repo_or_url: str) -> tuple[str, str]:
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


class WebGithubReadonlyService:
    """
    Async service used by local LangChain tools (in-process, no MCP wrapper required).
    """

    def __init__(self, timeout_sec: float = _DEFAULT_TIMEOUT_SEC):
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "*/*",
        }
        github_token = os.getenv("GITHUB_TOKEN")
        self._github_auth_header: Optional[str] = (
            f"Bearer {github_token}" if github_token else None
        )
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec),
            headers=headers,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _http_get(
        self,
        url: str,
        *,
        headers: Optional[dict[str, str]] = None,
        max_bytes: int = _MAX_HTTP_BYTES,
        enforce_public_target: bool = False,
        max_redirects: int = 5,
    ) -> dict[str, Any]:
        current_url = url
        redirects_followed = 0

        while True:
            if enforce_public_target:
                err = await self._validate_public_http_target(current_url)
                if err:
                    return {
                        "ok": False,
                        "status": 0,
                        "url": current_url,
                        "error": err,
                        "body": b"",
                        "headers": {},
                        "over_limit": False,
                    }

            try:
                if enforce_public_target:
                    resp = await self._client.get(
                        current_url,
                        headers=headers,
                        follow_redirects=False,
                    )
                else:
                    resp = await self._client.get(current_url, headers=headers)
            except httpx.HTTPError as e:
                return {
                    "ok": False,
                    "status": 0,
                    "url": current_url,
                    "error": f"{type(e).__name__}: {e}",
                    "body": b"",
                    "headers": {},
                    "over_limit": False,
                }

            if (
                enforce_public_target
                and resp.is_redirect
                and resp.headers.get("location")
            ):
                if redirects_followed >= max(0, int(max_redirects)):
                    return {
                        "ok": False,
                        "status": resp.status_code,
                        "url": str(resp.url),
                        "error": f"Too many redirects (>{max_redirects})",
                        "body": b"",
                        "headers": {k.lower(): v for k, v in resp.headers.items()},
                        "over_limit": False,
                    }
                current_url = urljoin(str(resp.url), resp.headers["location"])
                redirects_followed += 1
                continue

            break

        body = resp.content[: max_bytes + 1]
        over_limit = len(body) > max_bytes
        if over_limit:
            body = body[:max_bytes]
        return {
            "ok": resp.is_success,
            "status": resp.status_code,
            "url": str(resp.url),
            "error": None
            if resp.is_success
            else f"HTTP {resp.status_code}: {resp.reason_phrase}",
            "body": body,
            "headers": {k.lower(): v for k, v in resp.headers.items()},
            "over_limit": over_limit,
        }

    @staticmethod
    def _blocked_ip_reason(
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    ) -> Optional[str]:
        if ip.is_loopback:
            return "loopback address"
        if ip.is_link_local:
            return "link-local address"
        if ip.is_private:
            return "private address"
        if ip.is_multicast:
            return "multicast address"
        if ip.is_reserved:
            return "reserved address"
        if ip.is_unspecified:
            return "unspecified address"
        if hasattr(ip, "is_site_local") and getattr(ip, "is_site_local"):
            return "site-local address"
        if not ip.is_global:
            return "non-global address"
        return None

    async def _validate_public_http_target(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return "URL hostname is required"

        normalized_host = hostname.strip().rstrip(".").lower()
        if not normalized_host:
            return "URL hostname is required"
        if normalized_host == "localhost" or normalized_host.endswith(".localhost"):
            return f"Access to local host '{hostname}' is not allowed"

        port = parsed.port
        if port is None:
            port = 443 if parsed.scheme == "https" else 80

        resolved_ips: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []

        try:
            literal_ip = ipaddress.ip_address(normalized_host)
        except ValueError:
            literal_ip = None

        if literal_ip is not None:
            resolved_ips.append(literal_ip)
        else:
            try:
                infos = await asyncio.get_running_loop().getaddrinfo(
                    hostname,
                    port,
                    type=socket.SOCK_STREAM,
                )
            except socket.gaierror as e:
                return f"DNS resolution failed for host '{hostname}': {e}"
            except Exception as e:
                return f"Failed to resolve host '{hostname}': {type(e).__name__}: {e}"

            for family, _, _, _, sockaddr in infos:
                if family not in {socket.AF_INET, socket.AF_INET6}:
                    continue
                if not isinstance(sockaddr, tuple) or not sockaddr:
                    continue
                ip_txt = str(sockaddr[0])
                try:
                    resolved_ips.append(ipaddress.ip_address(ip_txt))
                except ValueError:
                    continue

        if not resolved_ips:
            return f"Could not resolve any IP address for host '{hostname}'"

        seen: set[str] = set()
        for ip in resolved_ips:
            ip_txt = str(ip)
            if ip_txt in seen:
                continue
            seen.add(ip_txt)
            reason = self._blocked_ip_reason(ip)
            if reason:
                return (
                    f"Access to host '{hostname}' is not allowed: "
                    f"resolved to {ip_txt} ({reason})"
                )
        return None

    @staticmethod
    def _json_from_http(resp: dict[str, Any]) -> dict[str, Any]:
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
            data = json.loads(
                (resp.get("body") or b"").decode("utf-8", errors="replace")
            )
        except Exception as e:
            return {
                "ok": False,
                "status": resp.get("status"),
                "error": f"Invalid JSON response: {e}",
            }
        return {
            "ok": True,
            "status": resp.get("status"),
            "url": resp.get("url"),
            "headers": resp.get("headers", {}),
            "data": data,
            "truncated_bytes": bool(resp.get("over_limit")),
        }

    @staticmethod
    def _decode_github_content(
        item: dict[str, Any],
    ) -> tuple[Optional[str], Optional[str]]:
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
            return None, "Binary file content is not supported by this read-only tool"
        return blob.decode("utf-8", errors="replace"), None

    async def _github_json(self, path: str, **query: Any) -> dict[str, Any]:
        q = {k: v for k, v in query.items() if v not in (None, "", False)}
        from urllib.parse import urlencode

        url = f"{_GITHUB_API_BASE.rstrip('/')}/{path.lstrip('/')}"
        if q:
            url = f"{url}?{urlencode(q, doseq=True)}"
        resp = await self._http_get(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                **(
                    {"Authorization": self._github_auth_header}
                    if self._github_auth_header
                    else {}
                ),
            },
        )
        return self._json_from_http(resp)

    async def web_fetch_url(self, url: str, max_chars: int = 12000) -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            return {
                "ok": False,
                "error": "Only http:// and https:// URLs are supported",
            }

        resp = await self._http_get(url, enforce_public_target=True)
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

    async def github_get_repo_metadata(self, repo_or_url: str) -> dict[str, Any]:
        try:
            owner, repo = _normalize_repo(repo_or_url)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        resp = await self._github_json(f"/repos/{owner}/{repo}")
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

    async def github_read_readme(
        self, repo_or_url: str, ref: str = "", max_chars: int = 20000
    ) -> dict[str, Any]:
        try:
            owner, repo = _normalize_repo(repo_or_url)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        resp = await self._github_json(f"/repos/{owner}/{repo}/readme", ref=ref or None)
        if not resp["ok"]:
            return resp

        item = resp["data"]
        content, err = self._decode_github_content(item)
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

    async def github_get_repo_tree(
        self, repo_or_url: str, ref: str = "", max_entries: int = 250
    ) -> dict[str, Any]:
        try:
            owner, repo = _normalize_repo(repo_or_url)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        resolved_ref = ref
        repo_info: Optional[dict[str, Any]] = None
        if not resolved_ref:
            meta = await self._github_json(f"/repos/{owner}/{repo}")
            if not meta["ok"]:
                return meta
            raw_repo_info = meta.get("data")
            if not isinstance(raw_repo_info, dict):
                return {
                    "ok": False,
                    "error": "Invalid GitHub repository metadata payload",
                }
            repo_info = raw_repo_info
            resolved_ref = repo_info.get("default_branch") or "main"

        resp = await self._github_json(
            f"/repos/{owner}/{repo}/git/trees/{quote(resolved_ref, safe='')}",
            recursive=1,
        )
        if not resp["ok"]:
            return resp

        tree = resp["data"].get("tree", [])
        max_entries = max(20, min(int(max_entries), 2000))
        entries = [
            {
                "path": item.get("path"),
                "type": item.get("type"),
                "size": item.get("size"),
                "sha": item.get("sha"),
            }
            for item in tree[:max_entries]
        ]
        return {
            "ok": True,
            "repo": f"{owner}/{repo}",
            "ref": resolved_ref,
            "truncated": len(tree) > len(entries),
            "entry_count": len(tree),
            "entries": entries,
            "default_branch": (repo_info or {}).get("default_branch"),
        }

    async def github_read_file(
        self,
        repo_or_url: str,
        path: str,
        ref: str = "",
        max_chars: int = 20000,
    ) -> dict[str, Any]:
        if not path or not path.strip():
            return {"ok": False, "error": "path is required"}

        try:
            owner, repo = _normalize_repo(repo_or_url)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        clean_path = path.strip().lstrip("/")
        resp = await self._github_json(
            f"/repos/{owner}/{repo}/contents/{quote(clean_path, safe='/')}",
            ref=ref or None,
        )
        if not resp["ok"]:
            return resp

        item = resp["data"]
        if isinstance(item, list):
            return {
                "ok": False,
                "error": "Provided path is a directory, not a file",
                "path": clean_path,
            }

        content, err = self._decode_github_content(item)
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
