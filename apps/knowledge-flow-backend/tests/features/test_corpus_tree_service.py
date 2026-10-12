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


@pytest.mark.asyncio
async def test_paged_tree_continues_before_budget_omissions_and_deduplicates():
    from fred_core.documents.document_store import BaseDocumentMetadataStore
    from pydantic import ValidationError

    from knowledge_flow_backend.features.corpus_tree.service import InvalidTreePage

    docs = [_document(uid=str(i), name=f"Report-{i}.pdf") for i in range(6)]
    for doc in docs:
        doc.tags.tag_ids = ["a", "b"]
    tags = [_tag(tag_id="a", full_path="A", item_ids=[]), _tag(tag_id="b", full_path="B", item_ids=[])]
    service = _tree_service(tags=tags, docs=docs)

    class Store(BaseDocumentMetadataStore):
        async def get_all_metadata(self, filters, session=None):
            return docs

    async def descriptors(*args, **kwargs):
        return tags

    async def discover(user, **kwargs):
        return await Store().discover_metadata_page(**kwargs)

    service.tag_service.list_tag_descriptors_for_user = descriptors
    service.metadata_service.discover_documents_page = discover
    seen = []
    cursor = None
    for _ in range(10):
        response = await service.get_tree(_user(), DocumentTreeRequest(limit=5, max_chars=600, cursor=cursor))
        records = _records(response.tree)
        page = {record["uid"] for record in records if "uid" in record}
        assert page and len(response.tree) <= 600
        assert not page.intersection(seen)
        seen.extend(page)
        cursor = response.next_cursor
        if cursor is None:
            break
        assert response.truncated
    assert set(seen) == {str(i) for i in range(6)}
    with pytest.raises(InvalidTreePage):
        await service.get_tree(_user(), DocumentTreeRequest(limit=1, cursor="bad"))
    first = await service.get_tree(_user(), DocumentTreeRequest(limit=1))
    with pytest.raises(InvalidTreePage):
        await service.get_tree(_user(), DocumentTreeRequest(limit=1, cursor=first.next_cursor, name_filter="other"))
    with pytest.raises(ValidationError):
        DocumentTreeRequest(name_filter="Report")


@pytest.mark.asyncio
async def test_oversized_page_reports_budget_error_without_skipping():
    from fred_core.documents.document_store import DocumentDiscoveryEntry

    from knowledge_flow_backend.features.corpus_tree.service import InvalidTreePage, _render_page

    doc = _document(uid="large", name="x" * 1000)
    doc.tags.tag_ids = ["a"]
    with pytest.raises(InvalidTreePage, match="Increase max_chars"):
        _render_page([_tag(tag_id="a", full_path="A", item_ids=[])], [DocumentDiscoveryEntry(doc, doc.document_name)], 500)


@pytest.mark.asyncio
async def test_library_page_does_not_render_other_memberships():
    from fred_core.documents.document_store import DocumentDiscoveryEntry

    from knowledge_flow_backend.features.corpus_tree.service import _render_page, _selected_folders

    doc = _document(uid="shared", name="Report.pdf")
    doc.tags.tag_ids = ["a", "b"]
    tags = [_tag(tag_id="a", full_path="A", item_ids=[]), _tag(tag_id="b", full_path="B", item_ids=[])]
    entries = [DocumentDiscoveryEntry(doc, "report.pdf")]
    text, _ = _render_page(tags, entries, 20000, {"a"}, set())
    assert '"folder":"A"' in text and '"folder":"B"' not in text
    text, _ = _render_page(tags, entries, 20000, {"a"}, {"shared"})
    assert '"folder":"B"' in text
    many = [_tag(tag_id=str(i), full_path=f"Folder-{i}", item_ids=[]) for i in range(10001)]
    assert len(_selected_folders(many, [tag.id for tag in many])) == 10001


@pytest.mark.asyncio
@pytest.mark.parametrize("delegated", [False, True])
async def test_discovery_service_agent_uses_authorized_team_folders_only(monkeypatch, delegated):
    from unittest.mock import AsyncMock

    from knowledge_flow_backend.features.metadata import service as module
    from knowledge_flow_backend.features.metadata.service import MetadataService

    service = MetadataService.__new__(MetadataService)
    service.rebac = SimpleNamespace(lookup_user_resources=AsyncMock(return_value=[]))
    service.metadata_store = SimpleNamespace(discover_metadata_page=AsyncMock(return_value=([], False)))
    monkeypatch.setattr(module, "is_service_agent", lambda user: True)
    monkeypatch.setattr(module, "holds_caller_role", lambda user: delegated)
    args = dict(folder_ids=["authorized-team-folder"], selected_folder_ids=None, document_uids=None, name_filter=None, sort_by="name", sort_order="asc", limit=2, after=None)
    await service.discover_documents_page(_user(), **args)
    assert service.metadata_store.discover_metadata_page.call_args.kwargs["readable_uids"] == ([] if delegated else None)
    if not delegated:
        service.rebac.lookup_user_resources.assert_not_called()
    service.metadata_store.discover_metadata_page.reset_mock()
    await service.discover_documents_page(_user(), **{**args, "folder_ids": []})
    service.metadata_store.discover_metadata_page.assert_not_called()
