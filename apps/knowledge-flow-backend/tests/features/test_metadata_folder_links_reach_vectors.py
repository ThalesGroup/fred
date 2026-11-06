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

"""Linking or unlinking an indexed document must reach the folder ids its chunks
carry, since search pre-filters on them, and a failed index write must abort the
membership change instead of reporting success."""

from __future__ import annotations

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    ProcessingStage,
    ProcessingStatus,
    SourceInfo,
    SourceType,
    Tagging,
)
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document

from knowledge_flow_backend.core.stores.vector.base_vector_store import CHUNK_ID_FIELD, SearchFilter
from knowledge_flow_backend.core.stores.vector.in_memory_langchain_vector_store import InMemoryLangchainVectorStore
from knowledge_flow_backend.features.metadata.service import MetadataService, MetadataUpdateError

USER = KeycloakUser(uid="u-1", username="tester", email="tester@example.com", roles=["admin"])


def _document(tag_ids: list[str], *, vectorized: bool = True) -> DocumentMetadata:
    stages = {ProcessingStage.VECTORIZED: ProcessingStatus.DONE} if vectorized else {}
    return DocumentMetadata(
        identity=Identity(document_name="report.pdf", document_uid="doc-1"),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="application/pdf"),
        processing=Processing(stages=stages),
        tags=Tagging(tag_ids=list(tag_ids)),
    )


class _Rebac:
    def __init__(self) -> None:
        self.parents: list[tuple[str, str]] = []

    async def check_user_permission_or_raise(self, user, permission, resource_id, consistency_token=None) -> None:
        return None


class _MetadataStore:
    def __init__(self) -> None:
        self.saved: list[list[str]] = []

    async def save_metadata(self, metadata: DocumentMetadata, session=None) -> None:
        self.saved.append(list(metadata.tags.tag_ids))


class _FailingVectorStore:
    def set_document_tag_ids(self, *, document_uid, tag_ids) -> None:
        raise RuntimeError("index unavailable")


def _indexed_store(tag_ids: list[str]) -> InMemoryLangchainVectorStore:
    store = InMemoryLangchainVectorStore(embedding_model=FakeEmbeddings(size=8), embedding_model_name="fake")
    store.add_documents([Document(page_content="quarterly report", metadata={CHUNK_ID_FIELD: "doc-1::chunk::0", "document_uid": "doc-1", "tag_ids": tag_ids})])
    return store


def _service(vector_store) -> tuple[MetadataService, _MetadataStore, _Rebac]:
    service = object.__new__(MetadataService)
    store, rebac = _MetadataStore(), _Rebac()
    service.metadata_store = store
    service.rebac = rebac
    service.vector_store = vector_store
    service.content_store = None

    async def _add_parent(tag_id, document_uid, actor_uid=None):
        rebac.parents.append(("add", tag_id))

    async def _remove_parent(tag_id, document_uid):
        rebac.parents.append(("remove", tag_id))

    service._set_tag_as_parent_in_rebac = _add_parent
    service._remove_tag_as_parent_in_rebac = _remove_parent
    return service, store, rebac


def _found_in(store: InMemoryLangchainVectorStore, tag_id: str) -> bool:
    return bool(store.ann_search("report", k=5, search_filter=SearchFilter(tag_ids=[tag_id])))


@pytest.mark.asyncio
async def test_linking_an_indexed_document_makes_it_searchable_from_the_new_folder():
    vectors = _indexed_store(["alpha"])
    service, store, _ = _service(vectors)

    await service.add_tag_id_to_document(USER, _document(["alpha"]), "beta")

    assert store.saved == [["alpha", "beta"]]
    assert _found_in(vectors, "beta") and _found_in(vectors, "alpha")


@pytest.mark.asyncio
async def test_unlinking_an_indexed_document_keeps_it_only_in_its_remaining_folders():
    vectors = _indexed_store(["alpha", "beta"])
    service, store, _ = _service(vectors)

    await service.remove_tag_id_from_document(USER, _document(["alpha", "beta"]), "alpha")

    assert store.saved == [["beta"]]
    assert _found_in(vectors, "beta") and not _found_in(vectors, "alpha")


@pytest.mark.asyncio
async def test_a_failed_index_write_aborts_the_link():
    service, store, rebac = _service(_FailingVectorStore())
    document = _document(["alpha"])

    with pytest.raises(MetadataUpdateError):
        await service.add_tag_id_to_document(USER, document, "beta")

    assert store.saved == [] and rebac.parents == []
    assert document.tags.tag_ids == ["alpha"]


@pytest.mark.asyncio
async def test_a_failed_index_write_aborts_the_unlink():
    service, store, rebac = _service(_FailingVectorStore())

    with pytest.raises(MetadataUpdateError):
        await service.remove_tag_id_from_document(USER, _document(["alpha", "beta"]), "alpha")

    assert store.saved == [] and rebac.parents == []


@pytest.mark.asyncio
async def test_a_document_without_vectors_is_linked_without_touching_the_index():
    service, store, _ = _service(_FailingVectorStore())

    await service.add_tag_id_to_document(USER, _document(["alpha"], vectorized=False), "beta")

    assert store.saved == [["alpha", "beta"]]
