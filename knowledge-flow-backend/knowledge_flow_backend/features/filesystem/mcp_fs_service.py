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

import json
import logging
import posixpath
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import List

from fred_core import (
    Action,
    AgentPermission,
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
    KeycloakUser,
    Resource,
    TeamPermission,
    authorize,
)

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.content.content_service import ContentService
from knowledge_flow_backend.features.filesystem.workspace_filesystem import (
    WorkspaceFilesystem,
)
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.structure import TagType
from knowledge_flow_backend.features.tag.tag_service import TagService

logger = logging.getLogger(__name__)

_AREA_USER = "user"
_AREA_AGENT = "agent"
_AREA_TEAM = "team"
_AREA_CORPUS = "corpus"
_AREA_NAMES = {_AREA_USER, _AREA_AGENT, _AREA_TEAM, _AREA_CORPUS}
_CORPUS_LIBRARIES = "libraries"
_CORPUS_DOCUMENTS = "documents"


class _Area(str, Enum):
    ROOT = "root"
    USER = _AREA_USER
    AGENT = _AREA_AGENT
    TEAM = _AREA_TEAM
    CORPUS = _AREA_CORPUS


@dataclass(frozen=True)
class _ResolvedPath:
    area: _Area
    segments: tuple[str, ...]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dir(path: str) -> FilesystemResourceInfoResult:
    return FilesystemResourceInfoResult(
        path=path,
        size=None,
        type=FilesystemResourceInfo.DIRECTORY,
        modified=None,
    )


def _file(path: str, size: int) -> FilesystemResourceInfoResult:
    return FilesystemResourceInfoResult(
        path=path,
        size=size,
        type=FilesystemResourceInfo.FILE,
        modified=_now(),
    )


def _normalize_path(path: str) -> str:
    raw = (path or "").strip().replace("\\", "/").lstrip("/")
    if not raw:
        return ""
    normalized = posixpath.normpath(raw)
    if normalized in (".", "/"):
        return ""
    parts = [seg for seg in normalized.split("/") if seg]
    if any(seg == ".." for seg in parts):
        raise ValueError("Path cannot contain parent path segments")
    return "/".join(parts)


def _join_segments(segments: tuple[str, ...]) -> str:
    if not segments:
        return ""
    return "/".join(segments)


class McpFilesystemService:
    """
    Routed virtual filesystem for MCP tools.

    Areas:
    - `/user/...`   : user workspace files (`users/<uid>/...`)
    - `/agent/...`  : agent-scoped files (`agents/<agent_id>/config/...`)
    - `/team/...`   : team-scoped files (`teams/<team_id>/...`)
    - `/corpus/...` : read-only virtual corpus view (metadata + previews)

    Backward compatibility:
    - paths without a top-level area are treated as `/user/...`.
    """

    def __init__(self):
        context = ApplicationContext.get_instance()
        self.fs = context.get_filesystem()
        self.rebac = context.get_rebac_engine()
        self.scoped_storage = WorkspaceFilesystem(self.fs)
        self.metadata_service = MetadataService()
        self.content_service = ContentService()
        self.tag_service = TagService()

    def _resolve(self, path: str, *, default_area: _Area = _Area.USER) -> _ResolvedPath:
        normalized = _normalize_path(path)
        if not normalized:
            return _ResolvedPath(area=_Area.ROOT, segments=())
        parts = tuple(seg for seg in normalized.split("/") if seg)
        head = parts[0]
        if head in _AREA_NAMES:
            return _ResolvedPath(area=_Area(head), segments=parts[1:])
        return _ResolvedPath(area=default_area, segments=parts)

    async def _ensure_agent_permission(
        self,
        user: KeycloakUser,
        *,
        agent_id: str,
        permission: AgentPermission,
    ) -> None:
        await self.rebac.check_user_permission_or_raise(user, permission, agent_id)

    async def _ensure_team_permission(
        self,
        user: KeycloakUser,
        *,
        team_id: str,
        permission: TeamPermission,
    ) -> None:
        await self.rebac.check_user_permission_or_raise(user, permission, team_id)

    async def _list_agent_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> List[FilesystemResourceInfoResult]:
        if not segments:
            # We deliberately avoid broad agent enumeration here.
            return []
        agent_id, *sub = segments
        await self._ensure_agent_permission(
            user,
            agent_id=agent_id,
            permission=AgentPermission.READ,
        )
        sub_prefix = "/".join(sub) if sub else ""
        return await self.scoped_storage.list(
            user,
            sub_prefix,
            owner_override=f"{agent_id}/config",
            root_prefix="agents",
        )

    async def _list_team_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> List[FilesystemResourceInfoResult]:
        if not segments:
            # We deliberately avoid broad team enumeration here.
            return []
        team_id, *sub = segments
        await self._ensure_team_permission(
            user,
            team_id=team_id,
            permission=TeamPermission.CAN_READ,
        )
        sub_prefix = "/".join(sub) if sub else ""
        return await self.scoped_storage.list(
            user,
            sub_prefix,
            owner_override=team_id,
            root_prefix="teams",
        )

    async def _get_tag_for_user(self, user: KeycloakUser, tag_id: str):
        return await self.tag_service.get_tag_for_user(tag_id, user)

    async def _list_documents_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        tag = await self._get_tag_for_user(user, tag_id)
        return sorted(set(tag.item_ids or []))

    async def _ensure_document_in_tag(self, user: KeycloakUser, tag_id: str, document_uid: str) -> None:
        doc_ids = await self._list_documents_for_tag(user, tag_id)
        if document_uid not in doc_ids:
            raise FileNotFoundError(f"Document {document_uid!r} is not in library {tag_id!r}.")

    async def _render_document_metadata_json(self, user: KeycloakUser, document_uid: str) -> str:
        metadata = await self.metadata_service.get_document_metadata(user, document_uid)
        return json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2)

    async def _render_document_preview(self, user: KeycloakUser, document_uid: str) -> str:
        return await self.content_service.get_markdown_preview(user, document_uid)

    async def _render_library_manifest_json(self, user: KeycloakUser, tag_id: str) -> str:
        tag = await self._get_tag_for_user(user, tag_id)
        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
        payload = {
            "library": {
                "id": tag.id,
                "name": tag.name,
                "full_path": tag.full_path,
                "type": tag.type.value,
            },
            "documents": [
                {
                    "document_uid": doc.document_uid,
                    "document_name": doc.document_name,
                    "mime_type": doc.file.mime_type,
                    "updated_at": doc.modified.isoformat() if doc.modified else None,
                }
                for doc in docs
            ],
            "count": len(docs),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    async def _list_corpus_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> List[FilesystemResourceInfoResult]:
        if not segments:
            return [_dir(_CORPUS_LIBRARIES), _dir(_CORPUS_DOCUMENTS)]

        head = segments[0]
        if head == _CORPUS_LIBRARIES:
            if len(segments) == 1:
                tags = await self.tag_service.list_all_tags_for_user(
                    user,
                    tag_type=TagType.DOCUMENT,
                    limit=10_000,
                    offset=0,
                )
                return [_dir(tag.id) for tag in tags]

            tag_id = segments[1]
            if len(segments) == 2:
                await self._get_tag_for_user(user, tag_id)
                return [_file("manifest.json", 0), _dir(_CORPUS_DOCUMENTS)]

            if len(segments) == 3 and segments[2] == _CORPUS_DOCUMENTS:
                docs = await self._list_documents_for_tag(user, tag_id)
                return [_dir(uid) for uid in docs]

            if len(segments) == 4 and segments[2] == _CORPUS_DOCUMENTS:
                document_uid = segments[3]
                await self._ensure_document_in_tag(user, tag_id, document_uid)
                return [_file("metadata.json", 0), _file("preview.md", 0)]

            raise FileNotFoundError("Unknown corpus library path")

        if head == _CORPUS_DOCUMENTS:
            if len(segments) == 1:
                docs = await self.metadata_service.get_documents_metadata(user, {})
                return [_dir(doc.document_uid) for doc in docs]

            document_uid = segments[1]
            # Permission + existence check
            await self.metadata_service.get_document_metadata(user, document_uid)
            if len(segments) == 2:
                return [_file("metadata.json", 0), _file("preview.md", 0)]
            raise FileNotFoundError("Unknown corpus document path")

        raise FileNotFoundError("Unknown corpus path")

    async def _cat_corpus_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> str:
        if len(segments) < 3:
            raise FileNotFoundError("Corpus file path is incomplete")

        if segments[0] == _CORPUS_DOCUMENTS and len(segments) == 3:
            document_uid = segments[1]
            file_name = segments[2]
            if file_name == "metadata.json":
                return await self._render_document_metadata_json(user, document_uid)
            if file_name == "preview.md":
                return await self._render_document_preview(user, document_uid)
            raise FileNotFoundError("Unknown corpus document file")

        if len(segments) == 5 and segments[0] == _CORPUS_LIBRARIES and segments[2] == _CORPUS_DOCUMENTS:
            tag_id = segments[1]
            document_uid = segments[3]
            file_name = segments[4]
            await self._ensure_document_in_tag(user, tag_id, document_uid)
            if file_name == "metadata.json":
                return await self._render_document_metadata_json(user, document_uid)
            if file_name == "preview.md":
                return await self._render_document_preview(user, document_uid)
            raise FileNotFoundError("Unknown corpus library document file")

        if len(segments) == 3 and segments[0] == _CORPUS_LIBRARIES and segments[2] == "manifest.json":
            return await self._render_library_manifest_json(user, segments[1])

        raise FileNotFoundError("Unknown corpus file path")

    async def _stat_corpus_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> FilesystemResourceInfoResult:
        if not segments:
            return _dir(_AREA_CORPUS)
        try:
            # Any successful list means the path resolves to a directory,
            # including empty directories.
            await self._list_corpus_area(user, segments)
            return _dir(_join_segments(segments))
        except FileNotFoundError:
            content = await self._cat_corpus_area(user, segments)
            return _file(_join_segments(segments), len(content.encode("utf-8")))

    async def _grep_corpus_area(self, user: KeycloakUser, pattern: str, segments: tuple[str, ...]) -> List[str]:
        regex = re.compile(pattern)
        matches: list[str] = []

        if not segments:
            docs = await self.metadata_service.get_documents_metadata(user, {})
            for doc in docs:
                try:
                    text = await self._render_document_preview(user, doc.document_uid)
                except Exception:
                    continue
                if regex.search(text):
                    matches.append(f"{_AREA_CORPUS}/{_CORPUS_DOCUMENTS}/{doc.document_uid}/preview.md")
            return matches

        if len(segments) >= 2 and segments[0] == _CORPUS_DOCUMENTS and len(segments) == 2:
            text = await self._render_document_preview(user, segments[1])
            if regex.search(text):
                matches.append(f"{_AREA_CORPUS}/{_CORPUS_DOCUMENTS}/{segments[1]}/preview.md")
            return matches

        if len(segments) >= 2 and segments[0] == _CORPUS_LIBRARIES and len(segments) == 2:
            tag_id = segments[1]
            for uid in await self._list_documents_for_tag(user, tag_id):
                try:
                    text = await self._render_document_preview(user, uid)
                except Exception:
                    continue
                if regex.search(text):
                    matches.append(f"{_AREA_CORPUS}/{_CORPUS_LIBRARIES}/{tag_id}/{_CORPUS_DOCUMENTS}/{uid}/preview.md")
            return matches

        # Fallback: if prefix points to one concrete file, try it.
        try:
            content = await self._cat_corpus_area(user, segments)
        except Exception:
            return []
        if regex.search(content):
            matches.append(f"{_AREA_CORPUS}/{_join_segments(segments)}")
        return matches

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def list(self, user: KeycloakUser, prefix: str = "") -> List[FilesystemResourceInfoResult]:
        try:
            resolved = self._resolve(prefix)
            if resolved.area == _Area.ROOT:
                return [_dir(_AREA_USER), _dir(_AREA_AGENT), _dir(_AREA_TEAM), _dir(_AREA_CORPUS)]

            if resolved.area == _Area.USER:
                return await self.scoped_storage.list(user, _join_segments(resolved.segments))

            if resolved.area == _Area.AGENT:
                return await self._list_agent_area(user, resolved.segments)

            if resolved.area == _Area.TEAM:
                return await self._list_team_area(user, resolved.segments)

            if resolved.area == _Area.CORPUS:
                return await self._list_corpus_area(user, resolved.segments)

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to list filesystem entries")
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def stat(self, user: KeycloakUser, path: str) -> FilesystemResourceInfoResult:
        try:
            resolved = self._resolve(path)
            if resolved.area == _Area.ROOT:
                return _dir("/")

            if resolved.area == _Area.USER:
                if not resolved.segments:
                    return _dir(_AREA_USER)
                return await self.scoped_storage.stat(user, _join_segments(resolved.segments))

            if resolved.area == _Area.AGENT:
                if not resolved.segments:
                    return _dir(_AREA_AGENT)
                agent_id, *sub = resolved.segments
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.READ,
                )
                if not sub:
                    return _dir(f"{_AREA_AGENT}/{agent_id}")
                return await self.scoped_storage.stat(
                    user,
                    "/".join(sub),
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )

            if resolved.area == _Area.TEAM:
                if not resolved.segments:
                    return _dir(_AREA_TEAM)
                team_id, *sub = resolved.segments
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_READ,
                )
                if not sub:
                    return _dir(f"{_AREA_TEAM}/{team_id}")
                return await self.scoped_storage.stat(
                    user,
                    "/".join(sub),
                    owner_override=team_id,
                    root_prefix="teams",
                )

            if resolved.area == _Area.CORPUS:
                return await self._stat_corpus_area(user, resolved.segments)

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to stat %s", path)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def cat(self, user: KeycloakUser, path: str) -> str:
        try:
            resolved = self._resolve(path)
            if resolved.area == _Area.ROOT:
                raise FileNotFoundError("Cannot read root as file")

            if resolved.area == _Area.USER:
                if not resolved.segments:
                    raise FileNotFoundError("Cannot read /user as file")
                return await self.scoped_storage.get_text(user, _join_segments(resolved.segments))

            if resolved.area == _Area.AGENT:
                if len(resolved.segments) < 2:
                    raise FileNotFoundError("Agent file path must be /agent/<agent_id>/<file>")
                agent_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.READ,
                )
                return await self.scoped_storage.get_text(
                    user,
                    subpath,
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )

            if resolved.area == _Area.TEAM:
                if len(resolved.segments) < 2:
                    raise FileNotFoundError("Team file path must be /team/<team_id>/<file>")
                team_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_READ,
                )
                return await self.scoped_storage.get_text(
                    user,
                    subpath,
                    owner_override=team_id,
                    root_prefix="teams",
                )

            if resolved.area == _Area.CORPUS:
                return await self._cat_corpus_area(user, resolved.segments)

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to read %s", path)
            raise

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def write(self, user: KeycloakUser, path: str, data: str) -> None:
        try:
            resolved = self._resolve(path)
            if resolved.area == _Area.ROOT:
                raise PermissionError("Cannot write at filesystem root")

            if resolved.area == _Area.CORPUS:
                raise PermissionError("Corpus area is read-only")

            if resolved.area == _Area.USER:
                if not resolved.segments:
                    raise PermissionError("Cannot write to /user root")
                await self.scoped_storage.put(user, _join_segments(resolved.segments), data)
                return

            if resolved.area == _Area.AGENT:
                if len(resolved.segments) < 2:
                    raise PermissionError("Write path must be /agent/<agent_id>/<file>")
                agent_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.UPDATE,
                )
                await self.scoped_storage.put(
                    user,
                    subpath,
                    data,
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )
                return

            if resolved.area == _Area.TEAM:
                if len(resolved.segments) < 2:
                    raise PermissionError("Write path must be /team/<team_id>/<file>")
                team_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_UPDATE_RESOURCES,
                )
                await self.scoped_storage.put(
                    user,
                    subpath,
                    data,
                    owner_override=team_id,
                    root_prefix="teams",
                )
                return

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to write %s", path)
            raise

    @authorize(action=Action.DELETE, resource=Resource.FILES)
    async def delete(self, user: KeycloakUser, path: str) -> None:
        try:
            resolved = self._resolve(path)
            if resolved.area == _Area.ROOT:
                raise PermissionError("Cannot delete root")

            if resolved.area == _Area.CORPUS:
                raise PermissionError("Corpus area is read-only")

            if resolved.area == _Area.USER:
                if not resolved.segments:
                    raise PermissionError("Cannot delete /user root")
                await self.scoped_storage.delete(user, _join_segments(resolved.segments))
                return

            if resolved.area == _Area.AGENT:
                if len(resolved.segments) < 2:
                    raise PermissionError("Delete path must be /agent/<agent_id>/<file>")
                agent_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.DELETE,
                )
                await self.scoped_storage.delete(
                    user,
                    subpath,
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )
                return

            if resolved.area == _Area.TEAM:
                if len(resolved.segments) < 2:
                    raise PermissionError("Delete path must be /team/<team_id>/<file>")
                team_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_UPDATE_RESOURCES,
                )
                await self.scoped_storage.delete(
                    user,
                    subpath,
                    owner_override=team_id,
                    root_prefix="teams",
                )
                return

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to delete %s", path)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def grep(self, user: KeycloakUser, pattern: str, prefix: str = "") -> List[str]:
        try:
            resolved = self._resolve(prefix)
            if resolved.area == _Area.ROOT:
                matches: list[str] = []
                matches.extend(await self.scoped_storage.grep(user, pattern, ""))
                matches.extend(await self._grep_corpus_area(user, pattern, ()))
                return matches

            if resolved.area == _Area.USER:
                return await self.scoped_storage.grep(user, pattern, _join_segments(resolved.segments))

            if resolved.area == _Area.AGENT:
                if not resolved.segments:
                    return []
                agent_id, *sub = resolved.segments
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.READ,
                )
                return await self.scoped_storage.grep(
                    user,
                    pattern,
                    "/".join(sub) if sub else "",
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )

            if resolved.area == _Area.TEAM:
                if not resolved.segments:
                    return []
                team_id, *sub = resolved.segments
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_READ,
                )
                return await self.scoped_storage.grep(
                    user,
                    pattern,
                    "/".join(sub) if sub else "",
                    owner_override=team_id,
                    root_prefix="teams",
                )

            if resolved.area == _Area.CORPUS:
                return await self._grep_corpus_area(user, pattern, resolved.segments)

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Grep failed for pattern '%s' with prefix '%s'", pattern, prefix)
            raise

    @authorize(action=Action.READ, resource=Resource.FILES)
    async def print_root_dir(self, user: KeycloakUser) -> str:
        try:
            return "/"
        except Exception:
            logger.exception("Failed to get virtual FS root")
            raise

    @authorize(action=Action.CREATE, resource=Resource.FILES)
    async def mkdir(self, user: KeycloakUser, path: str) -> None:
        try:
            resolved = self._resolve(path)
            if resolved.area == _Area.ROOT:
                raise PermissionError("Cannot create root")
            if resolved.area == _Area.CORPUS:
                raise PermissionError("Corpus area is read-only")

            if resolved.area == _Area.USER:
                if not resolved.segments:
                    raise PermissionError("Cannot create /user root")
                await self.scoped_storage.mkdir(user, _join_segments(resolved.segments))
                return

            if resolved.area == _Area.AGENT:
                if len(resolved.segments) < 2:
                    raise PermissionError("Mkdir path must be /agent/<agent_id>/<dir>")
                agent_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_agent_permission(
                    user,
                    agent_id=agent_id,
                    permission=AgentPermission.UPDATE,
                )
                await self.scoped_storage.mkdir(
                    user,
                    subpath,
                    owner_override=f"{agent_id}/config",
                    root_prefix="agents",
                )
                return

            if resolved.area == _Area.TEAM:
                if len(resolved.segments) < 2:
                    raise PermissionError("Mkdir path must be /team/<team_id>/<dir>")
                team_id = resolved.segments[0]
                subpath = "/".join(resolved.segments[1:])
                await self._ensure_team_permission(
                    user,
                    team_id=team_id,
                    permission=TeamPermission.CAN_UPDATE_RESOURCES,
                )
                await self.scoped_storage.mkdir(
                    user,
                    subpath,
                    owner_override=team_id,
                    root_prefix="teams",
                )
                return

            raise FileNotFoundError("Unknown filesystem area")
        except Exception:
            logger.exception("Failed to create directory %s", path)
            raise
