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
    AREA_AGENT,
    AREA_CORPUS,
    AREA_TEAM,
    AREA_WORKSPACE,
    VirtualArea,
    absolute_virtual_path,
    dir_entry,
    format_numbered_file_excerpt,
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


class McpFilesystemService:
    """
    Routed virtual filesystem for MCP tools.

    Areas:
    - `/workspace/...` : user workspace files
    - `/agent/...`     : agent-scoped files
    - `/team/...`      : team-scoped files
    - `/corpus/...`    : read-only corpus virtual tree

    Backward compatibility:
    - `/user/...` is accepted as a legacy alias for `/workspace/...`
    - paths without a top-level area are treated as `/workspace/...`
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
        filesystem = context.get_filesystem()
        self.scoped_areas = ScopedAreaFilesystem(
            scoped_storage=WorkspaceFilesystem(filesystem),
            rebac=context.get_rebac_engine(),
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

        entries = [dir_entry(AREA_WORKSPACE)]
        if await self.scoped_areas.list_area(user, VirtualArea.AGENT, ()):
            entries.append(dir_entry(AREA_AGENT))
        if await self.scoped_areas.list_area(user, VirtualArea.TEAM, ()):
            entries.append(dir_entry(AREA_TEAM))
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
        limit: int = 100,
    ) -> str:
        """
        Read one text file using paginated numbered lines.

        Why this exists:
        - coding-oriented agents reason better over numbered excerpts than raw file blobs
        - pagination avoids forcing callers to load an entire large file at once

        How to use:
        - pass a visible file path plus optional zero-based `offset` and `limit`

        Example:
        - `await read_file(user, "/workspace/report.md", offset=0, limit=50)`
        """

        content = await self.cat(user, path)
        return format_numbered_file_excerpt(content, offset=offset, limit=limit)

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
            return await self.scoped_areas.list_area(user, resolved.area, resolved.segments)
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
            return await self.scoped_areas.stat_area(user, resolved.area, resolved.segments)
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
            return await self.scoped_areas.cat_area(user, resolved.area, resolved.segments)
        except Exception:
            logger.exception("Failed to read %s", path)
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
            await self.scoped_areas.write_area(user, resolved.area, resolved.segments, data)
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
            await self.scoped_areas.delete_area(user, resolved.area, resolved.segments)
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
                matches.extend(
                    await self.scoped_areas.grep_area(
                        user,
                        VirtualArea.WORKSPACE,
                        pattern,
                        (),
                    )
                )
                matches.extend(
                    await self.scoped_areas.grep_area(
                        user,
                        VirtualArea.AGENT,
                        pattern,
                        (),
                    )
                )
                matches.extend(
                    await self.scoped_areas.grep_area(
                        user,
                        VirtualArea.TEAM,
                        pattern,
                        (),
                    )
                )
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
                resolved.area,
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
            await self.scoped_areas.mkdir_area(user, resolved.area, resolved.segments)
        except Exception:
            logger.exception("Failed to create directory %s", path)
            raise
