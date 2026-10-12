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

import asyncio
import json
import threading
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fred_core import KeycloakUser
from fred_core.documents.document_structures import (
    DocumentMetadata,
    FileInfo,
    Identity,
    Processing,
    SourceInfo,
    SourceType,
)

from knowledge_flow_backend.features.corpus_tree.service import CorpusTreeService
from knowledge_flow_backend.features.corpus_tree.structure import DocumentTreeRequest


def _user() -> KeycloakUser:
    return KeycloakUser(uid="u-1", username="tester", email="tester@example.com", roles=["admin"])


def _document(*, uid: str, name: str) -> DocumentMetadata:
    return DocumentMetadata(
        identity=Identity(document_name=name, document_uid=uid, created=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        source=SourceInfo(source_type=SourceType.PUSH, source_tag="uploads"),
        file=FileInfo(mime_type="text/plain"),
        processing=Processing(),
        tags={"tag_ids": [], "tag_names": []},
    )


def _tag(*, tag_id: str, full_path: str, item_ids: list[str]) -> SimpleNamespace:
    """Lightweight tag double — CorpusTreeService only ever reads `.id`/`.full_path`/`.item_ids`."""

    return SimpleNamespace(id=tag_id, full_path=full_path, item_ids=item_ids)


class _TagServiceStub:
    def __init__(self, tags: list[SimpleNamespace]) -> None:
        self._tags = tags

    async def list_all_tags_for_user(self, user, tag_type=None, path_prefix=None, limit=200, offset=0, owner_filter=None, team_id=None):
        del user, tag_type, path_prefix, limit, offset, owner_filter, team_id
        return list(self._tags)


class _MetadataServiceStub:
    def __init__(self, docs: list[DocumentMetadata]) -> None:
        self._docs = docs

    async def get_documents_by_uids(self, user, document_uids: list[str]):
        del user
        wanted = set(document_uids)
        return [doc.model_copy(deep=True) for doc in self._docs if doc.document_uid in wanted]


def _tree_service(*, tags: list[SimpleNamespace], docs: list[DocumentMetadata]) -> CorpusTreeService:
    service = CorpusTreeService.__new__(CorpusTreeService)
    service.tag_service = _TagServiceStub(tags)
    service.metadata_service = _MetadataServiceStub(docs)
    return service


@pytest.mark.asyncio
async def test_renders_every_document_under_its_folder():
    tag = _tag(tag_id="tag-1", full_path="Sales", item_ids=["doc-1", "doc-2"])
    docs = [
        _document(uid="doc-1", name="Architecture.docx"),
        _document(uid="doc-2", name="Budget.xlsx"),
    ]
    service = _tree_service(tags=[tag], docs=docs)

    response = await service.get_tree(_user(), DocumentTreeRequest())

    assert '"folder":"Sales","folder_id":"tag-1"' in response.tree
    assert "Architecture.docx" in response.tree
    assert "Budget.xlsx" in response.tree


@pytest.mark.asyncio
async def test_tag_ids_narrows_the_listing_to_the_allowed_folder_and_its_descendants():
    sales = _tag(tag_id="tag-1", full_path="Sales", item_ids=["doc-1"])
    hr = _tag(tag_id="tag-2", full_path="HR", item_ids=["doc-2"])
    docs = [
        _document(uid="doc-1", name="Architecture.docx"),
        _document(uid="doc-2", name="Onboarding.docx"),
    ]
    service = _tree_service(tags=[sales, hr], docs=docs)

    response = await service.get_tree(_user(), DocumentTreeRequest(tag_ids=["tag-1"]))

    assert "Architecture.docx" in response.tree
    assert "HR" not in response.tree
    assert "Onboarding.docx" not in response.tree


@pytest.mark.asyncio
async def test_empty_scope_returns_canonical_empty_tree():
    service = _tree_service(tags=[], docs=[])

    response = await service.get_tree(_user(), DocumentTreeRequest())

    assert response.tree == "(empty)"
    assert response.truncated is False


@pytest.mark.asyncio
async def test_document_uids_narrows_the_listing_to_the_selected_leaves():
    sales = _tag(tag_id="tag-1", full_path="Sales", item_ids=["doc-1", "doc-2"])
    hr = _tag(tag_id="tag-2", full_path="HR", item_ids=["doc-3"])
    docs = [
        _document(uid="doc-1", name="Architecture.docx"),
        _document(uid="doc-2", name="Budget.xlsx"),
        _document(uid="doc-3", name="Onboarding.docx"),
    ]
    service = _tree_service(tags=[sales, hr], docs=docs)

    response = await service.get_tree(_user(), DocumentTreeRequest(document_uids=["doc-2"]))

    assert "Budget.xlsx" in response.tree
    assert "Architecture.docx" not in response.tree
    # The folder holding nothing selected is pruned, not rendered empty.
    assert "HR" not in response.tree


@pytest.mark.asyncio
async def test_library_scope_and_document_scope_union_rather_than_intersect():
    sales = _tag(tag_id="tag-1", full_path="Sales", item_ids=["doc-1"])
    hr = _tag(tag_id="tag-2", full_path="HR", item_ids=["doc-2", "doc-3"])
    docs = [
        _document(uid="doc-1", name="Architecture.docx"),
        _document(uid="doc-2", name="Onboarding.docx"),
        _document(uid="doc-3", name="Payroll.xlsx"),
    ]
    service = _tree_service(tags=[sales, hr], docs=docs)

    response = await service.get_tree(_user(), DocumentTreeRequest(tag_ids=["tag-1"], document_uids=["doc-2"]))

    # The whole selected library, plus the separately named document.
    assert "Architecture.docx" in response.tree
    assert "Onboarding.docx" in response.tree
    assert "Payroll.xlsx" not in response.tree


@pytest.mark.asyncio
async def test_a_folder_with_no_document_still_renders_without_a_document_scope():
    empty = _tag(tag_id="tag-1", full_path="Archive", item_ids=[])
    service = _tree_service(tags=[empty], docs=[])

    response = await service.get_tree(_user(), DocumentTreeRequest())

    assert '"folder":"Archive","folder_id":"tag-1"' in response.tree


@pytest.mark.asyncio
async def test_selecting_a_folder_and_its_documents_lists_each_one_once():
    """Ticking a folder and the files inside it is redundant, not duplicating:
    the union collapses to the same set and every leaf renders once."""

    sales = _tag(tag_id="tag-1", full_path="Sales", item_ids=["doc-1", "doc-2"])
    docs = [
        _document(uid="doc-1", name="Architecture.docx"),
        _document(uid="doc-2", name="Budget.xlsx"),
    ]
    service = _tree_service(tags=[sales], docs=docs)

    response = await service.get_tree(_user(), DocumentTreeRequest(tag_ids=["tag-1"], document_uids=["doc-1", "doc-2"]))

    assert response.tree.count("Architecture.docx") == 1
    assert response.tree.count("Budget.xlsx") == 1
    assert response.tree.count('"folder":"Sales","folder_id":"tag-1"') == 1


def _records(tree: str) -> list[dict]:
    records = [json.loads(line) for line in tree.splitlines() if line.lstrip().startswith("{")]
    return [record for record in records if "uid" in record]


@pytest.mark.asyncio
async def test_projects_arrival_and_descriptive_metadata_without_confusing_file_creation():
    early = _document(uid="early", name="Early.pdf")
    late = _document(uid="late", name="Late.pdf")
    early.identity.created = datetime(2026, 10, 10, tzinfo=timezone.utc)
    late.identity.created = datetime(2020, 1, 1, tzinfo=timezone.utc)
    early.source.date_added_to_kb = datetime(2026, 10, 12, 8, tzinfo=timezone.utc)
    late.source.date_added_to_kb = datetime(2026, 10, 12, 9, tzinfo=timezone.utc)
    late.identity.title = "Platform design"
    late.identity.modified = datetime(2026, 10, 11, tzinfo=timezone.utc)
    late.file.language = "fr"
    late.file.page_count = 24
    late.labels = ["Architecture"]
    service = _tree_service(tags=[_tag(tag_id="docs", full_path="Docs", item_ids=["early", "late", "denied"])], docs=[early, late])
    response = await service.get_tree(_user(), DocumentTreeRequest())
    records = {record["uid"]: record for record in _records(response.tree)}
    assert set(records) == {"early", "late"}
    assert records["early"]["created"] > records["late"]["created"]
    assert records["early"]["added_to_kb"] < records["late"]["added_to_kb"]
    assert records["late"]["modified"] == "2026-10-11T00:00:00+00:00"
    assert records["late"]["title"] == "Platform design"
    assert records["late"]["language"] == "fr"
    assert records["late"]["page_count"] == 24
    assert records["late"]["labels"] == ["Architecture"]
    assert records["late"]["source"] == "uploads"
    scoped = await service.get_tree(_user(), DocumentTreeRequest(document_uids=["early"]))
    assert "Platform design" not in scoped.tree
    assert "Architecture" not in scoped.tree


@pytest.mark.asyncio
async def test_missing_stored_arrival_stays_unknown():
    doc = _document(uid="legacy", name="Legacy.pdf")
    assert "date_added_to_kb" not in doc.source.model_fields_set
    service = _tree_service(tags=[_tag(tag_id="docs", full_path="Docs", item_ids=["legacy"])], docs=[doc])
    response = await service.get_tree(_user(), DocumentTreeRequest())
    assert _records(response.tree)[0]["added_to_kb"] is None


@pytest.mark.asyncio
async def test_rendering_does_not_block_the_request_event_loop(monkeypatch):
    from knowledge_flow_backend.features.corpus_tree import service as module

    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    original = module.render_tree

    def render(root, *, max_chars):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(timeout=1), "the event loop could not release the renderer"
        return original(root, max_chars=max_chars)

    monkeypatch.setattr(module, "render_tree", render)
    service = _tree_service(tags=[], docs=[])
    request = asyncio.create_task(service.get_tree(_user(), DocumentTreeRequest()))
    try:
        await asyncio.wait_for(started.wait(), timeout=0.5)
        release.set()
        assert (await request).tree == "(empty)"
    finally:
        release.set()
        await asyncio.gather(request)


@pytest.mark.asyncio
async def test_metadata_rich_tree_fits_the_raised_default_budget():
    docs = [_document(uid=f"doc-{i}", name=f"Document-{i:03d}.pdf") for i in range(50)]
    service = _tree_service(tags=[_tag(tag_id="tag", full_path="Docs", item_ids=[doc.document_uid for doc in docs])], docs=docs)
    response = await service.get_tree(_user(), DocumentTreeRequest())
    assert 6000 < len(response.tree) <= 20_000
    assert not response.truncated
    assert all(f'"uid":"doc-{i}"' in response.tree for i in range(50))
    limited = await service.get_tree(_user(), DocumentTreeRequest(max_chars=6000))
    assert limited.truncated
    assert len(limited.tree) <= 6000
