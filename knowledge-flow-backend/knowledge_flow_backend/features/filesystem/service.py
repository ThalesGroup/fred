import logging
from typing import List
from knowledge_flow_backend.application_context import ApplicationContext

from fred_core import Action, KeycloakUser, Resource, authorize

from fred_core import FilesystemResourceInfoResult

logger = logging.getLogger(__name__)


class FilesystemService:
    """
    Business-facing service for asynchronous filesystem operations.

    This service acts as a unified interface to different filesystem backends
    (e.g., local filesystem, Minio/S3). It provides high-level methods for
    listing, reading, writing, deleting files, searching with regex, and
    retrieving filesystem metadata. 

    All methods are decorated with authorization checks to enforce user
    permissions based on the `KeycloakUser` and the corresponding `Action`
    on the `Resource.FILES`.

    Attributes:
        fs (BaseFilesystem): The underlying filesystem backend obtained from
            the ApplicationContext. This can be a local or cloud-based filesystem.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.fs = context.get_filesystem()

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def list(self, user: KeycloakUser, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        try:
            return await self.fs.list(prefix)
        except Exception as e:
            logger.exception("Failed to list filesystem entries")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def stat(self, user: KeycloakUser, path: str) -> FilesystemResourceInfoResult:
        try:
            return await self.fs.stat(path)
        except Exception as e:
            logger.exception(f"Failed to stat {path}")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def cat(self, user: KeycloakUser, path: str) -> str:
        try:
            return await self.fs.cat(path)
        except Exception as e:
            logger.exception(f"Failed to read {path}")
            raise e

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def write(self, user: KeycloakUser, path: str, data: str) -> None:
        try:
            await self.fs.write(path, data)
        except Exception as e:
            logger.exception(f"Failed to write {path}")
            raise e

    @authorize(action=Action.DELETE, resource=Resource.FILES)
    async def delete(self, user: KeycloakUser, path: str) -> None:
        try:
            await self.fs.delete(path)
        except Exception as e:
            logger.exception(f"Failed to delete {path}")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def grep(self, user: KeycloakUser, pattern: str, prefix: str = "") -> List[str]:
        try:
            return await self.fs.grep(pattern, prefix)
        except Exception as e:
            logger.exception(f"Grep failed for pattern '{pattern}' with prefix '{prefix}'")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def pwd(self, user: KeycloakUser) -> str:
        try:
            return await self.fs.pwd()
        except Exception as e:
            logger.exception("Failed to get FS root")
            raise e