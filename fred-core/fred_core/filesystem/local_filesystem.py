import re
from datetime import datetime
from pathlib import Path
from typing import List

import aiofiles

from fred_core import (
    BaseFilesystem,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)


class LocalFilesystem(BaseFilesystem):
    """
    Async local filesystem implementation with Unix-style utilities.
    All operations are relative to a root directory.
    """

    def __init__(self, root: str):
        """
        Initialize the local filesystem.

        Args:
            root (str): Root directory path. Supports '~' expansion.
        """
        self.root = Path(root).expanduser().resolve()

    async def read(self, path: str) -> bytes:
        """
        Read a file from the local filesystem.

        Args:
            path (str): Relative path to file from root.

        Returns:
            bytes: File content.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        full = self.root / path
        async with aiofiles.open(full, "rb") as f:
            return await f.read()

    async def write(self, path: str, data: str | bytes) -> None:
        """
        Write data to a file, creating directories as needed.

        Args:
            path (str): Relative path to file from root.
            data (str | bytes): Data to write.
        """
        full = self.root / path
        full.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, str):
            data = data.encode("utf-8")
        async with aiofiles.open(full, "wb") as f:
            await f.write(data)

    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        base = self.root / prefix
        results: List[FilesystemResourceInfoResult] = []

        for p in base.rglob("*"):
            st = p.stat()
            typ = FilesystemResourceInfo.FILE if p.is_file() else FilesystemResourceInfo.DIRECTORY
            results.append(FilesystemResourceInfoResult(
                path=str(p.relative_to(self.root)),
                size=st.st_size if p.is_file() else None,
                type=typ,
                modified=datetime.fromtimestamp(st.st_mtime)
            ))

        # Add empty directories
        for d in base.rglob("*"):
            if d.is_dir() and not any(d.iterdir()):
                results.append(FilesystemResourceInfoResult(
                    path=str(d.relative_to(self.root)),
                    size=None,
                    type=FilesystemResourceInfo.DIRECTORY,
                    modified=datetime.fromtimestamp(d.stat().st_mtime)
                ))

        # Sort by path
        results.sort(key=lambda x: x.path)
        return results

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        regex = re.compile(pattern)
        matches = []
        for entry in await self.list(prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)
        return matches

    async def delete(self, path: str) -> None:
        """
        Delete a file.

        Args:
            path (str): Relative path to file from root.
        """
        full = self.root / path
        full.unlink(missing_ok=True)

    async def pwd(self) -> str:
        """
        Return the absolute path of the filesystem root.

        Returns:
            str: Absolute path to root directory.
        """
        return str(self.root)

    async def mkdir(self, path: str) -> None:
        """
        Create a directory relative to root.

        Args:
            path (str): Directory path relative to root.
        """
        full = self.root / path
        full.mkdir(parents=True, exist_ok=True)

    async def exists(self, path: str) -> bool:
        """
        Check if a file or folder exists.

        Args:
            path (str): Path relative to root.

        Returns:
            bool: True if path exists, False otherwise.
        """
        return (self.root / path).exists()

    async def cat(self, path: str) -> str:
        """
        Read a file and return its content as string.

        Args:
            path (str): Path relative to root.

        Returns:
            str: File content as UTF-8 string.
        """
        data = await self.read(path)
        return data.decode("utf-8")

    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        """
        Return metadata about a file or directory as a FilesystemResourceInfoResult.

        Args:
            path (str): Path relative to the filesystem root.

        Returns:
            FilesystemResourceInfoResult: Metadata about the file or directory.

        Raises:
            FileNotFoundError: If the file or directory does not exist.
        """
        full = self.root / path
        if not full.exists():
            raise FileNotFoundError(f"{path} not found")

        typ = FilesystemResourceInfo.FILE if full.is_file() else FilesystemResourceInfo.DIRECTORY
        size = full.stat().st_size if full.is_file() else None
        modified = datetime.fromtimestamp(full.stat().st_mtime)

        return FilesystemResourceInfoResult(
            path=str(full.relative_to(self.root)),
            size=size,
            type=typ,
            modified=modified
        )

    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        """
        Search for regex pattern in files under prefix.

        Args:
            pattern (str): Regular expression pattern.
            prefix (str): Path prefix relative to root. Defaults to root.

        Returns:
            List[str]: List of file paths (relative to root) that match the pattern.
        """
        regex = re.compile(pattern)
        matches = []
        for entry in await self.list(prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)
        return matches
