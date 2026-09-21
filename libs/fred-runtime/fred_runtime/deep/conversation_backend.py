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

from pathlib import PurePosixPath

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
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
    ConversationScratchpadPort,
    ConversationScratchpadQuotaExceededError,
    ConversationScratchpadStorageError,
    ConversationScratchpadUnsupportedContentError,
)

_UNMOUNTED_PATH_ERROR = "Path is outside mounted conversation filesystems"


class ConversationNamespaceBackend(BackendProtocol):
    """Adapt one already-scoped conversation namespace to Deep's backend API."""

    def __init__(self, namespace: ConversationScratchpadPort) -> None:
        self._namespace = namespace

    async def als(self, path: str) -> LsResult:
        try:
            relative_directory = _relative_path(path, allow_root=True)
            descendants = await self._namespace.list(relative_directory)
            prefix = f"{relative_directory}/" if relative_directory else ""
            entries: dict[str, FileInfo] = {}

            for descendant in descendants:
                relative = descendant.removeprefix(prefix)
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
                entries[entry_path] = await self._file_info(entry_relative)

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
            file_data = {"content": content, "encoding": "utf-8"}
            sliced = slice_read_response(file_data, offset, limit)
            if isinstance(sliced, ReadResult):
                return sliced
            return ReadResult(file_data={"content": sliced, "encoding": "utf-8"})
        except ConversationScratchpadError as exc:
            return ReadResult(error=_error_message(exc))

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        try:
            relative_path = _relative_path(file_path)
            if await self._namespace.exists(relative_path):
                return WriteResult(
                    error=(
                        f"Cannot write to {file_path} because it already exists. "
                        "Read and then make an edit, or write to a new path."
                    )
                )
            await self._namespace.write_text(relative_path, content)
            return WriteResult(path=file_path)
        except ConversationScratchpadError as exc:
            return WriteResult(error=_error_message(exc))

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

    async def aglob(
        self, pattern: str, path: str | None = None
    ) -> GlobResult:
        try:
            relative_directory = _relative_path(path or "/", allow_root=True)
            prefix = f"{relative_directory}/" if relative_directory else ""
            matches: list[FileInfo] = []
            for descendant in await self._namespace.list(relative_directory):
                candidate = descendant.removeprefix(prefix)
                if PurePosixPath(candidate).match(pattern):
                    matches.append(await self._file_info(descendant))
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
            matches: list[GrepMatch] = []
            for descendant in await self._namespace.list(relative_directory):
                if glob and not PurePosixPath(descendant).match(glob):
                    continue
                content = await self._namespace.read_text(descendant)
                matches.extend(
                    {
                        "path": f"/{descendant}",
                        "line": line_number,
                        "text": line,
                    }
                    for line_number, line in enumerate(content.split("\n"), 1)
                    if pattern in line
                )
            return GrepResult(matches=matches)
        except ConversationScratchpadError as exc:
            return GrepResult(error=_error_message(exc))

    async def _file_info(self, relative_path: str) -> FileInfo:
        content = await self._namespace.read_text(relative_path)
        return {
            "path": f"/{relative_path}",
            "is_dir": False,
            "size": len(content.encode("utf-8")),
        }


class RejectingBackend(BackendProtocol):
    """Reject Deep file operations outside explicitly mounted namespaces."""

    async def als(self, path: str) -> LsResult:
        del path
        return LsResult(error=_UNMOUNTED_PATH_ERROR)

    async def aread(
        self, file_path: str, offset: int = 0, limit: int = 2000
    ) -> ReadResult:
        del file_path, offset, limit
        return ReadResult(error=_UNMOUNTED_PATH_ERROR)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        del file_path, content
        return WriteResult(error=_UNMOUNTED_PATH_ERROR)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        del file_path, old_string, new_string, replace_all
        return EditResult(error=_UNMOUNTED_PATH_ERROR)

    async def aglob(
        self, pattern: str, path: str | None = None
    ) -> GlobResult:
        del pattern, path
        return GlobResult(error=_UNMOUNTED_PATH_ERROR)

    async def agrep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> GrepResult:
        del pattern, path, glob
        return GrepResult(error=_UNMOUNTED_PATH_ERROR)


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
    if not path.startswith("/"):
        return path
    return path[1:]
