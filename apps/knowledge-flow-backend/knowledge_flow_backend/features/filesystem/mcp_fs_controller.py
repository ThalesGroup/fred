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

from fastapi import APIRouter, Body, Depends, HTTPException
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user
from pydantic import BaseModel

from knowledge_flow_backend.features.filesystem.mcp_fs_service import McpFilesystemService

logger = logging.getLogger(__name__)


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

    # ----------- Helper for consistent error handling -----------

    def _handle_exception(self, e: Exception, context: str):
        if isinstance(e, PermissionError):
            raise HTTPException(400, str(e))
        if isinstance(e, FileNotFoundError):
            raise HTTPException(404, "Path not found")
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
            offset: int = 0,
            limit: int = 100,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.read_file(user, path, offset=offset, limit=limit)
            except Exception as e:
                self._handle_exception(e, "Cat")

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
