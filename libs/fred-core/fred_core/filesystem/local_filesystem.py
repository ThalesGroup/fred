import logging
import re
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
        if not str(final_path).startswith(str(self.root)):
            raise PermissionError(
                f"Access outside of filesystem root is forbidden: '{path}'"
            )
        return final_path

    async def read(self, path: str) -> bytes:
        """
        Read the contents of a file as raw bytes.

        Args:
            path (str): Path of the file to read.

        Returns:
            bytes: File content.
        """
        full = self._resolve_path(path)
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
        full = self._resolve_path(path)

        if not full.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: '{full.parent}'")

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
        base = self._resolve_path(prefix)
        results: List[FilesystemResourceInfoResult] = []

        if not base.exists() or not base.is_dir():
            return results

        for p in base.rglob("*"):
            try:
                p = p.resolve()
                if not str(p).startswith(str(self.root)):
                    continue
            except Exception:
                logger.warning("Failed to resolve path during listing: %s", p)
                continue

            st = p.stat()
            typ = (
                FilesystemResourceInfo.FILE
                if p.is_file()
                else FilesystemResourceInfo.DIRECTORY
            )

            results.append(
                FilesystemResourceInfoResult(
                    path=str(p.relative_to(self.root)),
                    size=st.st_size if p.is_file() else None,
                    type=typ,
                    modified=datetime.fromtimestamp(st.st_mtime),
                )
            )

        results.sort(key=lambda x: x.path)
        return results

    async def delete(self, path: str) -> None:
        """
        Delete a file or directory.

        Args:
            path (str): Path to delete.
        """
        full = self._resolve_path(path)
        full.unlink(missing_ok=True)

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
        full = self._resolve_path(path)
        full.mkdir(parents=True, exist_ok=True)

    async def exists(self, path: str) -> bool:
        """
        Check if a file or directory exists.

        Args:
            path (str): Path to check.

        Returns:
            bool: True if the path exists, False otherwise.
        """
        return self._resolve_path(path).exists()

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
        full = self._resolve_path(path)

        if not full.exists():
            raise FileNotFoundError(f"{path} not found")

        typ = (
            FilesystemResourceInfo.FILE
            if full.is_file()
            else FilesystemResourceInfo.DIRECTORY
        )
        size = full.stat().st_size if full.is_file() else None
        modified = datetime.fromtimestamp(full.stat().st_mtime)

        return FilesystemResourceInfoResult(
            path=str(full.relative_to(self.root)),
            size=size,
            type=typ,
            modified=modified,
        )

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
