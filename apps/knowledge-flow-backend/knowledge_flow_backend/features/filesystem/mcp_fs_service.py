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

from __future__ import annotations

import fnmatch
import logging
from typing import List

from fred_core import (
    Action,
    FilesystemResourceInfoResult,
    KeycloakUser,
    Resource,
    authorize,
)

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.content.content_service import ContentService
from knowledge_flow_backend.features.filesystem.corpus_virtual_filesystem import (
    CorpusVirtualFilesystem,
)
from knowledge_flow_backend.features.filesystem.scoped_area_filesystem import (
    ScopedAreaFilesystem,
)
from knowledge_flow_backend.features.filesystem.virtual_fs_contract import (
    AREA_CORPUS,
    AREA_TEAMS,
    FileReadPage,
    VirtualArea,
    absolute_virtual_path,
    dir_entry,
    format_numbered_file_page,
    join_virtual_child,
    normalize_virtual_path,
    resolve_virtual_path,
)
from knowledge_flow_backend.features.filesystem.workspace_filesystem import (
    WorkspaceFilesystem,
)
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)


class FilesystemReadBounds:
    """
    Effective server-side bounds for paginated filesystem reads.

    Why this exists:
    - bounded reads must be enforced consistently for HTTP and MCP callers
    - keeping the resolved defaults together avoids sprinkling config lookups

    How to use:
    - build once from configuration during service initialization
    - pass optional caller values to `resolve(...)` before formatting output
    """

    def __init__(
        self,
        *,
        default_limit: int,
        max_limit: int,
        default_max_chars: int,
        absolute_max_chars: int,
    ) -> None:
        self.default_limit = default_limit
        self.max_limit = max_limit
        self.default_max_chars = default_max_chars
        self.absolute_max_chars = absolute_max_chars

    def resolve(
        self,
        *,
        limit: int | None,
        max_chars: int | None,
    ) -> tuple[int, int]:
        """
        Resolve caller inputs to validated effective read bounds.

        Why this exists:
        - callers may omit optional bounds but the backend must still enforce defaults
        - upper-limit checks belong close to the canonical config values

        How to use:
        - pass the optional caller-provided `limit` and `max_chars`
        - receive the effective `(limit, max_chars)` pair or a ValueError
        """

        effective_limit = self.default_limit if limit is None else limit
        effective_max_chars = self.default_max_chars if max_chars is None else max_chars
        if effective_limit <= 0:
            raise ValueError("limit must be > 0")
        if effective_limit > self.max_limit:
            raise ValueError(f"limit must be <= {self.max_limit}")
        if effective_max_chars <= 0:
            raise ValueError("max_chars must be > 0")
        if effective_max_chars > self.absolute_max_chars:
            raise ValueError(f"max_chars must be <= {self.absolute_max_chars}")
        return effective_limit, effective_max_chars


class McpFilesystemService:
    """
    Routed virtual filesystem for MCP tools.

    Areas (unified layout — FILES-04):
    - `/teams/{team_id}/...` : team box — `users/{uid}`, `shared`, `agents/{id}/users/{uid}`
    - `/corpus/...`          : read-only corpus virtual tree

    There is no implicit/default area and no legacy alias: an unknown top-level
    segment is rejected by `resolve_virtual_path`.
    """

    def __init__(self) -> None:
        """
        Build the filesystem facade from the shared application context.

        Why this exists:
        - the public MCP service should stay thin and delegate domain-specific work
          to smaller collaborators
        - constructing those collaborators once keeps the runtime wiring centralized

        How to use:
        - instantiate once per controller or dependency container

        Example:
        - `service = McpFilesystemService()`
        """

        context = ApplicationContext.get_instance()
        mcp_config = context.get_config().mcp
        filesystem = context.get_filesystem()
        self.scoped_areas = ScopedAreaFilesystem(
            scoped_storage=WorkspaceFilesystem(filesystem),
            rebac=context.get_rebac_engine(),
        )
        self.read_bounds = FilesystemReadBounds(
            default_limit=mcp_config.filesystem_read_default_limit,
            max_limit=mcp_config.filesystem_read_max_limit,
            default_max_chars=mcp_config.filesystem_read_default_max_chars,
            absolute_max_chars=mcp_config.filesystem_read_absolute_max_chars,
        )
        self.corpus_area = CorpusVirtualFilesystem(
            metadata_service=MetadataService(),
            content_service=ContentService(),
            tag_service=TagService(),
        )

    async def _root_entries(
        self,
        user: KeycloakUser,
    ) -> list[FilesystemResourceInfoResult]:
        """
        Return the visible top-level directories of the virtual filesystem.

        Why this exists:
        - the virtual root should expose only areas that make sense for the current user
        - one helper keeps that visibility policy centralized across callers

        How to use:
        - call when a resolved path belongs to `VirtualArea.ROOT`

        Example:
        - `await _root_entries(user)`
        """

        entries = [dir_entry(AREA_TEAMS)]
        if await self.corpus_area.list_area(user, ()):
            entries.append(dir_entry(AREA_CORPUS))
        return entries

    async def _walk_visible_tree(
        self,
        user: KeycloakUser,
        path: str = "/",
    ) -> List[FilesystemResourceInfoResult]:
        """
        Walk one visible virtual subtree and return absolute recursive entries.

        Why this exists:
        - `glob(...)` needs a recursive tree view
        - the public `ls(...)` contract should stay directory-local like a normal filesystem

        How to use:
        - pass any visible path accepted by the filesystem service

        Example:
        - `await _walk_visible_tree(user, "/corpus")`
        """

        current_path = absolute_virtual_path(path)
        entries = await self.ls(user, current_path)
        discovered: list[FilesystemResourceInfoResult] = []
        for entry in entries:
            child_path = join_virtual_child(current_path, entry.path)
            absolute_entry = FilesystemResourceInfoResult(
                path=child_path,
                size=entry.size,
                type=entry.type,
                modified=entry.modified,
            )
            discovered.append(absolute_entry)
            if entry.is_dir():
                discovered.extend(await self._walk_visible_tree(user, child_path))
        return discovered

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def ls(
        self,
        user: KeycloakUser,
        path: str = "/",
    ) -> List[FilesystemResourceInfoResult]:
        """
        List the direct children of one visible virtual directory.

        Why this exists:
        - agents and MCP clients should interact with Fred FS like a normal filesystem
        - `ls(...)` is the standard mental model for folder inspection

        How to use:
        - pass any visible path such as `/workspace`, `/corpus/CIR`, or `/team/<id>`

        Example:
        - `await ls(user, "/corpus")`
        """

        return await self.list(user, normalize_virtual_path(path))

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def read_file(
        self,
        user: KeycloakUser,
        path: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        max_chars: int | None = None,
    ) -> str:
        """
        Read one text file using paginated numbered lines.

        Why this exists:
        - coding-oriented agents reason better over numbered excerpts than raw file blobs
        - pagination avoids forcing callers to load an entire large file at once

        How to use:
        - pass a visible file path plus optional zero-based `offset`, `limit`, and `max_chars`

        Example:
        - `await read_file(user, "/workspace/report.md", offset=0, limit=50, max_chars=5000)`
        """

        return (
            await self.read_file_page(
                user,
                path,
                offset=offset,
                limit=limit,
                max_chars=max_chars,
            )
        ).content

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def read_file_page(
        self,
        user: KeycloakUser,
        path: str,
        *,
        offset: int = 0,
        limit: int | None = None,
        max_chars: int | None = None,
    ) -> FileReadPage:
        """
        Read one text file as a structured numbered page with continuation metadata.

        Why this exists:
        - long-document agents need a reliable `next_offset` instead of guessing after truncation
        - the filesystem layer should expose this safely without adding a parallel document API

        How to use:
        - pass the same path inputs as `read_file(...)`
        - continue with `next_offset` while `has_more` is true

        Example:
        - `await read_file_page(user, "/corpus/documents/doc-1/preview.md", offset=0, limit=40, max_chars=20000)`
        """

        effective_limit, effective_max_chars = self.read_bounds.resolve(
            limit=limit,
            max_chars=max_chars,
        )
        content = await self.cat(user, path)
        return format_numbered_file_page(
            path=absolute_virtual_path(path),
            content=content,
            offset=offset,
            limit=effective_limit,
            max_chars=effective_max_chars,
            max_read_lines=self.read_bounds.max_limit,
            max_read_chars=self.read_bounds.absolute_max_chars,
        )

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def glob(
        self,
        user: KeycloakUser,
        pattern: str,
        path: str = "/",
    ) -> List[str]:
        """
        Find visible virtual paths that match one glob pattern.

        Why this exists:
        - standard agents expect a filesystem-native way to discover files recursively
        - `glob(...)` removes the need for Fred-specific search habits

        How to use:
        - pass a glob pattern plus an optional base path

        Example:
        - `await glob(user, "**/*.md", path="/workspace")`
        """

        base_path = absolute_virtual_path(path)
        normalized_pattern = pattern.lstrip("/")
        matches: list[str] = []
        for entry in await self._walk_visible_tree(user, base_path):
            if entry.is_dir():
                continue
            if base_path == "/":
                relative_path = entry.path.lstrip("/")
            else:
                relative_path = entry.path[len(base_path.rstrip("/")) + 1 :]
            if fnmatch.fnmatch(entry.path, pattern) or fnmatch.fnmatch(entry.path.lstrip("/"), normalized_pattern) or fnmatch.fnmatch(relative_path, normalized_pattern):
                matches.append(entry.path)
        return matches

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def edit_file(
        self,
        user: KeycloakUser,
        path: str,
        *,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> dict[str, int | str]:
        """
        Apply one exact string replacement to an existing writable file.

        Why this exists:
        - standard agent file workflows rely on edit-in-place, not only full rewrites
        - exact replacement keeps the first Fred implementation intentionally small

        How to use:
        - pass a visible writable file path plus the exact text to replace
        - when `replace_all` is false, the old string must occur exactly once

        Example:
        - `await edit_file(user, "/workspace/note.md", old_string="draft", new_string="final")`
        """

        if not old_string:
            raise ValueError("old_string cannot be empty")
        if old_string == new_string:
            raise ValueError("new_string must differ from old_string")

        original = await self.cat(user, path)
        occurrences = original.count(old_string)
        if occurrences == 0:
            raise ValueError("old_string was not found in the target file")
        if not replace_all and occurrences != 1:
            raise ValueError("old_string must occur exactly once unless replace_all=true")

        updated = original.replace(old_string, new_string) if replace_all else original.replace(old_string, new_string, 1)
        await self.write(user, path, updated)
        return {"path": absolute_virtual_path(path), "occurrences": occurrences}

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def list(
        self,
        user: KeycloakUser,
        prefix: str = "",
    ) -> List[FilesystemResourceInfoResult]:
        """
        List one visible virtual directory using canonical path routing.

        Why this exists:
        - legacy aliases such as `/user` should still resolve through one public entrypoint
        - the service facade should expose one stable directory listing contract

        How to use:
        - pass a visible path or an empty string for the filesystem root

        Example:
        - `await list(user, "corpus/CIR")`
        """

        try:
            resolved = resolve_virtual_path(prefix)
            if resolved.area == VirtualArea.ROOT:
                return await self._root_entries(user)
            if resolved.area == VirtualArea.CORPUS:
                return await self.corpus_area.list_area(user, resolved.segments)
            return await self.scoped_areas.list_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to list filesystem entries")
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def stat(self, user: KeycloakUser, path: str) -> FilesystemResourceInfoResult:
        """
        Stat one visible virtual path.

        Why this exists:
        - MCP callers need one entrypoint that hides whether a path is backed by storage
          or synthesized virtually
        - routing here keeps the HTTP/controller layer simple

        How to use:
        - pass any visible virtual path

        Example:
        - `await stat(user, "/team/team-1/reports")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                return dir_entry("/")
            if resolved.area == VirtualArea.CORPUS:
                return await self.corpus_area.stat_area(user, resolved.segments)
            return await self.scoped_areas.stat_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to stat %s", path)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def cat(self, user: KeycloakUser, path: str) -> str:
        """
        Read one visible virtual file as text.

        Why this exists:
        - callers should not need to know whether a file comes from scoped storage
          or from the synthesized corpus area
        - routing here keeps file reads uniform across the visible filesystem

        How to use:
        - pass any visible file path

        Example:
        - `await cat(user, "/corpus/CIR/offer.docx/preview.md")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise FileNotFoundError("Cannot read root as file")
            if resolved.area == VirtualArea.CORPUS:
                return await self.corpus_area.cat_area(user, resolved.segments)
            return await self.scoped_areas.cat_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to read %s", path)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def read_bytes(self, user: KeycloakUser, path: str) -> bytes:
        """
        Read one writable-area file as raw bytes (binary-safe download).

        Why this exists:
        - templates and deliverables (e.g. .pptx) must round-trip byte-for-byte, which the
          text-oriented `cat(...)` path cannot guarantee
        - this is the single binary read surface over the team-rooted filesystem

        The read-only corpus is not served here: its original binaries are downloaded
        through the dedicated content API.

        Example:
        - `await read_bytes(user, "/teams/acme/shared/templates/deck.pptx")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise FileNotFoundError("Cannot read filesystem root as a file")
            if resolved.area == VirtualArea.CORPUS:
                raise PermissionError("Corpus binaries are served by the content API, not /fs")
            return await self.scoped_areas.read_bytes_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to read bytes %s", path)
            raise

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def write_bytes(self, user: KeycloakUser, path: str, data: bytes) -> None:
        """
        Write one writable-area file from raw bytes (binary-safe upload).

        Example:
        - `await write_bytes(user, "/teams/acme/users/u-1/outputs/q3.pptx", deck_bytes)`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise PermissionError("Cannot write at filesystem root")
            if resolved.area == VirtualArea.CORPUS:
                raise PermissionError("Corpus area is read-only")
            await self.scoped_areas.write_bytes_area(user, resolved.segments, data)
        except Exception:
            logger.exception("Failed to write bytes %s", path)
            raise

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def write(self, user: KeycloakUser, path: str, data: str) -> None:
        """
        Write one visible virtual file.

        Why this exists:
        - writable areas share one public filesystem contract
        - corpus stays read-only even though it is part of the same visible tree

        How to use:
        - pass a visible writable path plus the text content to store

        Example:
        - `await write(user, "/workspace/notes.md", "hello")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise PermissionError("Cannot write at filesystem root")
            if resolved.area == VirtualArea.CORPUS:
                raise PermissionError("Corpus area is read-only")
            await self.scoped_areas.write_area(user, resolved.segments, data)
        except Exception:
            logger.exception("Failed to write %s", path)
            raise

    @authorize(action=Action.DELETE, resource=Resource.FILES)
    async def delete(self, user: KeycloakUser, path: str) -> None:
        """
        Delete one visible virtual file or directory.

        Why this exists:
        - writable areas share one public filesystem contract
        - corpus stays read-only even though it is part of the same visible tree

        How to use:
        - pass one visible writable path

        Example:
        - `await delete(user, "/workspace/notes.md")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise PermissionError("Cannot delete root")
            if resolved.area == VirtualArea.CORPUS:
                raise PermissionError("Corpus area is read-only")
            await self.scoped_areas.delete_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to delete %s", path)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def grep(self, user: KeycloakUser, pattern: str, prefix: str = "") -> List[str]:
        """
        Search one visible virtual subtree and return matching file paths.

        Why this exists:
        - agents need one search entrypoint that matches the visible filesystem layout
        - corpus and writable areas use different backends but should return the same path shape

        How to use:
        - pass a regex pattern plus an optional visible path prefix

        Example:
        - `await grep(user, "invoice", "/corpus/CIR")`
        """

        try:
            resolved = resolve_virtual_path(prefix)
            if resolved.area == VirtualArea.ROOT:
                matches: list[str] = []
                matches.extend(await self.scoped_areas.grep_area(user, pattern, ()))
                matches.extend(f"/{path.lstrip('/')}" for path in await self.corpus_area.grep_area(user, pattern, ()))
                return matches
            if resolved.area == VirtualArea.CORPUS:
                return [
                    f"/{path.lstrip('/')}"
                    for path in await self.corpus_area.grep_area(
                        user,
                        pattern,
                        resolved.segments,
                    )
                ]
            return await self.scoped_areas.grep_area(
                user,
                pattern,
                resolved.segments,
            )
        except Exception:
            logger.exception("Grep failed for pattern '%s' with prefix '%s'", pattern, prefix)
            raise

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def mkdir(self, user: KeycloakUser, path: str) -> None:
        """
        Create one visible virtual directory.

        Why this exists:
        - writable areas share one public directory-creation contract
        - corpus stays read-only even though it is part of the same visible tree

        How to use:
        - pass one visible writable directory path

        Example:
        - `await mkdir(user, "/workspace/reports")`
        """

        try:
            resolved = resolve_virtual_path(path)
            if resolved.area == VirtualArea.ROOT:
                raise PermissionError("Cannot create root")
            if resolved.area == VirtualArea.CORPUS:
                raise PermissionError("Corpus area is read-only")
            await self.scoped_areas.mkdir_area(user, resolved.segments)
        except Exception:
            logger.exception("Failed to create directory %s", path)
            raise
