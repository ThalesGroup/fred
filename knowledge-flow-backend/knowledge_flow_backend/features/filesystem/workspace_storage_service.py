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

"""
User storage service: minimal, production-ready wrapper around ``UserStorage``.

Purpose
-------
- Offer a **single, private namespace per user** under ``users/<uid>/``.
- Keep the filesystem backend generic (local or MinIO) while exposing simple
  CRUD helpers for HTTP controllers and agents.

Example
-------
>>> svc = UserStorageService()
>>> await svc.put_file(user, "reports/summary.txt", b"hello", content_type="text/plain")
>>> files = await svc.list_files(user)
>>> blob = await svc.read_file(user, "reports/summary.txt")
>>> await svc.delete_file(user, "reports/summary.txt")
"""

from __future__ import annotations

import mimetypes

from fastapi import UploadFile
from fred_core import KeycloakUser

from knowledge_flow_backend.application_context import get_app_context
from knowledge_flow_backend.features.filesystem.mcp_fs_service import McpFilesystemService
from knowledge_flow_backend.features.filesystem.workspace_filesystem import WorkspaceFilesystem


class WorkspaceStorageService:
    """Thin service that routes scoped file operations to ``UserStorage``."""

    def __init__(self, *, namespace: str = "users") -> None:
        fs_service = McpFilesystemService()
        # Default namespace retained for user scope; root_prefix can override per call.
        self.storage: WorkspaceFilesystem = WorkspaceFilesystem(fs_service.fs, prefix=namespace)
        self.namespace = namespace
        self.layout = get_app_context().configuration.workspace_layout

    def _fmt(self, pattern: str, **kwargs) -> str:
        try:
            return pattern.format(**kwargs)
        except KeyError as e:
            raise ValueError(f"Missing placeholder in pattern: {e}") from e

    @staticmethod
    def _split_root_owner_key(resolved: str) -> tuple[str, str, str]:
        """
        Split a resolved path (e.g., 'agents/aid/config/file.txt') into (root, owner, remainder).
        Assumes pattern is root/owner/..., as enforced by WorkspaceLayoutConfig.
        """
        parts = resolved.split("/", 2)
        if len(parts) < 2:
            raise ValueError(f"Resolved path must contain at least root/owner: {resolved}")
        root = parts[0]
        owner = parts[1]
        remainder = parts[2] if len(parts) > 2 else ""
        return root, owner, remainder

    # internal generic helpers
    async def _put_file(self, user: KeycloakUser, root_prefix: str, owner_id: str, scoped_key: str, file: UploadFile):
        data = await file.read()
        await self.storage.put(user, scoped_key, data, owner_override=owner_id, root_prefix=root_prefix)
        return await self.storage.stat(user, scoped_key, owner_override=owner_id, root_prefix=root_prefix)

    async def _read_file(self, user: KeycloakUser, root_prefix: str, owner_id: str, scoped_key: str) -> bytes:
        return await self.storage.get_bytes(user, scoped_key, owner_override=owner_id, root_prefix=root_prefix)

    async def _delete_file(self, user: KeycloakUser, root_prefix: str, owner_id: str, scoped_key: str) -> None:
        await self.storage.delete(user, scoped_key, owner_override=owner_id, root_prefix=root_prefix)

    async def _list_files(self, user: KeycloakUser, root_prefix: str, owner_id: str, scoped_prefix: str):
        return await self.storage.list(user, scoped_prefix, owner_override=owner_id, root_prefix=root_prefix)

    # user scope
    async def put_user_file(self, user: KeycloakUser, key: str, file: UploadFile):
        resolved = self._fmt(self.layout.user_pattern, user_id=user.uid, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._put_file(user, root, owner, scoped, file)

    async def list_user_files(self, user: KeycloakUser, prefix: str = ""):
        resolved = self._fmt(self.layout.user_pattern, user_id=user.uid, key=prefix)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._list_files(user, root, owner, scoped)

    async def read_user_file(self, user: KeycloakUser, key: str) -> bytes:
        resolved = self._fmt(self.layout.user_pattern, user_id=user.uid, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._read_file(user, root, owner, scoped)

    async def delete_user_file(self, user: KeycloakUser, key: str) -> None:
        resolved = self._fmt(self.layout.user_pattern, user_id=user.uid, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        await self._delete_file(user, root, owner, scoped)

    # agent config scope
    async def put_agent_config_file(self, user: KeycloakUser, agent_id: str, key: str, file: UploadFile):
        resolved = self._fmt(self.layout.agent_config_pattern, agent_id=agent_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._put_file(user, root, owner, scoped, file)

    async def list_agent_config_files(self, user: KeycloakUser, agent_id: str, prefix: str = ""):
        resolved = self._fmt(self.layout.agent_config_pattern, agent_id=agent_id, key=prefix)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._list_files(user, root, owner, scoped)

    async def read_agent_config_file(self, user: KeycloakUser, agent_id: str, key: str) -> bytes:
        resolved = self._fmt(self.layout.agent_config_pattern, agent_id=agent_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._read_file(user, root, owner, scoped)

    async def delete_agent_config_file(self, user: KeycloakUser, agent_id: str, key: str) -> None:
        resolved = self._fmt(self.layout.agent_config_pattern, agent_id=agent_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        await self._delete_file(user, root, owner, scoped)

    # agent-user scope
    async def put_agent_user_file(self, user: KeycloakUser, agent_id: str, target_user_id: str, key: str, file: UploadFile):
        resolved = self._fmt(self.layout.agent_user_pattern, agent_id=agent_id, user_id=target_user_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._put_file(user, root, owner, scoped, file)

    async def list_agent_user_files(self, user: KeycloakUser, agent_id: str, target_user_id: str, prefix: str = ""):
        resolved = self._fmt(self.layout.agent_user_pattern, agent_id=agent_id, user_id=target_user_id, key=prefix)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._list_files(user, root, owner, scoped)

    async def read_agent_user_file(self, user: KeycloakUser, agent_id: str, target_user_id: str, key: str) -> bytes:
        resolved = self._fmt(self.layout.agent_user_pattern, agent_id=agent_id, user_id=target_user_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        return await self._read_file(user, root, owner, scoped)

    async def delete_agent_user_file(self, user: KeycloakUser, agent_id: str, target_user_id: str, key: str) -> None:
        resolved = self._fmt(self.layout.agent_user_pattern, agent_id=agent_id, user_id=target_user_id, key=key)
        root, owner, scoped = self._split_root_owner_key(resolved)
        await self._delete_file(user, root, owner, scoped)

    @staticmethod
    def guess_content_type(key: str) -> str:
        return mimetypes.guess_type(key)[0] or "application/octet-stream"
