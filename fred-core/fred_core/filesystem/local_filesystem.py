import re
from datetime import datetime
from pathlib import Path
from typing import List

import aiofiles

from fred_core import BaseFilesystem, StatResource, StatResult


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

    async def list(self, prefix: str = "") -> List[str]:
        """
        List all files under a given prefix recursively.

        Args:
            prefix (str): Directory path relative to root. Defaults to "" (root).

        Returns:
            List[str]: List of relative file paths.
        """
        root = self.root / prefix
        return [str(p.relative_to(self.root)) for p in root.rglob("*") if p.is_file()]

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

    # --- Unix-style utilities ---

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

    async def stat(self, path: str) -> StatResult:
        """
        Return file or folder metadata.

        Args:
            path (str): Path relative to root.

        Returns:
            dict: Metadata including:
                - size (int | None): File size in bytes.
                - type (str): "file" or "directory".
                - modified (datetime | None): Last modification time.
        """
        full = self.root / path
        st = full.stat()
        return StatResult(
            size=st.st_size,
            type=StatResource.FILE if full.is_file() else StatResource.DIRECTORY,
            modified=datetime.fromtimestamp(st.st_mtime)
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
        for path_str in await self.list(prefix):
            content = await self.cat(path_str)
            if regex.search(content):
                matches.append(path_str)
        return matches
