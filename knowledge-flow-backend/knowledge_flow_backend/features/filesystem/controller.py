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
                logger.exception("List failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Stat failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Cat failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Write failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Delete failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Grep failed")
                raise HTTPException(500, str(e))

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
                logger.exception("Pwd failed")
                raise HTTPException(500, str(e))
