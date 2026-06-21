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

import logging
import mimetypes
from typing import Annotated

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from pydantic import BaseModel

from knowledge_flow_backend.features.filesystem.download_token import (
    DEFAULT_DOWNLOAD_TTL_SECONDS,
    make_download_token,
    verify_download_token,
)
from knowledge_flow_backend.features.filesystem.mcp_fs_service import McpFilesystemService
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    FileReadPage,
    absolute_virtual_path,
    normalize_virtual_path,
)

logger = logging.getLogger(__name__)


class ShareFileResponse(BaseModel):
    """
    A signed, short-TTL download link for an existing workspace file (FILES-04, RFC §7.4).

    Returned by `share_file` so an agent can hand a file back to the user as a clickable link.
    The file also remains in the user's space, so an expired link is never a dead end.
    """

    download_url: str
    file_name: str
    size: int | None = None
    mime: str | None = None


class EditFileRequest(BaseModel):
    """
    Exact text replacement request for the virtual filesystem.

    Why this exists:
    - standard coding-oriented filesystem tools need one compact edit payload
    - using a small request model keeps the HTTP route explicit and easy to consume

    How to use:
    - pass the exact `old_string` to replace plus the `new_string`
    - set `replace_all=true` only when all matches should be replaced

    Example:
    - `{"old_string": "draft", "new_string": "final", "replace_all": false}`
    """

    old_string: str
    new_string: str
    replace_all: bool = False


class McpFilesystemController:
    """
    Controller exposing filesystem operations via API.
    Works directly with the selected backend (local or MinIO).
    """

    def __init__(self, router: APIRouter):
        self.service = McpFilesystemService()
        self._register_routes(router)

    # ----------- Helpers -----------

    @staticmethod
    def _download_href(request: Request, path: str) -> str:
        """Build the origin-relative `/fs/download/{path}` href for any `/fs/*` request."""
        full = request.url.path
        index = full.find("/fs/")
        prefix = full[:index] if index >= 0 else ""
        return f"{prefix}/fs/download/{normalize_virtual_path(path)}"

    def _handle_exception(self, e: Exception, context: str):
        if isinstance(e, PermissionError):
            raise HTTPException(403, str(e))
        if isinstance(e, FileNotFoundError):
            raise HTTPException(404, str(e) or "Path not found")
        if isinstance(e, ValueError):
            raise HTTPException(400, str(e))
        logger.exception("%s failed", context)
        raise HTTPException(500, "Internal server error")

    # ----------- Routes -----------

    def _register_routes(self, router: APIRouter):
        @router.get("/fs/list", tags=["Filesystem"], summary="List a directory", operation_id="ls")
        async def list_entries(
            path: str = "/",
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.ls(user, path)
            except Exception as e:
                self._handle_exception(e, "List")

        @router.get("/fs/stat/{path:path}", tags=["Filesystem"], summary="Get file information", operation_id="stat_file_or_directory")
        async def stat(
            path: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.stat(user, path)
            except Exception as e:
                self._handle_exception(e, "Stat")

        @router.get("/fs/cat/{path:path}", tags=["Filesystem"], summary="Read a file", operation_id="read_file")
        async def cat(
            path: str,
            offset: Annotated[int, Query(ge=0)] = 0,
            limit: Annotated[int | None, Query(ge=1)] = None,
            max_chars: Annotated[int | None, Query(ge=1)] = None,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.read_file(
                    user,
                    path,
                    offset=offset,
                    limit=limit,
                    max_chars=max_chars,
                )
            except Exception as e:
                self._handle_exception(e, "Cat")

        @router.get(
            "/fs/page/{path:path}",
            tags=["Filesystem"],
            summary="Read a paginated file page",
            operation_id="read_file_page",
            response_model=FileReadPage,
        )
        async def read_file_page(
            path: str,
            offset: Annotated[int, Query(ge=0)] = 0,
            limit: Annotated[int | None, Query(ge=1)] = None,
            max_chars: Annotated[int | None, Query(ge=1)] = None,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.read_file_page(
                    user,
                    path,
                    offset=offset,
                    limit=limit,
                    max_chars=max_chars,
                )
            except Exception as e:
                self._handle_exception(e, "ReadFilePage")

        @router.post("/fs/write/{path:path}", tags=["Filesystem"], summary="Write a file", operation_id="write_file")
        async def write(path: str, data: str = Body(..., embed=True), user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                return await self.service.write(user, path, data)
            except Exception as e:
                self._handle_exception(e, "Write")

        @router.delete("/fs/delete/{path:path}", tags=["Filesystem"], summary="Delete a file", operation_id="delete_file")
        async def delete(path: str, user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.DELETE, Resource.FILES)
            try:
                return await self.service.delete(user, path)
            except Exception as e:
                self._handle_exception(e, "Delete")

        @router.post("/fs/upload/{path:path}", tags=["Filesystem"], summary="Upload a binary file", operation_id="upload_file")
        async def upload(
            path: str,
            request: Request,
            file: UploadFile = File(..., description="Binary payload"),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                data = await file.read()
                await self.service.write_bytes(user, path, data)
                return {
                    "path": absolute_virtual_path(path),
                    "file_name": file.filename,
                    "size": len(data),
                    "download_url": self._download_href(request, path),
                }
            except Exception as e:
                self._handle_exception(e, "Upload")

        @router.get("/fs/download/{path:path}", tags=["Filesystem"], summary="Download a binary file", operation_id="download_file")
        async def download(
            path: str,
            token: str | None = Query(None, description="Optional signed link token (see share_file)."),
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            # A signed link is short-lived: reject an expired or tampered token. Direct API
            # access without a token stays governed by the session + ReBAC below.
            if token is not None and not verify_download_token(token, normalize_virtual_path(path), user.uid):
                raise HTTPException(403, "Invalid or expired download token")
            try:
                data = await self.service.read_bytes(user, path)
                media_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
                return Response(content=data, media_type=media_type)
            except Exception as e:
                self._handle_exception(e, "Download")

        @router.get(
            "/fs/share/{path:path}",
            tags=["Filesystem"],
            summary="Get a signed download link for an existing file",
            operation_id="share_file",
            response_model=ShareFileResponse,
        )
        async def share_file(
            path: str,
            request: Request,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                info = await self.service.stat(user, path)
                if info.is_dir():
                    raise HTTPException(400, "Cannot share a directory")
                normalized = normalize_virtual_path(path)
                token = make_download_token(normalized, user.uid, ttl_seconds=DEFAULT_DOWNLOAD_TTL_SECONDS)
                href = self._download_href(request, path)
                separator = "&" if "?" in href else "?"
                return ShareFileResponse(
                    download_url=f"{href}{separator}token={token}",
                    file_name=normalized.rsplit("/", 1)[-1],
                    size=info.size,
                    mime=mimetypes.guess_type(path)[0],
                )
            except HTTPException:
                raise
            except Exception as e:
                self._handle_exception(e, "Share")

        @router.post("/fs/edit/{path:path}", tags=["Filesystem"], summary="Edit a file", operation_id="edit_file")
        async def edit(
            path: str,
            payload: EditFileRequest,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                return await self.service.edit_file(
                    user,
                    path,
                    old_string=payload.old_string,
                    new_string=payload.new_string,
                    replace_all=payload.replace_all,
                )
            except Exception as e:
                self._handle_exception(e, "Edit")

        @router.get("/fs/glob", tags=["Filesystem"], summary="Find files matching a glob", operation_id="glob")
        async def glob(pattern: str, path: str = "/", user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.glob(user, pattern, path)
            except Exception as e:
                self._handle_exception(e, "Glob")

        @router.get("/fs/grep", tags=["Filesystem"], summary="Search files by regex", operation_id="grep")
        async def grep(pattern: str, path: str = "/", user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.grep(user, pattern, path)
            except Exception as e:
                self._handle_exception(e, "Grep")

        @router.post("/fs/mkdir/{path:path}", tags=["Filesystem"], summary="Create a directory/folder", operation_id="mkdir")
        async def mkdir(path: str, user: KeycloakUser = Depends(get_current_user)):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                return await self.service.mkdir(user, path)
            except Exception as e:
                self._handle_exception(e, "Mkdir")
