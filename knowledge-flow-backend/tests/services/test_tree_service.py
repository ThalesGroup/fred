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

import pytest
from fred_core import KeycloakUser

from knowledge_flow_backend.common.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
)
from knowledge_flow_backend.features.tag.structure import Tag, TagType, TagWithItemsId
from knowledge_flow_backend.features.tree.service import TreeService
from knowledge_flow_backend.features.tree.structure import DocumentTreeRequest


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", email="tester@example.com", roles=["admin"], groups=["admins"])


def _document(*, uid: str, name: str, tag_ids: list[str]) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="text/plain"),
        processing=Processing(),
        tags={"tag_ids": tag_ids, "tag_names": []},
    )


def _library(*, tag_id: str, name: str, path: str | None = None, item_ids: list[str] | None = None) -> TagWithItemsId:
    return TagWithItemsId.from_tag(
        Tag(
            id=tag_id,
            created_at="2026-03-21T00:00:00Z",
            updated_at="2026-03-21T00:00:00Z",
            owner_id="u-1",
            name=name,
            path=path,
            description=None,
            type=TagType.DOCUMENT,
        ),
        item_ids=item_ids or [],
    )


class _TagServiceStub:
    def __init__(self, tags: list[TagWithItemsId]) -> None:
        self._tags = tags

    async def list_all_tags_for_user(self, user, tag_type=None, path_prefix=None, limit=10000, offset=0):
        del user, tag_type, limit, offset
        if not path_prefix:
            return list(self._tags)
        return [t for t in self._tags if t.full_path == path_prefix or t.full_path.startswith(path_prefix + "/")]


class _MetadataServiceStub:
    def __init__(self, docs: list[DocumentMetadata]) -> None:
        self._by_uid = {doc.document_uid: doc for doc in docs}

    async def get_documents_metadata(self, user, filters_dict):
        del user
        uids = filters_dict.get("document_uid", [])
        return [self._by_uid[u].model_copy(deep=True) for u in uids if u in self._by_uid]


def _tree_service(*, tags: list[TagWithItemsId], docs: list[DocumentMetadata]) -> TreeService:
    service = TreeService.__new__(TreeService)  # bypass __init__ (no ApplicationContext needed)
    service.tag_service = _TagServiceStub(tags)
    service.metadata_service = _MetadataServiceStub(docs)
    return service


@pytest.mark.asyncio
async def test_tree_lists_nested_folders_from_root():
    library = _library(tag_id="tag-1", name="HR", path="Sales", item_ids=["doc-1"])
    document = _document(uid="doc-1", name="Onboarding.pdf", tag_ids=["tag-1"])
    service = _tree_service(tags=[library], docs=[document])

    result = await service.get_tree(_user(), DocumentTreeRequest())

    assert not result.truncated
    assert "Sales/" in result.tree
    assert "HR/" in result.tree
    assert "Onboarding.pdf" in result.tree
    assert "[doc-1]" in result.tree  # uid must be present so callers can target summarize_document/search


@pytest.mark.asyncio
async def test_working_directory_narrows_to_subtree():
    sales_hr = _library(tag_id="tag-1", name="HR", path="Sales", item_ids=["doc-1"])
    sales_legal = _library(tag_id="tag-2", name="Legal", path="Sales", item_ids=["doc-2"])
    docs = [
        _document(uid="doc-1", name="Onboarding.pdf", tag_ids=["tag-1"]),
        _document(uid="doc-2", name="Contract.pdf", tag_ids=["tag-2"]),
    ]
    service = _tree_service(tags=[sales_hr, sales_legal], docs=docs)

    result = await service.get_tree(_user(), DocumentTreeRequest(working_directory="Sales/HR"))

    assert "Onboarding.pdf" in result.tree
    assert "Contract.pdf" not in result.tree


@pytest.mark.asyncio
async def test_tag_ids_scope_restricts_to_descendants_only():
    sales_hr = _library(tag_id="tag-1", name="HR", path="Sales", item_ids=["doc-1"])
    other = _library(tag_id="tag-2", name="Other", path=None, item_ids=["doc-2"])
    docs = [
        _document(uid="doc-1", name="Onboarding.pdf", tag_ids=["tag-1"]),
        _document(uid="doc-2", name="Unrelated.pdf", tag_ids=["tag-2"]),
    ]
    service = _tree_service(tags=[sales_hr, other], docs=docs)

    result = await service.get_tree(_user(), DocumentTreeRequest(tag_ids=["tag-1"]))

    assert "Onboarding.pdf" in result.tree
    assert "Unrelated.pdf" not in result.tree


@pytest.mark.asyncio
async def test_unknown_working_directory_yields_empty_tree():
    service = _tree_service(tags=[], docs=[])

    result = await service.get_tree(_user(), DocumentTreeRequest(working_directory="Nonexistent"))

    assert result.tree == "(empty)"
    assert not result.truncated
