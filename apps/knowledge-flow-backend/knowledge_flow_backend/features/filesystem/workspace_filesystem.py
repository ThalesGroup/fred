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

from fred_core import KeycloakUser
from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from minio.error import S3Error


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


def _direct_child_entry(
    res: FilesystemResourceInfoResult,
    *,
    relative_path: str,
) -> FilesystemResourceInfoResult:
    """
    Collapse one recursive filesystem hit into the direct child visible from a folder.

    Why this exists:
    - the underlying filesystem `list(...)` returns recursive descendants
    - the MCP-facing workspace view should behave like a normal `ls`, which only shows
      direct children of the requested directory

    How to use:
    - pass one result already stripped to the namespace-relative path
    - use the returned entry in `WorkspaceFilesystem.list(...)`

    Example:
    - a recursive hit on `reports/2026/summary.md` becomes the direct directory entry
      `reports`
    """
    direct_name = relative_path.split("/", 1)[0]
    is_direct_child = "/" not in relative_path
    return FilesystemResourceInfoResult(
        path=direct_name,
        size=res.size if is_direct_child else None,
        type=res.type if is_direct_child else FilesystemResourceInfo.DIRECTORY,
        modified=res.modified if is_direct_child else None,
    )


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
        """
        List the direct children of one scoped workspace folder.

        Why this exists:
        - agents and MCP clients expect `list(...)` to behave like a standard directory
          listing, not like a recursive tree dump
        - this adapter keeps the lower filesystem backend unchanged while exposing the
          simpler contract at the workspace boundary

        How to use:
        - pass an optional folder prefix inside the scoped namespace
        - the result contains only direct files and directories visible from that folder

        Example:
        - `list(user, "reports")` returns `summary.md` and `archive`, not
          `archive/2025/q1.md`
        """
        # Allow optional sub-prefix inside the user's namespace
        sub = _normalize_key(prefix) if prefix else ""
        owner = (owner_override or user.uid).strip("/")
        root = (root_prefix or self.prefix).rstrip("/")
        full_prefix = _join(root, owner, sub)

        # Determine the namespace root to strip from results.
        # When a sub-prefix is given (e.g. "config"), strip from that directory
        # so that direct children are returned relative to the requested folder,
        # not relative to the owner root.  Without this, every file inside
        # "config/" would appear as a single "config" directory entry.
        namespace_root = _join(root, owner, sub) if sub else _join(root, owner)
        if not namespace_root.endswith("/"):
            namespace_root += "/"

        results = await self.fs.list(full_prefix)
        direct_children: dict[str, FilesystemResourceInfoResult] = {}
        for res in results:
            if res.path.startswith(namespace_root):
                relative_path = res.path[len(namespace_root) :]
                if not relative_path:
                    continue
                child = _direct_child_entry(res, relative_path=relative_path)
                existing = direct_children.get(child.path)
                if existing is None or child.is_dir():
                    direct_children[child.path] = child
        return [direct_children[name] for name in sorted(direct_children)]

    async def rename(
        self,
        user: KeycloakUser,
        old_key: str,
        new_key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> None:
        """
        Rename a file or folder in place (same parent), preserving all descendants.

        Why this exists:
        - `BaseFilesystem` has no native move primitive across local/MinIO/GCS, and
          adding one to the protocol plus all three backends is a bigger change than a
          single workspace rename needs
        - implemented generically on top of the existing read/write/delete/list
          primitives, so it works uniformly on every backend with no backend-specific
          code

        How to use:
        - pass the old and new keys relative to the scoped namespace; both must share
          the same parent directory (this is a rename, not an arbitrary cross-folder
          move)
        """
        old_path = self._path(user, old_key, owner_override, root_prefix)
        new_path = self._path(user, new_key, owner_override, root_prefix)
        if await self.fs.exists(new_path):
            raise ValueError(f"A file or folder already exists at {new_key!r}")

        if await self.fs.exists(old_path):
            data = await self.fs.read(old_path)
            await self.fs.write(new_path, data)
            await self.fs.delete(old_path)
            return

        prefix = old_path if old_path.endswith("/") else f"{old_path}/"
        descendants = [entry for entry in await self.fs.list(old_path) if entry.path.startswith(prefix) and entry.is_file()]
        if not descendants:
            raise FileNotFoundError(old_key)
        for entry in descendants:
            relative = entry.path[len(prefix) :]
            data = await self.fs.read(entry.path)
            await self.fs.write(f"{new_path}/{relative}", data)
            await self.fs.delete(entry.path)

    async def list_recursive_files(
        self,
        user: KeycloakUser,
        prefix: str = "",
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> List[FilesystemResourceInfoResult]:
        """
        List every file (not directories) under one scoped workspace folder, recursively.

        Why this exists:
        - usage-stats cards (FRONT-09.I) need every file's size and type, not just the
          direct-children view `list(...)` exposes
        - `self.fs.list(...)` already walks recursively under the hood; this skips the
          direct-child collapsing `list(...)` does, instead of re-walking storage

        How to use:
        - pass an optional folder prefix inside the scoped namespace
        """
        sub = _normalize_key(prefix) if prefix else ""
        owner = (owner_override or user.uid).strip("/")
        root = (root_prefix or self.prefix).rstrip("/")
        full_prefix = _join(root, owner, sub)
        results = await self.fs.list(full_prefix)
        return [res for res in results if res.is_file()]

    async def exists(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> bool:
        path = self._path(user, key, owner_override, root_prefix)
        return await self.fs.exists(path)

    async def mkdir(
        self,
        user: KeycloakUser,
        key: str,
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> None:
        path = self._path(user, key, owner_override, root_prefix)
        await self.fs.mkdir(path)

    async def grep(
        self,
        user: KeycloakUser,
        pattern: str,
        prefix: str = "",
        owner_override: str | None = None,
        root_prefix: str | None = None,
    ) -> List[str]:
        # Reuse list logic to resolve the prefix path correctly
        sub = _normalize_key(prefix) if prefix else ""
        owner = (owner_override or user.uid).strip("/")
        root = (root_prefix or self.prefix).rstrip("/")
        full_prefix = _join(root, owner, sub)

        namespace_root = _join(root, owner)
        if not namespace_root.endswith("/"):
            namespace_root += "/"

        results = await self.fs.grep(pattern, full_prefix)
        return [p[len(namespace_root) :] for p in results if p.startswith(namespace_root) and p[len(namespace_root) :]]

    # Placeholder for future public URL generation (HTTP controller layer)
    def url_for(self, key: str) -> str:
        raise NotImplementedError("UserStorage.url_for is provided by the HTTP layer")
