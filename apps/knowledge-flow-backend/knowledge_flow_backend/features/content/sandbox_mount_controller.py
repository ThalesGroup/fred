# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Read-only WebDAV source view. XML is serialized, never parsed from clients."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import mimetypes
import os
from contextlib import closing
from email.utils import formatdate
from pathlib import PurePosixPath
from urllib.parse import quote
from xml.etree import ElementTree  # nosec B405

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fred_core import KeycloakUser, get_current_user
from fred_core.common.team_id import is_personal_team_id
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


class _BindCorpus(BaseModel):
    session_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    document_uid: str = Field(min_length=1)


class _BindAttachment(BaseModel):
    session_id: str = Field(min_length=1)
    team_id: str = Field(min_length=1)
    attachment_id: str = Field(min_length=1)


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
        @router.post("/sandbox-mount/views/{key}/corpus")
        async def bind_corpus(request: Request, key: str, body: _BindCorpus, user: KeycloakUser = Depends(get_current_user)) -> dict[str, str]:
            _check_bind_credential(request, key, body.session_id, user.uid, body.team_id)
            try:
                source = await self.store.bind_corpus(
                    key=key,
                    session_id=body.session_id,
                    team_id=body.team_id,
                    user=user,
                    document_uid=body.document_uid,
                    context=self.context,
                )
            except (FileNotFoundError, PermissionError):
                raise HTTPException(404, "Sandbox source is unavailable") from None
            except ValueError:
                raise HTTPException(400, "Sandbox source is invalid") from None
            return {"path": f"/inputs/{source.path}"}

        @router.post("/sandbox-mount/views/{key}/attachments")
        async def bind_attachment(request: Request, key: str, body: _BindAttachment, user: KeycloakUser = Depends(get_current_user)) -> dict[str, str]:
            _check_bind_credential(request, key, body.session_id, user.uid, body.team_id)
            try:
                source = await self.store.bind_attachment(
                    key=key,
                    session_id=body.session_id,
                    team_id=body.team_id,
                    user=user,
                    attachment_id=body.attachment_id,
                    context=self.context,
                )
            except (FileNotFoundError, PermissionError):
                raise HTTPException(404, "Sandbox source is unavailable") from None
            except ValueError:
                raise HTTPException(400, "Sandbox source is invalid") from None
            return {"path": f"/inputs/{source.path}"}

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
                row, sources = await self.store.list_sources(key)
            except PermissionError:
                raise HTTPException(429, "Sandbox view request rate exceeded") from None
            except FileNotFoundError:
                raise HTTPException(404, "Sandbox view is unavailable") from None
            if path:
                sources = [item for item in sources if item.path == path or item.path.startswith(f"{path}/")]
            if row is not None:
                try:
                    await self.store._check_session(row.session_id, row.user_id, row.team_id)
                    rebac = self.context.get_rebac_engine()
                    await rebac.require_active_account(row.user_id)
                    user = KeycloakUser(uid=row.user_id, username=row.user_id, roles=[])
                    if not is_personal_team_id(row.team_id):
                        await rebac.check_user_team_permission_or_raise(user, TeamPermission.CAN_READ, row.team_id)
                except Exception:
                    raise HTTPException(404, "Sandbox view is unavailable") from None
                visible = []
                for item in sources:
                    try:
                        if item.kind == "corpus":
                            current = await authorize_corpus_source(user, row.team_id, item.uid, context=self.context)
                            allowed = current.name == item.name and current.size == item.size
                        elif item.kind == "attachment":
                            original = await self.store.attachment_original(row.session_id, row.user_id, item.uid)
                            allowed = original.name == item.name and original.size == item.size
                        else:
                            allowed = False
                    except Exception:
                        allowed = False
                    if allowed:
                        visible.append(item)
                sources = visible
            source = next((item for item in sources if item.path == path), None)
            directory = path == "" or any(item.path.startswith(f"{path}/") for item in sources)
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
                    for child, item in _child_paths(path, sources):
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
