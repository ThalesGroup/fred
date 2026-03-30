from __future__ import annotations

import json
import logging
import re
from typing import List

from fred_core import FilesystemResourceInfoResult, KeycloakUser

from knowledge_flow_backend.common.document_structures import DocumentMetadata
from knowledge_flow_backend.features.content.content_service import ContentService
from knowledge_flow_backend.features.metadata.service import MetadataService
from knowledge_flow_backend.features.tag.structure import TagType, TagWithPermissions
from knowledge_flow_backend.features.tag.tag_service import TagService

from .corpus_virtual_contract import (
    CORPUS_DOCUMENTS,
    CORPUS_LIBRARIES,
    corpus_display_label,
    corpus_tree_document_segments,
    extract_stable_id_from_display_segment,
    friendly_corpus_segment,
    split_corpus_folder_path,
)
from .virtual_fs_contract import AREA_CORPUS, dir_entry, file_entry, join_segments

logger = logging.getLogger(__name__)


class CorpusVirtualFilesystem:
    """
    Read-only virtual filesystem implementation for `/corpus`.

    Why this exists:
    - corpus storage is not a normal filesystem and must be rendered from tags,
      metadata, and previews
    - isolating corpus-specific behavior keeps the main filesystem router small

    How to use:
    - instantiate once with the metadata/content/tag services
    - call `list_area(...)`, `cat_area(...)`, `stat_area(...)`, and `grep_area(...)`
      with corpus-relative segments

    Example:
    - `await corpus_fs.list_area(user, ("CIR",))`
    """

    def __init__(
        self,
        *,
        metadata_service: MetadataService,
        content_service: ContentService,
        tag_service: TagService,
    ) -> None:
        """
        Store the services required to synthesize the corpus filesystem.

        Why this exists:
        - the virtual corpus tree is derived from metadata, content previews, and tags
        - constructor injection keeps the implementation easy to test in isolation

        How to use:
        - pass the already-configured backend services once at startup

        Example:
        - `CorpusVirtualFilesystem(metadata_service=..., content_service=..., tag_service=...)`
        """

        self.metadata_service = metadata_service
        self.content_service = content_service
        self.tag_service = tag_service

    async def _get_tag_for_user(self, user: KeycloakUser, tag_id: str):
        """
        Load one authorized tag for the current user.

        Why this exists:
        - most corpus helpers eventually need an authorized tag object
        - keeping the call in one helper avoids duplicating service access

        How to use:
        - pass the user plus one stable tag id

        Example:
        - `await _get_tag_for_user(user, "tag-1")`
        """

        return await self.tag_service.get_tag_for_user(tag_id, user)

    async def _list_documents_for_tag(self, user: KeycloakUser, tag_id: str) -> list[str]:
        """
        Return the stable document ids attached to one library tag.

        Why this exists:
        - library-scoped resolution needs a cheap membership check by uid
        - centralizing the lookup keeps document-in-library checks consistent

        How to use:
        - pass the user plus one resolved tag id

        Example:
        - `await _list_documents_for_tag(user, "tag-1")`
        """

        tag = await self._get_tag_for_user(user, tag_id)
        return sorted(set(tag.item_ids or []))

    async def _ensure_document_in_tag(self, user: KeycloakUser, tag_id: str, document_uid: str) -> None:
        """
        Ensure one document really belongs to the selected library tag.

        Why this exists:
        - legacy compatibility paths can name libraries and documents independently
        - reads should fail fast when a document does not belong to that library

        How to use:
        - call after resolving both the library tag id and the document uid

        Example:
        - `await _ensure_document_in_tag(user, "tag-1", "doc-9")`
        """

        doc_ids = await self._list_documents_for_tag(user, tag_id)
        if document_uid not in doc_ids:
            raise FileNotFoundError(f"Document {document_uid!r} is not in library {tag_id!r}.")

    async def _render_document_metadata_json(self, user: KeycloakUser, document_uid: str) -> str:
        """
        Render one document metadata payload as the visible `metadata.json` file.

        Why this exists:
        - corpus browsing should expose metadata like a normal file read
        - callers should not need to know the metadata service response model

        How to use:
        - pass the authorized user and one document uid

        Example:
        - `await _render_document_metadata_json(user, "doc-1")`
        """

        metadata = await self.metadata_service.get_document_metadata(user, document_uid)
        return json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2)

    async def _render_document_preview(self, user: KeycloakUser, document_uid: str) -> str:
        """
        Render one document preview as the visible `preview.md` file.

        Why this exists:
        - the corpus filesystem exposes preview content as a normal readable file
        - callers should not need to call the content service directly

        How to use:
        - pass the authorized user and one document uid

        Example:
        - `await _render_document_preview(user, "doc-1")`
        """

        return await self.content_service.get_markdown_preview(user, document_uid)

    async def _try_render_document_preview(self, user: KeycloakUser, document_uid: str) -> str | None:
        """
        Best-effort preview fetch for optional corpus flows.

        Why this exists:
        - one unreadable preview should not break corpus-wide listing or grep
        - returning `None` keeps fallback behavior explicit for callers

        How to use:
        - call when preview content is optional
        - check for `None` before using the result

        Example:
        - `await _try_render_document_preview(user, "doc-1")`
        """

        try:
            return await self._render_document_preview(user, document_uid)
        except Exception:
            logger.debug(
                "Skipping preview fetch for document_uid=%s during corpus helper flow",
                document_uid,
                exc_info=True,
            )
            return None

    async def _render_library_manifest_json(self, user: KeycloakUser, tag_id: str) -> str:
        """
        Render one library manifest payload as the legacy `manifest.json` file.

        Why this exists:
        - `/corpus/libraries/...` remains available for compatibility
        - the manifest file is the compact legacy summary for one library

        How to use:
        - pass the authorized user and one resolved tag id

        Example:
        - `await _render_library_manifest_json(user, "tag-1")`
        """

        tag = await self._get_tag_for_user(user, tag_id)
        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
        payload = {
            "library": {
                "id": tag.id,
                "name": tag.name,
                "full_path": tag.full_path,
                "display_path": friendly_corpus_segment(tag.full_path, tag.id),
                "type": tag.type.value,
            },
            "documents": [
                {
                    "document_uid": doc.document_uid,
                    "document_name": doc.document_name,
                    "display_path": friendly_corpus_segment(doc.document_name, doc.document_uid),
                    "mime_type": doc.file.mime_type,
                    "updated_at": doc.modified.isoformat() if doc.modified else None,
                }
                for doc in docs
            ],
            "count": len(docs),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    async def _list_corpus_tags(self, user: KeycloakUser) -> list[TagWithPermissions]:
        """
        Return readable document-library tags visible to one user.

        Why this exists:
        - corpus tree rendering and resolution both need the same authorized tag set
        - one helper avoids repeating the tag-service query everywhere

        How to use:
        - call from list, cat, stat, and grep flows

        Example:
        - `await _list_corpus_tags(user)`
        """

        return await self.tag_service.list_all_tags_for_user(
            user,
            tag_type=TagType.DOCUMENT,
            limit=10_000,
            offset=0,
        )

    async def _resolve_library_tag_id(self, user: KeycloakUser, segment: str) -> str:
        """
        Resolve one visible library segment back to a stable tag id.

        Why this exists:
        - compatibility paths may use friendly labels instead of raw ids
        - later reads still need the real tag id for metadata access

        How to use:
        - pass either a raw tag id or a friendly display segment

        Example:
        - `await _resolve_library_tag_id(user, "Policies [tag-1]")`
        """

        candidate_id = extract_stable_id_from_display_segment(segment) or segment.strip()
        try:
            tag = await self._get_tag_for_user(user, candidate_id)
            return tag.id
        except Exception:
            logger.debug(
                "Library segment %r did not resolve directly as tag_id=%r",
                segment,
                candidate_id,
                exc_info=True,
            )

        for tag in await self._list_corpus_tags(user):
            if segment in {
                tag.id,
                tag.name,
                tag.full_path,
                friendly_corpus_segment(tag.name, tag.id),
                friendly_corpus_segment(tag.full_path, tag.id),
            }:
                return tag.id
        raise FileNotFoundError(f"Unknown library segment {segment!r}.")

    async def _list_corpus_documents(self, user: KeycloakUser) -> list[DocumentMetadata]:
        """
        Return readable document metadata visible to one user.

        Why this exists:
        - natural browsing and legacy compatibility both need the same document set
        - sorting once keeps all directory output deterministic

        How to use:
        - call when you need all visible documents for the current user

        Example:
        - `await _list_corpus_documents(user)`
        """

        docs = await self.metadata_service.get_documents_metadata(user, {})
        return sorted(docs, key=lambda doc: doc.document_name.lower())

    async def _get_corpus_tree_tag(
        self,
        user: KeycloakUser,
        folder_segments: tuple[str, ...],
    ) -> TagWithPermissions | None:
        """
        Return the library tag that matches one natural corpus folder.

        Why this exists:
        - natural browsing is driven by tag full paths, not by storage folders
        - leaf folder reads need the exact tag when a folder maps to a real library

        How to use:
        - pass folder segments such as `("CIR", "TSN")`

        Example:
        - `await _get_corpus_tree_tag(user, ("CIR",))`
        """

        target_path = "/".join(folder_segments)
        for tag in await self._list_corpus_tags(user):
            if tag.full_path == target_path:
                return tag
        return None

    async def _list_corpus_tree_child_folder_names(
        self,
        user: KeycloakUser,
        folder_segments: tuple[str, ...],
    ) -> list[str]:
        """
        Return the direct child folder names of one natural corpus folder.

        Why this exists:
        - the corpus filesystem must expose tag hierarchy as real directories
        - list and stat flows need one shared source of truth for child folders

        How to use:
        - pass the current folder segments

        Example:
        - `await _list_corpus_tree_child_folder_names(user, ("CIR",))`
        """

        child_names: set[str] = set()
        prefix_length = len(folder_segments)
        for tag in await self._list_corpus_tags(user):
            parts = split_corpus_folder_path(tag.full_path)
            if parts[:prefix_length] != folder_segments or len(parts) <= prefix_length:
                continue
            child_names.add(parts[prefix_length])
        return sorted(child_names, key=str.lower)

    async def _list_corpus_tree_folder_documents(
        self,
        user: KeycloakUser,
        folder_segments: tuple[str, ...],
    ) -> list[DocumentMetadata]:
        """
        Return the documents that appear directly inside one natural corpus folder.

        Why this exists:
        - leaf library folders should show their documents in-place
        - root browsing also needs to expose readable unfiled documents

        How to use:
        - pass the current folder segments

        Example:
        - `await _list_corpus_tree_folder_documents(user, ("CIR", "TSN"))`
        """

        if not folder_segments:
            docs = await self._list_corpus_documents(user)
            authorized_tag_ids = {tag.id for tag in await self._list_corpus_tags(user)}
            return [doc for doc in docs if not authorized_tag_ids.intersection(set(doc.tags.tag_ids or []))]

        tag = await self._get_corpus_tree_tag(user, folder_segments)
        if tag is None:
            return []

        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag.id)
        return sorted(docs, key=lambda doc: doc.document_name.lower())

    async def _corpus_tree_folder_exists(
        self,
        user: KeycloakUser,
        folder_segments: tuple[str, ...],
    ) -> bool:
        """
        Tell whether one natural corpus folder exists.

        Why this exists:
        - the natural tree contains both real library folders and intermediate parents
        - list, stat, and cat need one consistent existence check

        How to use:
        - pass folder segments such as `("CIR", "TSN")`

        Example:
        - `await _corpus_tree_folder_exists(user, ("CIR",))`
        """

        if not folder_segments:
            return True
        if await self._get_corpus_tree_tag(user, folder_segments) is not None:
            return True
        child_names = await self._list_corpus_tree_child_folder_names(user, folder_segments)
        return bool(child_names)

    async def _resolve_corpus_tree_document_uid(
        self,
        user: KeycloakUser,
        folder_segments: tuple[str, ...],
        document_segment: str,
    ) -> str:
        """
        Resolve one visible document folder in the natural tree back to its uid.

        Why this exists:
        - natural corpus folders should show readable document names
        - reads and metadata access still need the stable document uid

        How to use:
        - pass the containing folder plus the displayed document segment

        Example:
        - `await _resolve_corpus_tree_document_uid(user, ("CIR",), "offer.docx")`
        """

        docs = await self._list_corpus_tree_folder_documents(user, folder_segments)
        child_folder_names = set(await self._list_corpus_tree_child_folder_names(user, folder_segments))
        document_segments = corpus_tree_document_segments(docs, sibling_folder_names=child_folder_names)

        candidate_uid = extract_stable_id_from_display_segment(document_segment)
        if candidate_uid:
            for doc in docs:
                if doc.document_uid == candidate_uid:
                    return doc.document_uid

        normalized_segment = document_segment.strip()
        for doc in docs:
            if normalized_segment in {
                doc.document_uid,
                doc.document_name,
                corpus_display_label(doc.document_name, fallback=doc.document_uid),
                document_segments[doc.document_uid],
            }:
                return doc.document_uid

        raise FileNotFoundError(f"Unknown document segment {document_segment!r} in folder {'/'.join(folder_segments)!r}.")

    async def _resolve_document_uid(self, user: KeycloakUser, segment: str) -> str:
        """
        Resolve one compatibility document segment back to its stable uid.

        Why this exists:
        - legacy `/corpus/documents/...` paths can use friendly labels or raw ids
        - later reads still need the stable document uid

        How to use:
        - pass either the raw uid or a friendly document segment

        Example:
        - `await _resolve_document_uid(user, "offer.pdf [doc-9]")`
        """

        candidate_uid = extract_stable_id_from_display_segment(segment) or segment.strip()
        try:
            metadata = await self.metadata_service.get_document_metadata(user, candidate_uid)
            return metadata.document_uid
        except Exception:
            logger.debug(
                "Document segment %r did not resolve directly as document_uid=%r",
                segment,
                candidate_uid,
                exc_info=True,
            )

        for doc in await self._list_corpus_documents(user):
            if segment in {
                doc.document_uid,
                doc.document_name,
                friendly_corpus_segment(doc.document_name, doc.document_uid),
            }:
                return doc.document_uid
        raise FileNotFoundError(f"Unknown document segment {segment!r}.")

    async def _resolve_document_uid_in_tag(self, user: KeycloakUser, tag_id: str, segment: str) -> str:
        """
        Resolve one library-scoped document segment back to its stable uid.

        Why this exists:
        - compatibility library paths expose friendly document names
        - later reads still need a stable document uid inside that library

        How to use:
        - pass the resolved tag id plus either a raw uid or a friendly segment

        Example:
        - `await _resolve_document_uid_in_tag(user, "tag-1", "offer.pdf [doc-9]")`
        """

        candidate_uid = extract_stable_id_from_display_segment(segment) or segment.strip()
        try:
            await self._ensure_document_in_tag(user, tag_id, candidate_uid)
            return candidate_uid
        except Exception:
            logger.debug(
                "Document segment %r did not resolve directly in library=%r as uid=%r",
                segment,
                tag_id,
                candidate_uid,
                exc_info=True,
            )

        docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
        for doc in docs:
            if segment in {
                doc.document_uid,
                doc.document_name,
                friendly_corpus_segment(doc.document_name, doc.document_uid),
            }:
                return doc.document_uid
        raise FileNotFoundError(f"Unknown document segment {segment!r} in library {tag_id!r}.")

    async def _list_natural_tree_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> List[FilesystemResourceInfoResult]:
        """
        List one natural corpus folder built from library tag paths.

        Why this exists:
        - users should browse corpus content through business folders, not storage ids
        - the corpus filesystem must mimic the library UI without changing storage

        How to use:
        - call with corpus-relative segments that do not start with legacy
          `libraries` or `documents`

        Example:
        - `await _list_natural_tree_area(user, ("CIR",))`
        """

        if not await self._corpus_tree_folder_exists(user, segments):
            if not segments:
                raise FileNotFoundError("Unknown corpus path")
            parent_segments = segments[:-1]
            if not await self._corpus_tree_folder_exists(user, parent_segments):
                raise FileNotFoundError("Unknown corpus path")
            document_uid = await self._resolve_corpus_tree_document_uid(user, parent_segments, segments[-1])
            await self.metadata_service.get_document_metadata(user, document_uid)
            return [file_entry("metadata.json", 0), file_entry("preview.md", 0)]

        child_folder_names = await self._list_corpus_tree_child_folder_names(user, segments)
        docs = await self._list_corpus_tree_folder_documents(user, segments)
        document_segments = corpus_tree_document_segments(docs, sibling_folder_names=set(child_folder_names))
        return [
            *[dir_entry(folder_name) for folder_name in child_folder_names],
            *[dir_entry(document_segments[doc.document_uid]) for doc in docs],
        ]

    async def list_area(
        self,
        user: KeycloakUser,
        segments: tuple[str, ...],
    ) -> List[FilesystemResourceInfoResult]:
        """
        List one corpus-relative virtual directory.

        Why this exists:
        - `/corpus` is synthesized from metadata, not backed by a real folder tree
        - callers still need standard directory listing behavior

        How to use:
        - pass corpus-relative segments such as `("CIR",)` or `("documents",)`
        - the result contains direct child files/directories only

        Example:
        - `await list_area(user, ("CIR",))`
        """

        if not segments or segments[0] not in {CORPUS_LIBRARIES, CORPUS_DOCUMENTS}:
            return await self._list_natural_tree_area(user, segments)

        head = segments[0]
        if head == CORPUS_LIBRARIES:
            if len(segments) == 1:
                tags = await self._list_corpus_tags(user)
                return [dir_entry(friendly_corpus_segment(tag.full_path, tag.id)) for tag in tags]

            tag_id = await self._resolve_library_tag_id(user, segments[1])
            if len(segments) == 2:
                await self._get_tag_for_user(user, tag_id)
                return [file_entry("manifest.json", 0), dir_entry(CORPUS_DOCUMENTS)]

            if len(segments) == 3 and segments[2] == CORPUS_DOCUMENTS:
                docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
                docs = sorted(docs, key=lambda doc: doc.document_name.lower())
                return [dir_entry(friendly_corpus_segment(doc.document_name, doc.document_uid)) for doc in docs]

            if len(segments) == 4 and segments[2] == CORPUS_DOCUMENTS:
                document_uid = await self._resolve_document_uid_in_tag(user, tag_id, segments[3])
                await self._ensure_document_in_tag(user, tag_id, document_uid)
                return [file_entry("metadata.json", 0), file_entry("preview.md", 0)]

            raise FileNotFoundError("Unknown corpus library path")

        if len(segments) == 1:
            docs = await self._list_corpus_documents(user)
            return [dir_entry(friendly_corpus_segment(doc.document_name, doc.document_uid)) for doc in docs]

        document_uid = await self._resolve_document_uid(user, segments[1])
        await self.metadata_service.get_document_metadata(user, document_uid)
        if len(segments) == 2:
            return [file_entry("metadata.json", 0), file_entry("preview.md", 0)]
        raise FileNotFoundError("Unknown corpus document path")

    async def cat_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> str:
        """
        Read one corpus-relative virtual file.

        Why this exists:
        - visible corpus paths may map to rendered metadata or preview files
        - callers should not need to know the underlying metadata/content services

        How to use:
        - pass corpus-relative segments ending in `metadata.json`, `preview.md`,
          or legacy `manifest.json`

        Example:
        - `await cat_area(user, ("CIR", "offer.docx", "preview.md"))`
        """

        if len(segments) < 3:
            raise FileNotFoundError("Corpus file path is incomplete")

        if segments[0] not in {CORPUS_LIBRARIES, CORPUS_DOCUMENTS}:
            folder_segments = segments[:-2]
            document_segment = segments[-2]
            file_name = segments[-1]
            if not await self._corpus_tree_folder_exists(user, folder_segments):
                raise FileNotFoundError("Unknown natural corpus folder path")
            document_uid = await self._resolve_corpus_tree_document_uid(user, folder_segments, document_segment)
            if file_name == "metadata.json":
                return await self._render_document_metadata_json(user, document_uid)
            if file_name == "preview.md":
                return await self._render_document_preview(user, document_uid)
            raise FileNotFoundError("Unknown corpus document file")

        if segments[0] == CORPUS_DOCUMENTS and len(segments) == 3:
            document_uid = await self._resolve_document_uid(user, segments[1])
            file_name = segments[2]
            if file_name == "metadata.json":
                return await self._render_document_metadata_json(user, document_uid)
            if file_name == "preview.md":
                return await self._render_document_preview(user, document_uid)
            raise FileNotFoundError("Unknown corpus document file")

        if len(segments) == 5 and segments[0] == CORPUS_LIBRARIES and segments[2] == CORPUS_DOCUMENTS:
            tag_id = await self._resolve_library_tag_id(user, segments[1])
            document_uid = await self._resolve_document_uid_in_tag(user, tag_id, segments[3])
            await self._ensure_document_in_tag(user, tag_id, document_uid)
            file_name = segments[4]
            if file_name == "metadata.json":
                return await self._render_document_metadata_json(user, document_uid)
            if file_name == "preview.md":
                return await self._render_document_preview(user, document_uid)
            raise FileNotFoundError("Unknown corpus library document file")

        if len(segments) == 3 and segments[0] == CORPUS_LIBRARIES and segments[2] == "manifest.json":
            tag_id = await self._resolve_library_tag_id(user, segments[1])
            return await self._render_library_manifest_json(user, tag_id)

        raise FileNotFoundError("Unknown corpus file path")

    async def stat_area(self, user: KeycloakUser, segments: tuple[str, ...]) -> FilesystemResourceInfoResult:
        """
        Stat one corpus-relative virtual path.

        Why this exists:
        - corpus paths may be synthetic directories or synthetic files
        - callers still expect a normal file-or-directory stat answer

        How to use:
        - pass corpus-relative segments from a visible `/corpus/...` path

        Example:
        - `await stat_area(user, ("CIR", "offer.docx"))`
        """

        if not segments:
            return dir_entry(AREA_CORPUS)
        try:
            await self.list_area(user, segments)
            return dir_entry(join_segments(segments))
        except FileNotFoundError:
            content = await self.cat_area(user, segments)
            return file_entry(join_segments(segments), len(content.encode("utf-8")))

    async def grep_area(
        self,
        user: KeycloakUser,
        pattern: str,
        segments: tuple[str, ...],
    ) -> List[str]:
        """
        Search corpus previews and return visible corpus paths.

        Why this exists:
        - `/corpus` is not backed by a real searchable directory tree
        - grep still needs to return paths the user can navigate directly

        How to use:
        - pass a regex pattern plus an optional corpus-relative prefix

        Example:
        - `await grep_area(user, "invoice", ("CIR",))`
        """

        regex = re.compile(pattern)
        matches: list[str] = []

        if not segments or segments[0] not in {CORPUS_LIBRARIES, CORPUS_DOCUMENTS}:
            if await self._corpus_tree_folder_exists(user, segments):
                child_folder_names = set(await self._list_corpus_tree_child_folder_names(user, segments))
                docs = await self._list_corpus_tree_folder_documents(user, segments)
                document_segments = corpus_tree_document_segments(docs, sibling_folder_names=child_folder_names)

                for doc in docs:
                    text = await self._try_render_document_preview(user, doc.document_uid)
                    if text is None or not regex.search(text):
                        continue
                    natural_path = "/".join((*segments, document_segments[doc.document_uid], "preview.md"))
                    matches.append(f"{AREA_CORPUS}/{natural_path}")

                for child_name in await self._list_corpus_tree_child_folder_names(user, segments):
                    matches.extend(await self.grep_area(user, pattern, (*segments, child_name)))
                return matches

            parent_segments = segments[:-1]
            if segments and await self._corpus_tree_folder_exists(user, parent_segments):
                try:
                    document_uid = await self._resolve_corpus_tree_document_uid(user, parent_segments, segments[-1])
                except FileNotFoundError:
                    return []
                text = await self._render_document_preview(user, document_uid)
                if regex.search(text):
                    return [f"{AREA_CORPUS}/{'/'.join((*segments, 'preview.md'))}"]
                return []

        if len(segments) == 1 and segments[0] == CORPUS_DOCUMENTS:
            docs = await self._list_corpus_documents(user)
            for doc in docs:
                text = await self._try_render_document_preview(user, doc.document_uid)
                if text is None:
                    continue
                if regex.search(text):
                    matches.append(f"{AREA_CORPUS}/{CORPUS_DOCUMENTS}/{friendly_corpus_segment(doc.document_name, doc.document_uid)}/preview.md")
            return matches

        if len(segments) == 1 and segments[0] == CORPUS_LIBRARIES:
            for tag in await self._list_corpus_tags(user):
                docs = await self.metadata_service.get_document_metadata_in_tag(user, tag.id)
                for doc in docs:
                    text = await self._try_render_document_preview(user, doc.document_uid)
                    if text is None:
                        continue
                    if regex.search(text):
                        matches.append(
                            f"{AREA_CORPUS}/{CORPUS_LIBRARIES}/"
                            f"{friendly_corpus_segment(tag.full_path, tag.id)}/"
                            f"{CORPUS_DOCUMENTS}/"
                            f"{friendly_corpus_segment(doc.document_name, doc.document_uid)}/preview.md"
                        )
            return matches

        if len(segments) == 2 and segments[0] == CORPUS_DOCUMENTS:
            document_uid = await self._resolve_document_uid(user, segments[1])
            metadata = await self.metadata_service.get_document_metadata(user, document_uid)
            text = await self._render_document_preview(user, document_uid)
            if regex.search(text):
                matches.append(f"{AREA_CORPUS}/{CORPUS_DOCUMENTS}/{friendly_corpus_segment(metadata.document_name, metadata.document_uid)}/preview.md")
            return matches

        if len(segments) == 2 and segments[0] == CORPUS_LIBRARIES:
            tag_id = await self._resolve_library_tag_id(user, segments[1])
            tag = await self._get_tag_for_user(user, tag_id)
            docs = await self.metadata_service.get_document_metadata_in_tag(user, tag_id)
            for doc in docs:
                text = await self._try_render_document_preview(user, doc.document_uid)
                if text is None:
                    continue
                if regex.search(text):
                    matches.append(
                        f"{AREA_CORPUS}/{CORPUS_LIBRARIES}/"
                        f"{friendly_corpus_segment(tag.full_path, tag.id)}/"
                        f"{CORPUS_DOCUMENTS}/"
                        f"{friendly_corpus_segment(doc.document_name, doc.document_uid)}/preview.md"
                    )
            return matches

        try:
            content = await self.cat_area(user, segments)
        except Exception:
            return []
        if regex.search(content):
            matches.append(f"{AREA_CORPUS}/{join_segments(segments)}")
        return matches
