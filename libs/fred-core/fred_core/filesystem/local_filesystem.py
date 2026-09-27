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

import asyncio
import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import List

import aiofiles
from fred_core.filesystem.structures import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)

logger = logging.getLogger(__name__)


class LocalFilesystem(BaseFilesystem):
    """
    Async local filesystem implementation with strict sandboxing.
    All operations are restricted to a root directory and prevent path traversal.
    """

    def __init__(self, root: str):
        """
        Initialize the filesystem with a given root directory.

        Args:
            root (str): Path to the root directory for this filesystem.
        """
        self.root = Path(root).expanduser().resolve()

    def _resolve_path(self, path: str) -> Path:
        """
        Resolve a path securely relative to the root, preventing traversal outside the root.

        Args:
            path (str): User-provided path.

        Returns:
            Path: Absolute resolved path within the root.

        Raises:
            PermissionError: If the resolved path escapes the root directory.
        """
        final_path = (self.root / path).resolve()
        if not final_path.is_relative_to(self.root):
            raise PermissionError(
                f"Access outside of filesystem root is forbidden: '{path}'"
            )
        return final_path

    def _resolve_writable_path(self, path: str) -> Path:
        full = self._resolve_path(path)
        if not full.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: '{full.parent}'")
        return full

    def _list_sync(self, prefix: str) -> List[FilesystemResourceInfoResult]:
        base = self._resolve_path(prefix)
        results: List[FilesystemResourceInfoResult] = []

        if not base.exists() or not base.is_dir():
            return results

        for candidate in base.rglob("*"):
            try:
                path = candidate.resolve()
                if not path.is_relative_to(self.root):
                    continue
            except Exception:
                logger.warning("Failed to resolve path during listing: %s", candidate)
                continue

            is_file = path.is_file()
            stat = path.stat()
            results.append(
                FilesystemResourceInfoResult(
                    path=str(path.relative_to(self.root)),
                    size=stat.st_size if is_file else None,
                    type=(
                        FilesystemResourceInfo.FILE
                        if is_file
                        else FilesystemResourceInfo.DIRECTORY
                    ),
                    modified=datetime.fromtimestamp(stat.st_mtime),
                )
            )

        results.sort(key=lambda result: result.path)
        return results

    def _delete_sync(self, path: str) -> None:
        full = self._resolve_path(path)
        if full == self.root:
            raise ValueError("Deleting the filesystem root is forbidden")
        if full.is_dir():
            shutil.rmtree(full)
        else:
            full.unlink(missing_ok=True)

    def _stat_sync(self, path: str) -> FilesystemResourceInfoResult:
        full = self._resolve_path(path)
        if not full.exists():
            raise FileNotFoundError(f"{path} not found")

        is_file = full.is_file()
        stat = full.stat()
        return FilesystemResourceInfoResult(
            path=str(full.relative_to(self.root)),
            size=stat.st_size if is_file else None,
            type=(
                FilesystemResourceInfo.FILE
                if is_file
                else FilesystemResourceInfo.DIRECTORY
            ),
            modified=datetime.fromtimestamp(stat.st_mtime),
        )

    async def read(self, path: str) -> bytes:
        """
        Read the contents of a file as raw bytes.

        Args:
            path (str): Path of the file to read.

        Returns:
            bytes: File content.
        """
        full = await asyncio.to_thread(self._resolve_path, path)
        async with aiofiles.open(full, "rb") as f:
            return await f.read()

    async def write(self, path: str, data: str | bytes) -> None:
        """
        Write data to a file. Accepts bytes or string (UTF-8).

        Args:
            path (str): Target file path.
            data (str | bytes): Content to write.

        Raises:
            FileNotFoundError: If the parent directory does not exist.
        """
        full = await asyncio.to_thread(self._resolve_writable_path, path)

        if isinstance(data, str):
            data = data.encode("utf-8")

        async with aiofiles.open(full, "wb") as f:
            await f.write(data)

    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        """
        List files and directories under a given prefix.

        Args:
            prefix (str): Directory prefix to list (relative to root).

        Returns:
            List[FilesystemResourceInfoResult]: List of files and directories with metadata.
        """
        return await asyncio.to_thread(self._list_sync, prefix)

    async def delete(self, path: str) -> None:
        """
        Delete a file or directory.

        Args:
            path (str): Path to delete.
        """
        await asyncio.to_thread(self._delete_sync, path)

    async def print_root_dir(self) -> str:
        """
        Return the root directory of the filesystem.

        Returns:
            str: Absolute path of the root directory.
        """
        return str(self.root)

    async def mkdir(self, path: str) -> None:
        """
        Create a directory and all necessary parent directories.

        Args:
            path (str): Directory path to create.
        """
        full = await asyncio.to_thread(self._resolve_path, path)
        await asyncio.to_thread(full.mkdir, parents=True, exist_ok=True)

    async def exists(self, path: str) -> bool:
        """
        Check if a file or directory exists.

        Args:
            path (str): Path to check.

        Returns:
            bool: True if the path exists, False otherwise.
        """
        full = await asyncio.to_thread(self._resolve_path, path)
        return await asyncio.to_thread(full.exists)

    async def cat(self, path: str) -> str:
        """
        Read a file and return its content as a UTF-8 string.

        Args:
            path (str): Path of the file.

        Returns:
            str: File content decoded as UTF-8.
        """
        data = await self.read(path)
        return data.decode("utf-8")

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        """
        Return metadata about a file or directory.

        Args:
            path (str): Path to file or directory.

        Returns:
            FilesystemResourceInfoResult: Metadata including type, size, and modification time.

        Raises:
            FileNotFoundError: If the path does not exist.
        """
        return await asyncio.to_thread(self._stat_sync, path)

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """
        Search for a regex pattern in all files under a given prefix.

        Args:
            pattern (str): Regular expression to search for.
            prefix (str): Directory prefix to search in (relative to root).

        Returns:
            List[str]: Paths of files containing the pattern.
        """
        regex = re.compile(pattern)
        matches = []

        for entry in await self.list(prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)

        return matches
