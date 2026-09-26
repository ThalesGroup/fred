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

"""Deep Agents adapters for conversation-bound text namespaces."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable
from pathlib import PurePosixPath
from typing import TypeVar

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileData,
    FileDownloadResponse,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)
from deepagents.backends.utils import slice_read_response
from fred_sdk.contracts.runtime import (
    ConversationScratchpadEditConflictError,
    ConversationScratchpadError,
    ConversationScratchpadFileNotFoundError,
    ConversationScratchpadInvalidPathError,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)

from fred_runtime.conversation_filesystem import (
    ConversationFilesystemService,
    ConversationTextFileMetadata,
)

_MAX_CONCURRENT_READS = 16

_InputT = TypeVar("_InputT")
_ResultT = TypeVar("_ResultT")


class ConversationNamespaceBackend(BackendProtocol):
    """Adapt one safe physical conversation namespace to Deep's backend API."""

    def __init__(
        self,
        conversation: ConversationFilesystemService,
        *,
        namespace_id: str,
        max_bytes: int,
        max_files: int,
    ) -> None:
        self._namespace = conversation.namespace(
            namespace_id, max_bytes=max_bytes, max_files=max_files
        )

    async def als(self, path: str) -> LsResult:
        try:
            relative_directory = _relative_path(path, allow_root=True)
            descendants = await self._namespace.list_metadata(relative_directory)
            prefix = f"{relative_directory}/" if relative_directory else ""
            entries: dict[str, FileInfo] = {}

            for descendant in descendants:
                relative = descendant.path.removeprefix(prefix)
                first, separator, _rest = relative.partition("/")
                if not first:
                    continue
                entry_relative = f"{prefix}{first}"
                entry_path = f"/{entry_relative}"
                if separator:
                    entries[entry_path] = {
                        "path": f"{entry_path}/",
                        "is_dir": True,
                        "size": 0,
                    }
                    continue
                entries[entry_path] = self._file_info(descendant)

            return LsResult(
                entries=sorted(entries.values(), key=lambda entry: entry["path"])
            )
        except ConversationScratchpadError as exc:
            return LsResult(error=_error_message(exc))

    async def aread(
        self,
        file_path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ReadResult:
        try:
            content = await self._namespace.read_text(_relative_path(file_path))
            file_data: FileData = {"content": content, "encoding": "utf-8"}
            sliced = slice_read_response(file_data, offset, limit)
            if isinstance(sliced, ReadResult):
                return sliced
            return ReadResult(file_data={"content": sliced, "encoding": "utf-8"})
        except ConversationScratchpadError as exc:
            return ReadResult(error=_error_message(exc))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        try:
            relative_path = _relative_path(file_path)
            await self._namespace.write_text(relative_path, content)
            return WriteResult(path=file_path)
        except ConversationScratchpadError as exc:
            return WriteResult(error=_error_message(exc))

    async def adownload_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        async def download(path: str) -> FileDownloadResponse:
            try:
                content = await self._namespace.read_bytes(_relative_path(path))
                return FileDownloadResponse(path=path, content=content)
            except ConversationScratchpadFileNotFoundError:
                return FileDownloadResponse(path=path, error="file_not_found")
            except ConversationScratchpadInvalidPathError:
                return FileDownloadResponse(path=path, error="invalid_path")
            except ConversationScratchpadError as exc:
                return FileDownloadResponse(path=path, error=_error_message(exc))

        return await _bounded_gather(paths, download)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        try:
            occurrences = await self._namespace.edit_text(
                _relative_path(file_path),
                old_string,
                new_string,
                replace_all=replace_all,
            )
            return EditResult(path=file_path, occurrences=occurrences)
        except ConversationScratchpadError as exc:
            return EditResult(error=_error_message(exc))

    async def aglob(self, pattern: str, path: str | None = None) -> GlobResult:
        try:
            relative_directory = _relative_path(path or "/", allow_root=True)
            prefix = f"{relative_directory}/" if relative_directory else ""
            descendants = [
                descendant
                for descendant in await self._namespace.list_metadata(
                    relative_directory
                )
                if PurePosixPath(descendant.path.removeprefix(prefix)).match(pattern)
            ]
            matches = [self._file_info(descendant) for descendant in descendants]
            return GlobResult(matches=matches)
        except ConversationScratchpadError as exc:
            return GlobResult(error=_error_message(exc))

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        try:
            relative_directory = _relative_path(path or "/", allow_root=True)
            descendants = [
                descendant
                for descendant in await self._namespace.list(relative_directory)
                if not glob or PurePosixPath(descendant).match(glob)
            ]

            async def grep_file(descendant: str) -> list[GrepMatch]:
                content = await self._namespace.read_text(descendant)
                return [
                    {
                        "path": f"/{descendant}",
                        "line": line_number,
                        "text": line,
                    }
                    for line_number, line in enumerate(content.split("\n"), 1)
                    if pattern in line
                ]

            per_file_matches = await _bounded_gather(descendants, grep_file)
            matches = [
                match for file_matches in per_file_matches for match in file_matches
            ]
            return GrepResult(matches=matches)
        except ConversationScratchpadError as exc:
            return GrepResult(error=_error_message(exc))

    @staticmethod
    def _file_info(metadata: ConversationTextFileMetadata) -> FileInfo:
        return {
            "path": f"/{metadata.path}",
            "is_dir": False,
            "size": metadata.size,
        }


async def _bounded_gather(
    items: Iterable[_InputT],
    operation: Callable[[_InputT], Awaitable[_ResultT]],
) -> list[_ResultT]:
    """Run independent storage reads concurrently without flooding the provider."""
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_READS)

    async def run(item: _InputT) -> _ResultT:
        async with semaphore:
            return await operation(item)

    return list(await asyncio.gather(*(run(item) for item in items)))


def _error_message(error: ConversationScratchpadError) -> str:
    if isinstance(error, ConversationScratchpadStorageError):
        return "Shared scratchpad storage failed"
    if isinstance(
        error,
        (
            ConversationScratchpadEditConflictError,
            ConversationScratchpadFileNotFoundError,
            ConversationScratchpadInvalidPathError,
            ConversationScratchpadUnsupportedContentError,
        ),
    ):
        return str(error)
    if isinstance(error, ConversationScratchpadQuotaExceededError):
        return "Shared scratchpad quota exceeded"
    return "Shared scratchpad operation failed"


def _relative_path(path: str, *, allow_root: bool = False) -> str:
    if path == "/" and allow_root:
        return ""
    if allow_root and path.endswith("/"):
        path = path[:-1]
    if not path.startswith("/"):
        return path
    return path[1:]
