# Copyright Thales 2025
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
from fastapi import APIRouter, Depends, HTTPException, Path, Body
from fred_core import Action, KeycloakUser, Resource, authorize_or_raise, get_current_user

from knowledge_flow_backend.features.filesystem.service import FilesystemService

logger = logging.getLogger(__name__)


class FilesystemController:
    """
    Controller exposing filesystem operations via API.
    Works directly with the selected backend (local or MinIO).
    """

    def __init__(self, router: APIRouter):
        self.service = FilesystemService()
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

        @router.get(
            "/fs/list",
            tags=["Filesystem"],
            summary="List files and directories in the root"
        )
        async def list_entries(
            prefix: str = "",
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.list(user, prefix)
            except Exception as e:
                self._handle_exception(e, "List")

        @router.get(
            "/fs/stat/{path:path}",
            tags=["Filesystem"],
            summary="Get file information"
        )
        async def stat(
            path: str,
            user: KeycloakUser = Depends(get_current_user),
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.stat(user, path)
            except Exception as e:
                self._handle_exception(e, "Stat")

        @router.get(
            "/fs/cat/{path:path}",
            tags=["Filesystem"],
            summary="Read a file"
        )
        async def cat(
            path: str,
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.cat(user, path)
            except Exception as e:
                self._handle_exception(e, "Cat")

        @router.post(
            "/fs/write/{path:path}",
            tags=["Filesystem"],
            summary="Write a file"
        )
        async def write(
            path: str,
            data: str = Body(..., embed=True),
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                return await self.service.write(user, path, data)
            except Exception as e:
                self._handle_exception(e, "Write")

        @router.delete(
            "/fs/delete/{path:path}",
            tags=["Filesystem"],
            summary="Delete a file"
        )
        async def delete(
            path: str,
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.DELETE, Resource.FILES)
            try:
                return await self.service.delete(user, path)
            except Exception as e:
                self._handle_exception(e, "Delete")

        @router.get(
            "/fs/grep",
            tags=["Filesystem"],
            summary="Search files by regex"
        )
        async def grep(
            pattern: str,
            prefix: str = "",
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.grep(user, pattern, prefix)
            except Exception as e:
                self._handle_exception(e, "Grep")

        @router.get(
            "/fs/pwd",
            tags=["Filesystem"],
            summary="Get root path of the filesystem"
        )
        async def pwd(
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.READ, Resource.FILES)
            try:
                return await self.service.pwd(user)
            except Exception as e:
                self._handle_exception(e, "Pwd")

        @router.post(
            "/fs/mkdir/{path:path}",
            tags=["Filesystem"],
            summary="Create a directory/folder"
        )
        async def mkdir(
            path: str,
            user: KeycloakUser = Depends(get_current_user)
        ):
            authorize_or_raise(user, Action.CREATE, Resource.FILES)
            try:
                return await self.service.mkdir(user, path)
            except Exception as e:
                self._handle_exception(e, "Mkdir")
