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


class LocalFilesystem(BaseFilesystem):
    """
    Async local filesystem implementation with strict sandboxing.
    All operations are restricted to a root directory and disallow path traversal.
    """

    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()

    # ---------------------------------------------------------
    # SECURITY: centralised safe path resolver
    # ---------------------------------------------------------
    def _resolve_path(self, path: str) -> Path:
        """
        Resolve path securely relative to root, preventing path traversal.
        """
        # Normalize and resolve absolute path
        final_path = (self.root / path).resolve()

        # SECURITY CHECK: final path must remain inside root
        if not str(final_path).startswith(str(self.root)):
            raise PermissionError(f"Access outside of filesystem root is forbidden: '{path}'")

        return final_path

    # ---------------------------------------------------------
    # READ
    # ---------------------------------------------------------
    async def read(self, path: str) -> bytes:
        full = self._resolve_path(path)
        async with aiofiles.open(full, "rb") as f:
            return await f.read()

    # ---------------------------------------------------------
    # WRITE
    # ---------------------------------------------------------
    async def write(self, path: str, data: str | bytes) -> None:
        full = self._resolve_path(path)

        if not full.parent.exists():
            raise FileNotFoundError(f"Parent directory does not exist: '{full.parent}'")

        if isinstance(data, str):
            data = data.encode("utf-8")

        async with aiofiles.open(full, "wb") as f:
            await f.write(data)

    # ---------------------------------------------------------
    # LIST
    # ---------------------------------------------------------
    async def list(self, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        base = self._resolve_path(prefix)
        results: List[FilesystemResourceInfoResult] = []

        if not base.exists() or not base.is_dir():
            return results

        for p in base.rglob("*"):
            # SECURITY: forbid listing anything outside the root (symlinks)
            try:
                p = p.resolve()
                if not str(p).startswith(str(self.root)):
                    continue  # ignore external symlink escapes
            except Exception:
                continue

            st = p.stat()
            typ = FilesystemResourceInfo.FILE if p.is_file() else FilesystemResourceInfo.DIRECTORY

            results.append(
                FilesystemResourceInfoResult(
                    path=str(p.relative_to(self.root)),
                    size=st.st_size if p.is_file() else None,
                    type=typ,
                    modified=datetime.fromtimestamp(st.st_mtime),
                )
            )

        # Sort results
        results.sort(key=lambda x: x.path)
        return results

    # ---------------------------------------------------------
    # DELETE
    # ---------------------------------------------------------
    async def delete(self, path: str) -> None:
        full = self._resolve_path(path)
        full.unlink(missing_ok=True)

    # ---------------------------------------------------------
    # PWD
    # ---------------------------------------------------------
    async def pwd(self) -> str:
        return str(self.root)

    # ---------------------------------------------------------
    # MKDIR
    # ---------------------------------------------------------
    async def mkdir(self, path: str) -> None:
        full = self._resolve_path(path)
        full.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------
    # EXISTS
    # ---------------------------------------------------------
    async def exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    # ---------------------------------------------------------
    # CAT
    # ---------------------------------------------------------
    async def cat(self, path: str) -> str:
        data = await self.read(path)
        return data.decode("utf-8")

    # ---------------------------------------------------------
    # STAT
    # ---------------------------------------------------------
    async def stat(self, path: str) -> FilesystemResourceInfoResult:
        full = self._resolve_path(path)

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

    # ---------------------------------------------------------
    # GREP
    # ---------------------------------------------------------
    async def grep(self, pattern: str, prefix: str = "") -> List[str]:
        regex = re.compile(pattern)
        matches = []

        for entry in await self.list(prefix):
            if entry.is_file():
                content = await self.cat(entry.path)
                if regex.search(content):
                    matches.append(entry.path)

        return matches
