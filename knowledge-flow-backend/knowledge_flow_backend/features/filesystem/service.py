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
from typing import List

from fred_core import Action, FilesystemResourceInfoResult, KeycloakUser, Resource, authorize

from knowledge_flow_backend.application_context import ApplicationContext

logger = logging.getLogger(__name__)


class FilesystemService:
    """
    Business-facing service for asynchronous filesystem operations.

    Each user has an isolated filesystem namespace:
        <root>/<user_id>
    where <root> comes from the filesystem backend configuration:
        - Local: ~/.fred/knowledge-flow/filesystem/
        - MinIO: bucket "filesystem"
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.fs = context.get_filesystem()

    #
    # User-scoping logic
    #

    def _user_root(self, user: KeycloakUser) -> str:
        """
        Returns the root directory for the user.
        Example: <root>/<user_id>
        """
        return user.uid

    def _resolve(self, user: KeycloakUser, path: str) -> str:
        """
        Builds the full path inside the user's namespace.
        """
        path = path.lstrip("/")
        if path:
            return f"{self._user_root(user)}/{path}"
        return self._user_root(user)

    #
    # Operations
    #

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def list(self, user: KeycloakUser, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        try:
            full_prefix = self._resolve(user, prefix)
            return await self.fs.list(full_prefix)
        except Exception as e:
            logger.exception("Failed to list filesystem entries")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def stat(self, user: KeycloakUser, path: str) -> FilesystemResourceInfoResult:
        try:
            full_path = self._resolve(user, path)
            return await self.fs.stat(full_path)
        except Exception as e:
            logger.exception(f"Failed to stat {path}")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def cat(self, user: KeycloakUser, path: str) -> str:
        try:
            full_path = self._resolve(user, path)
            return await self.fs.cat(full_path)
        except Exception as e:
            logger.exception(f"Failed to read {path}")
            raise e

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def write(self, user: KeycloakUser, path: str, data: str) -> None:
        try:
            full_path = self._resolve(user, path)
            await self.fs.write(full_path, data)
        except Exception as e:
            logger.exception(f"Failed to write {path}")
            raise e

    @authorize(action=Action.DELETE, resource=Resource.FILES)
    async def delete(self, user: KeycloakUser, path: str) -> None:
        try:
            full_path = self._resolve(user, path)
            await self.fs.delete(full_path)
        except Exception as e:
            logger.exception(f"Failed to delete {path}")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def grep(self, user: KeycloakUser, pattern: str, prefix: str = "") -> List[str]:
        try:
            full_prefix = self._resolve(user, prefix)
            return await self.fs.grep(pattern, full_prefix)
        except Exception as e:
            logger.exception(f"Grep failed for pattern '{pattern}' with prefix '{prefix}'")
            raise e

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def pwd(self, user: KeycloakUser) -> str:
        """
        Returns the user's root relative to the filesystem backend.
        """
        try:
            return self._user_root(user)
        except Exception as e:
            logger.exception("Failed to get user FS root")
            raise e

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def mkdir(self, user: KeycloakUser, path: str) -> None:
        """
        Create a directory inside the user's namespace.
        """
        try:
            full_path = self._resolve(user, path)
            await self.fs.mkdir(full_path)
        except Exception as e:
            logger.exception(f"Failed to create directory {path}")
            raise e
