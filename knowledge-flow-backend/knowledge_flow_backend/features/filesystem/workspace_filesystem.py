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
Lightweight namespacing facade over the configured Filesystem (local or MinIO).

We normalize keys and inject a `root/owner/key` shape:
- `root` defaults to "users" but can be overridden (e.g., "agents").
- `owner` defaults to user.uid but can be overridden (e.g., agent_id).
- `key` is the sanitized relative path (no leading slash, no '..').

Parent prefixes are created on demand; controllers/ services decide which
root/owner to use (user exchange, agent config, agent-user notes).
"""

from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import List, Optional

from minio.error import S3Error

from fred_core import KeycloakUser
from fred_core.filesystem.structures import BaseFilesystem, FilesystemResourceInfoResult


def _normalize_key(key: str) -> str:
    """Sanitize a user-supplied key (no absolute path, no parent escapes)."""
    k = (key or "").strip()
    k = k.replace("\\", "/")  # normalize separators
    k = k.lstrip("/")
    if not k:
        raise ValueError("Key cannot be empty")
    if ".." in k.split("/"):
        raise ValueError("Key cannot contain parent path segments")
    return k


def _join(*parts: str) -> str:
    return posixpath.join(*parts)


@dataclass(frozen=True)
class UserFile:
    """Lightweight file descriptor used by list/stat operations."""

    path: str
    size: Optional[int]
    type: str
    modified: Optional[str]


class WorkspaceFilesystem:
    """User-scoped storage facade over ``BaseFilesystem``.

    Keep this thin: it only injects the user namespace and path hygiene, then
    delegates to the underlying filesystem implementation.
    """

    def __init__(self, fs: BaseFilesystem, prefix: str = "users"):
        self.fs = fs
        self.prefix = prefix.rstrip("/")

    def _path(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> str:
        """
        Build a safe path inside the configured prefix.

        owner_override: when provided, use this identifier instead of user.uid.
        Useful for agent-scoped storage that still authenticates as a user/admin.
        """
        safe_key = _normalize_key(key)
        owner = (owner_override or user.uid).strip("/")
        root = (root_prefix or self.prefix).rstrip("/")
        return _join(root, owner, safe_key)

    async def put(
        self,
        user: KeycloakUser,
        key: str,
        data: bytes | str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> str:
        """Write bytes/str at ``users/<uid>/<key>``. Creates parent dirs if needed."""
        path = self._path(user, key, owner_override, root_prefix)
        parent = posixpath.dirname(path)
        if parent and parent != path:
            # MinIO write fails if parent prefix doesn't exist
            exists = await self.fs.exists(parent)
            if not exists:
                await self.fs.mkdir(parent)
        await self.fs.write(path, data)
        return path

    async def get_bytes(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> bytes:
        path = self._path(user, key, owner_override, root_prefix)
        try:
            return await self.fs.read(path)
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(path) from e
            raise

    async def get_text(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> str:
        path = self._path(user, key, owner_override, root_prefix)
        try:
            return await self.fs.cat(path)
        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(path) from e
            raise

    async def delete(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> None:
        path = self._path(user, key, owner_override, root_prefix)
        await self.fs.delete(path)

    async def stat(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> FilesystemResourceInfoResult:
        path = self._path(user, key, owner_override, root_prefix)
        return await self.fs.stat(path)

    async def list(
        self,
        user: KeycloakUser,
        prefix: str = "",
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> List[FilesystemResourceInfoResult]:
        # Allow optional sub-prefix inside the user's namespace
        sub = _normalize_key(prefix) if prefix else ""
        owner = (owner_override or user.uid).strip("/")
        root = (root_prefix or self.prefix).rstrip("/")
        full_prefix = _join(root, owner, sub)
        return await self.fs.list(full_prefix)

    async def exists(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> bool:
        path = self._path(user, key, owner_override, root_prefix)
        return await self.fs.exists(path)

    # Placeholder for future public URL generation (HTTP controller layer)
    def url_for(self, key: str) -> str:
        raise NotImplementedError("UserStorage.url_for is provided by the HTTP layer")
