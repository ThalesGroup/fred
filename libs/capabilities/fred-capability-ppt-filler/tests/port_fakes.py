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

"""In-memory fakes of the ``RuntimeServices`` ports the ppt_filler capability uses.

These implement the SDK ABC ports (``AgentAssetPort``, ``WorkspaceFsPort``,
``DocumentContentPort``, ``DocumentFolderPort``) with dict-backed storage so the
save-time (`validate_config`) and chat-time (fill) code runs fully offline: no
network, no real Knowledge Flow, no ApplicationContext.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from fred_sdk.contracts.context import PublishedArtifact
from fred_sdk.contracts.runtime import (
    AgentAssetPort,
    DocumentContentPort,
    DocumentFolderPort,
    DocumentRawContent,
    FolderDocumentEntry,
    WorkspaceFsPort,
)


class FakeAssets(AgentAssetPort):
    """Dict-backed ``AgentAssetPort``: fetch returns stored bytes; store records."""

    def __init__(self, blobs: Optional[Dict[str, bytes]] = None) -> None:
        self.blobs: Dict[str, bytes] = dict(blobs or {})
        self.store_calls: List[dict] = []
        self.delete_calls: List[str] = []

    async def store(
        self,
        key: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,
        filename: Optional[str] = None,
    ) -> str:
        self.store_calls.append(
            {
                "key": key,
                "content": bytes(content),
                "content_type": content_type,
                "filename": filename,
            }
        )
        self.blobs[key] = bytes(content)
        return key

    async def fetch(self, key: str) -> bytes:
        if key not in self.blobs:
            raise FileNotFoundError(f"no such asset: {key}")
        return self.blobs[key]

    async def delete(self, key: str) -> None:
        self.delete_calls.append(key)
        self.blobs.pop(key, None)


class FakeWorkspace(WorkspaceFsPort):
    """``WorkspaceFsPort`` whose ``write`` records bytes and mints a durable href.

    Only ``write`` is functional (the fill tool's single workspace need); every
    other abstract method raises so an accidental use is loud, not silent.
    """

    def __init__(self) -> None:
        self.writes: List[dict] = []

    def bind(self, binding) -> None:  # pragma: no cover - not exercised
        raise NotImplementedError

    async def read_bytes(self, path: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def read_text(self, path: str) -> str:  # pragma: no cover
        raise NotImplementedError

    async def read_user_bytes(self, path: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def read_team_bytes(self, path: str) -> bytes:  # pragma: no cover
        raise NotImplementedError

    async def write(
        self,
        path: str,
        content: bytes,
        *,
        content_type: Optional[str] = None,
        title: Optional[str] = None,
    ) -> PublishedArtifact:
        file_name = path.split("/")[-1]
        self.writes.append(
            {
                "path": path,
                "content": bytes(content),
                "content_type": content_type,
                "title": title,
            }
        )
        return PublishedArtifact(
            key=path,
            file_name=file_name,
            size=len(content),
            href=f"/fs/download/{path}",
            document_uid=f"uid-{path}",
            mime=content_type,
        )

    async def ls(self, path: str = "") -> list:  # pragma: no cover
        raise NotImplementedError

    async def delete(self, path: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def link_for(self, path: str) -> PublishedArtifact:  # pragma: no cover
        raise NotImplementedError


class FakeDocs(DocumentContentPort):
    """``DocumentContentPort`` serving configured raw bytes for a uid; records uids."""

    def __init__(self, docs: Optional[Dict[str, Tuple[bytes, str]]] = None) -> None:
        # {document_uid: (bytes, content_type)}
        self.docs: Dict[str, Tuple[bytes, str]] = dict(docs or {})
        self.fetch_uids: List[str] = []

    async def fetch_raw(self, document_uid: str) -> DocumentRawContent:
        self.fetch_uids.append(document_uid)
        if document_uid not in self.docs:
            raise RuntimeError(f"no such document: {document_uid}")
        content, content_type = self.docs[document_uid]
        return DocumentRawContent(
            content=content,
            content_type=content_type,
            filename=f"{document_uid}.bin",
        )


class FakeFolders(DocumentFolderPort):
    """``DocumentFolderPort`` over a folder->tag map and a tag->[(uid, name)] listing."""

    def __init__(
        self,
        folder_to_tag: Optional[Dict[str, str]] = None,
        tag_to_docs: Optional[Dict[str, List[Tuple[str, str]]]] = None,
    ) -> None:
        self.folder_to_tag: Dict[str, str] = dict(folder_to_tag or {})
        self.tag_to_docs: Dict[str, List[Tuple[str, str]]] = dict(tag_to_docs or {})
        self.resolve_calls: List[str] = []
        self.list_calls: List[str] = []

    async def resolve_folder(self, folder: str) -> Optional[str]:
        self.resolve_calls.append(folder)
        return self.folder_to_tag.get(folder)

    async def list_folder_documents(
        self, folder_tag_id: str
    ) -> Tuple[FolderDocumentEntry, ...]:
        self.list_calls.append(folder_tag_id)
        return tuple(
            FolderDocumentEntry(document_uid=uid, document_name=name)
            for uid, name in self.tag_to_docs.get(folder_tag_id, [])
        )
