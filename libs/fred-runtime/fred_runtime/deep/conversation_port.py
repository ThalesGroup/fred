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

"""Fred capability access to the same virtual filesystem used by Deep tools."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from deepagents.backends.protocol import BackendProtocol
from deepagents.middleware.filesystem import FilesystemPermission
from fred_sdk.contracts.runtime import (
    ConversationFilesystemInterruptError,
    ConversationFilesystemPermissionError,
    ConversationFilesystemPort,
    ConversationFilesystemQuotaError,
    ConversationScratchpadEditConflictError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)
from wcmatch import glob as wcglob

Origin = Literal["agent", "system"]
_MATCH_FLAGS = wcglob.BRACE | wcglob.GLOBSTAR


class DeepConversationFilesystemPort(ConversationFilesystemPort):
    """Bind a composite backend and this invocation's effective ordered rules."""

    def __init__(
        self, backend: BackendProtocol, permissions: list[FilesystemPermission]
    ) -> None:
        self._backend = backend
        self._permissions = tuple(permissions)

    @property
    def backend(self) -> BackendProtocol:
        return self._backend

    @property
    def permissions(self) -> list[FilesystemPermission]:
        return list(self._permissions)

    def _check(
        self, path: str, operation: Literal["read", "write"], origin: Origin
    ) -> None:
        if origin == "system":
            return
        if origin != "agent":
            raise ValueError("Filesystem origin must be 'agent' or 'system'")
        for rule in self._permissions:
            if operation not in rule.operations:
                continue
            if any(
                wcglob.globmatch(path, pattern, flags=_MATCH_FLAGS)
                for pattern in rule.paths
            ):
                if rule.mode == "deny":
                    raise ConversationFilesystemPermissionError(
                        f"Permission denied for {operation} on {path}"
                    )
                if rule.mode == "interrupt":
                    raise ConversationFilesystemInterruptError(
                        f"Approval required for {operation} on {path}"
                    )
                return

    async def read_text(self, path: str, *, origin: Origin) -> str:
        path = _virtual_path(path)
        self._check(path, "read", origin)
        responses = await self._backend.adownload_files([path])
        response = responses[0]
        if response.error == "file_not_found":
            raise ConversationScratchpadFileNotFoundError(
                f"File does not exist: {path}"
            )
        if response.error is not None or response.content is None:
            raise ConversationScratchpadStorageError(
                "Conversation filesystem read failed"
            )
        try:
            return response.content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ConversationScratchpadUnsupportedContentError(
                "Conversation filesystem supports UTF-8 text only"
            ) from exc

    async def write_text(self, path: str, content: str, *, origin: Origin) -> None:
        path = _virtual_path(path)
        self._check(path, "write", origin)
        result = await self._backend.awrite(path, content)
        if result.error is not None:
            if "quota exceeded" in result.error:
                raise ConversationFilesystemQuotaError(result.error)
            raise ConversationScratchpadStorageError(result.error)

    async def edit_text(
        self,
        path: str,
        old_text: str,
        new_text: str,
        *,
        origin: Origin,
        replace_all: bool = False,
    ) -> int:
        path = _virtual_path(path)
        self._check(path, "write", origin)
        result = await self._backend.aedit(path, old_text, new_text, replace_all)
        if result.error is not None:
            if "uniquely match" in result.error:
                raise ConversationScratchpadEditConflictError(result.error)
            raise ConversationScratchpadStorageError(result.error)
        return result.occurrences or 0

    async def list(self, path: str = "/", *, origin: Origin) -> tuple[str, ...]:
        path = _virtual_path(path, allow_root=True)
        self._check(path, "read", origin)
        result = await self._backend.aglob("**", path=path)
        if result.error is not None:
            raise ConversationScratchpadStorageError(result.error)
        paths = []
        for info in result.matches or []:
            candidate = info["path"]
            try:
                self._check(candidate, "read", origin)
            except ConversationFilesystemPermissionError:
                continue
            paths.append(candidate)
        return tuple(sorted(paths))

    async def exists(self, path: str, *, origin: Origin) -> bool:
        path = _virtual_path(path)
        self._check(path, "read", origin)
        location = PurePosixPath(path)
        result = await self._backend.aglob(location.name, path=str(location.parent))
        if result.error is not None:
            raise ConversationScratchpadStorageError(
                "Conversation filesystem lookup failed"
            )
        return any(info["path"] == path for info in result.matches or [])


def _virtual_path(path: str, *, allow_root: bool = False) -> str:
    if not isinstance(path, str) or not path.startswith("/"):
        raise ConversationScratchpadInvalidPathError("Filesystem path must be absolute")
    if path == "/" and allow_root:
        return path
    if any(part in {"", ".", ".."} for part in path[1:].split("/")) or any(
        character == "\\" or ord(character) < 32 for character in path
    ):
        raise ConversationScratchpadInvalidPathError("Filesystem path is unsafe")
    return path
