# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read-only WebDAV source view. XML is serialized, never parsed from clients."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import mimetypes
import os
import re
from contextlib import closing
from email.utils import formatdate
from pathlib import PurePosixPath
from urllib.parse import quote
from xml.etree import ElementTree  # nosec B405

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common.team_id import is_personal_team_id
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.rebac_engine import TeamPermission
from pydantic import BaseModel, Field

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.content.content_controller import resolve_range_window
from knowledge_flow_backend.features.content.sandbox_scope import authorize_corpus_source
from knowledge_flow_backend.features.content.sandbox_views import (
    VIEW_KEY_RE,
    MountedSource,
    SandboxViewStore,
)

DAV = "DAV:"
ElementTree.register_namespace("D", DAV)


class _OpenView(BaseModel):
    session_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)


def _gateway_secret() -> bytes:
    value = os.getenv("SANDBOX_FILE_GATEWAY_SECRET", "")
    if len(value) < 32:
        raise HTTPException(503, "Sandbox file gateway is unavailable")
    return value.encode()


def _check_mount_credential(request: Request, key: str) -> None:
    if not VIEW_KEY_RE.fullmatch(key):
        raise HTTPException(404, "Sandbox view is unavailable")
    expected = hmac.new(_gateway_secret(), b"fred-sandbox-files-v1\0" + key.encode(), hashlib.sha256).hexdigest()
    authorization = request.headers.get("authorization", "")
    if not hmac.compare_digest(authorization, f"Bearer {expected}"):
        raise HTTPException(401, "Sandbox mount credential refused")


def _check_bind_credential(request: Request, key: str, session_id: str, user_id: str, team_id: str) -> None:
    if not VIEW_KEY_RE.fullmatch(key):
        raise HTTPException(404, "Sandbox view is unavailable")
    payload = b"\0".join((b"fred-sandbox-files-bind-v1", key.encode(), session_id.encode(), user_id.encode(), team_id.encode()))
    expected = hmac.new(_gateway_secret(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(request.headers.get("x-fred-sandbox-bind", ""), expected):
        raise HTTPException(401, "Sandbox file binding refused")


def _safe_path(path: str) -> str:
    if path in {"", "/"}:
        return ""
    parts = path.strip("/").split("/")
    if any(part in {"", ".", ".."} or "\\" in part or "\x00" in part for part in parts):
        raise HTTPException(404, "Sandbox file is unavailable")
    if str(PurePosixPath(*parts)) != "/".join(parts):
        raise HTTPException(404, "Sandbox file is unavailable")
    return "/".join(parts)


def _child_paths(path: str, sources: list[MountedSource]) -> list[tuple[str, MountedSource | None]]:
    prefix = f"{path}/" if path else ""
    children: dict[str, MountedSource | None] = {}
    for source in sources:
        if not source.path.startswith(prefix):
            continue
        remainder = source.path[len(prefix) :]
        if not remainder:
            continue
        name, separator, _ = remainder.partition("/")
        child = prefix + name
        children[child] = None if separator else source
    return sorted(children.items())


def _corpus_page_number(parts: list[str]) -> int:
    if len(parts) not in {7, 8}:
        raise FileNotFoundError
    outer, inner, label = parts[4:7]
    match = re.fullmatch(r"page-([0-9]{4,6})", label)
    if not re.fullmatch(r"block-[0-9]{2}", outer) or not re.fullmatch(r"block-[0-9]{2}", inner) or match is None:
        raise FileNotFoundError
    page = int(match.group(1))
    if label != f"page-{page:04d}" or page // 10000 != int(outer[6:]) or (page // 100) % 100 != int(inner[6:]):
        raise FileNotFoundError
    return page


def _href(request: Request, key: str, path: str, directory: bool) -> str:
    base = request.url.path.split(f"/sandbox-mount/{key}", 1)[0]
    encoded = "/".join(quote(part, safe="") for part in path.split("/") if part)
    suffix = f"/{encoded}" if encoded else ""
    return f"{base}/sandbox-mount/{key}{suffix}{'/' if directory else ''}"


def _dav_entry(root: ElementTree.Element, href: str, size: int | None) -> None:
    response = ElementTree.SubElement(root, f"{{{DAV}}}response")
    ElementTree.SubElement(response, f"{{{DAV}}}href").text = href
    propstat = ElementTree.SubElement(response, f"{{{DAV}}}propstat")
    prop = ElementTree.SubElement(propstat, f"{{{DAV}}}prop")
    kind = ElementTree.SubElement(prop, f"{{{DAV}}}resourcetype")
    ElementTree.SubElement(prop, f"{{{DAV}}}getlastmodified").text = formatdate(usegmt=True)
    if size is None:
        ElementTree.SubElement(kind, f"{{{DAV}}}collection")
    else:
        ElementTree.SubElement(prop, f"{{{DAV}}}getcontentlength").text = str(size)
        ElementTree.SubElement(prop, f"{{{DAV}}}getcontenttype").text = mimetypes.guess_type(href)[0] or "application/octet-stream"
    ElementTree.SubElement(propstat, f"{{{DAV}}}status").text = "HTTP/1.1 200 OK"


def _stream(handle):
    with closing(handle):
        while chunk := handle.read(64 * 1024):
            yield chunk


class SandboxMountController:
    def __init__(self, router: APIRouter, mount_router: APIRouter) -> None:
        self.context = ApplicationContext.get_instance()
        self.store = SandboxViewStore(self.context.get_pg_async_engine())
        self._register_binding(router)
        self._register_mount(mount_router)

    def _register_binding(self, router: APIRouter) -> None:
        @router.post("/sandbox-mount/views/{key}")
        async def open_view(request: Request, key: str, body: _OpenView, user: KeycloakUser = Depends(get_current_user)) -> dict[str, str]:
            _check_bind_credential(request, key, body.session_id, user.uid, body.team_id)
            try:
                await self.store.ensure_view(
                    key=key,
                    session_id=body.session_id,
                    team_id=body.team_id,
                    user=user,
                    context=self.context,
                )
            except (FileNotFoundError, PermissionError):
                raise HTTPException(404, "Sandbox view is unavailable") from None
            except ValueError:
                raise HTTPException(400, "Sandbox view is invalid") from None
            return {"path": "/inputs"}

    def _register_mount(self, router: APIRouter) -> None:
        @router.delete("/sandbox-mount/views/{key}", status_code=204)
        async def revoke_view(request: Request, key: str) -> Response:
            if not VIEW_KEY_RE.fullmatch(key):
                raise HTTPException(404, "Sandbox view is unavailable")
            expected = hmac.new(_gateway_secret(), b"fred-sandbox-files-revoke-v1\0" + key.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {expected}"):
                raise HTTPException(401, "Sandbox view revocation refused")
            await self.store.revoke(key)
            return Response(status_code=204)

        async def handle_mount(request: Request, key: str, path: str = "") -> Response:
            _check_mount_credential(request, key)
            path = _safe_path(path)
            try:
                row = await self.store.get_view(key)
            except PermissionError:
                raise HTTPException(429, "Sandbox view request rate exceeded") from None
            except FileNotFoundError:
                raise HTTPException(404, "Sandbox view is unavailable") from None
            if row is not None:
                sources: list[MountedSource] = []
                try:
                    await self.store._check_session(row.session_id, row.user_id, row.team_id)
                    rebac = self.context.get_rebac_engine()
                    if isinstance(rebac, NoopRebacEngine):
                        raise PermissionError("Sandbox file mounts require access control")
                    await rebac.require_active_account(row.user_id)
                    user = KeycloakUser(uid=row.user_id, username=row.user_id, roles=[])
                    if not is_personal_team_id(row.team_id):
                        await rebac.check_user_team_permission_or_raise(user, TeamPermission.CAN_READ, row.team_id)
                except Exception:
                    raise HTTPException(404, "Sandbox view is unavailable") from None
                parts = path.split("/") if path else []
                children: list[tuple[str, MountedSource | None]] = []
                directory = path in {"", "corpus", "attachments"}
                source_verified = False
                try:
                    if parts and parts[0] == "corpus":
                        if len(parts) == 1:
                            children = [("corpus/libraries", None)]
                            sources = []
                        elif parts[1] == "libraries":
                            if len(parts) == 2:
                                libraries = await self.store.corpus_libraries(user, row.team_id, context=self.context)
                                children = [(f"corpus/libraries/{tag_id}", None) for tag_id in sorted(libraries)]
                                directory, sources = True, []
                            elif len(parts) == 3:
                                await self.store.corpus_page_count(user, row.team_id, parts[2], context=self.context)
                                children = [(f"{path}/pages", None)]
                                directory, sources = True, []
                            elif len(parts) >= 4 and parts[3] == "pages":
                                if len(parts) in {4, 5, 6, 7}:
                                    count = await self.store.corpus_page_count(user, row.team_id, parts[2], context=self.context)
                                    if count > 1_000_000:
                                        raise ValueError("Corpus page limit exceeded")
                                    if len(parts) == 4:
                                        children = [(f"{path}/block-{index:02d}", None) for index in range(min(100, (count + 9999) // 10000))]
                                    elif len(parts) == 5 and re.fullmatch(r"block-[0-9]{2}", parts[4]):
                                        outer = int(parts[4][6:])
                                        if outer * 10000 >= count:
                                            raise FileNotFoundError
                                        remaining = count - outer * 10000
                                        children = [(f"{path}/block-{index:02d}", None) for index in range(min(100, (remaining + 99) // 100))]
                                    elif len(parts) == 6 and all(re.fullmatch(r"block-[0-9]{2}", part) for part in parts[4:6]):
                                        first = int(parts[4][6:]) * 10000 + int(parts[5][6:]) * 100
                                        if first >= count:
                                            raise FileNotFoundError
                                        children = [(f"{path}/page-{index:04d}", None) for index in range(first, min(first + 100, count))]
                                    elif len(parts) == 7:
                                        page = _corpus_page_number(parts)
                                        if page >= count:
                                            raise FileNotFoundError
                                        sources, _ = await self.store.corpus_page(user, row.team_id, parts[2], page, base_path=path, context=self.context)
                                        children = _child_paths(path, sources)
                                    else:
                                        raise FileNotFoundError
                                    directory = True
                                elif len(parts) == 8:
                                    _corpus_page_number(parts)
                                    uid, marker, name = parts[7].partition("--")
                                    if not uid or not marker:
                                        raise FileNotFoundError
                                    current = await authorize_corpus_source(user, row.team_id, uid, context=self.context)
                                    metadata = await self.context.get_metadata_store().get_metadata_by_uid(uid)
                                    if name != current.name or metadata is None or parts[2] not in (metadata.tags.tag_ids or ()):
                                        raise FileNotFoundError
                                    sources = [MountedSource(path, "corpus", uid, current.name, current.size)]
                                    source_verified = True
                                else:
                                    raise FileNotFoundError
                            else:
                                sources = []
                        elif len(parts) in {2, 3}:
                            current = await authorize_corpus_source(user, row.team_id, parts[1], context=self.context)
                            item = MountedSource(
                                f"corpus/{current.document_uid}/{current.name}",
                                "corpus",
                                current.document_uid,
                                current.name,
                                current.size,
                            )
                            sources = [item]
                            source_verified = True
                        else:
                            sources = []
                    elif parts and parts[0] == "attachments":
                        sources = await self.store.attachment_sources(row.session_id, row.user_id)
                    else:
                        sources = []
                except (FileNotFoundError, PermissionError, ValueError):
                    sources = []
                if path:
                    sources = [item for item in sources if item.path == path or item.path.startswith(f"{path}/")]
            else:
                raise HTTPException(404, "Sandbox view is unavailable")
            source = next((item for item in sources if item.path == path), None)
            directory = directory or any(item.path.startswith(f"{path}/") for item in sources)
            if source is None and not directory:
                raise HTTPException(404, "Sandbox file is unavailable")

            if request.method == "OPTIONS":
                return Response(headers={"DAV": "1", "Allow": "OPTIONS, PROPFIND, HEAD, GET"})
            if request.method == "PROPFIND":
                depth = request.headers.get("depth", "0")
                if depth not in {"0", "1"}:
                    raise HTTPException(403, "WebDAV depth is unavailable")
                root = ElementTree.Element(f"{{{DAV}}}multistatus")
                _dav_entry(root, _href(request, key, path, directory), source.size if source is not None else None)
                if directory and depth == "1":
                    children = [("corpus", None), ("attachments", None)] if path == "" else children or _child_paths(path, sources)
                    for child, item in children:
                        _dav_entry(root, _href(request, key, child, item is None), item.size if item else None)
                return Response(
                    ElementTree.tostring(root, encoding="utf-8", xml_declaration=True),
                    status_code=207,
                    media_type="application/xml",
                )
            if source is None:
                raise HTTPException(405, "Directory body is unavailable")

            if row is None:
                raise HTTPException(404, "Sandbox file is unavailable")
            user = KeycloakUser(uid=row.user_id, username=row.user_id, roles=[])
            try:
                if source.kind == "corpus":
                    if not source_verified:
                        current = await authorize_corpus_source(user, row.team_id, source.uid, context=self.context)
                        if current.name != source.name or current.size != source.size:
                            raise FileNotFoundError
                    object_key = None
                elif source.kind == "attachment":
                    original = await self.store.attachment_original(row.session_id, row.user_id, source.uid)
                    if original.name != source.name or original.size != source.size:
                        raise FileNotFoundError
                    object_key = original.object_key
                else:
                    raise FileNotFoundError
            except Exception:
                raise HTTPException(404, "Sandbox file is unavailable") from None

            window = resolve_range_window(request.headers.get("range"), source.size)
            start, end = window if window is not None else (0, source.size - 1)
            length = max(0, end - start + 1)
            headers = {"Content-Length": str(length), "Accept-Ranges": "bytes"}
            if window is not None:
                headers["Content-Range"] = f"bytes {start}-{end}/{source.size}"
            media_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
            if request.method == "HEAD":
                return Response(status_code=206 if window else 200, headers=headers, media_type=media_type)
            if length == 0:
                return Response(b"", status_code=200, headers=headers, media_type=media_type)
            try:
                await self.store.reserve_bytes(key, length)
                content_store = self.context.get_content_store()
                if source.kind == "corpus":
                    handle = await asyncio.to_thread(content_store.get_content_range, source.uid, start, length)
                else:
                    if object_key is None:
                        raise FileNotFoundError
                    handle = await asyncio.to_thread(content_store.get_object_stream, object_key, start=start, length=length)
            except (FileNotFoundError, PermissionError, ValueError):
                raise HTTPException(404, "Sandbox file is unavailable") from None
            return StreamingResponse(
                _stream(handle),
                status_code=206 if window else 200,
                headers=headers,
                media_type=media_type,
            )

        @router.api_route("/sandbox-mount/{key}", methods=["OPTIONS", "PROPFIND", "HEAD", "GET"])
        @router.api_route("/sandbox-mount/{key}/", methods=["OPTIONS", "PROPFIND", "HEAD", "GET"])
        async def mount_root(request: Request, key: str) -> Response:
            return await handle_mount(request, key)

        @router.api_route("/sandbox-mount/{key}/{path:path}", methods=["OPTIONS", "PROPFIND", "HEAD", "GET"])
        async def mount_file(request: Request, key: str, path: str) -> Response:
            return await handle_mount(request, key, path)
