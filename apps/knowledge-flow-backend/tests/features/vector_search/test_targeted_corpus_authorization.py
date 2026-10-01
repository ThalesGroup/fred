"""Named vector targets use persisted folder rights, independently of personal scope."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fred_core import AuthorizationError, KeycloakUser, Resource, TeamPermission
from fred_core.store import VectorSearchHit

from knowledge_flow_backend.features.metadata.service import MetadataNotFound, MetadataService
from knowledge_flow_backend.features.tag.corpus_access import CorpusAccess
from knowledge_flow_backend.features.vector_search.vector_search_service import VectorSearchService


def _service(count=1):
    folders = AsyncMock()
    folders.get_tags_by_ids.return_value = [SimpleNamespace(id="folder-a", owner_id="team-a", deletion_task_id=None), SimpleNamespace(id="folder-b", owner_id="team-a", deletion_task_id=None)]
    rebac = AsyncMock()
    access = CorpusAccess(rebac, folders)
    documents = [SimpleNamespace(document_uid=f"doc-{i}", kind="corpus", tags=SimpleNamespace(tag_ids=["folder-b"])) for i in range(count)]
    store = AsyncMock()
    store.get_metadata_by_uids.return_value = documents
    service = VectorSearchService.__new__(VectorSearchService)
    service.metadata_service = SimpleNamespace(metadata_store=store)
    service.tag_service = SimpleNamespace(corpus_access=access)
    service._hybrid = AsyncMock(return_value=[])
    return service, rebac, folders, documents


USER = KeycloakUser(uid="alice", username="alice", roles=[])


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 1001, 5001])
async def test_comparison_authorizes_once_and_keeps_additive_targets(count):
    service, rebac, folders, documents = _service(count)
    first = VectorSearchHit(uid="in-folder-a", content="a", title="A", score=0.9, rank=1)
    second = VectorSearchHit(uid="doc-0", content="b", title="B", score=0.8, rank=1)
    service._hybrid.side_effect = [[first], [second]]
    uids = [doc.document_uid for doc in documents]
    hits = await service.similarity_search(anchor="compare", user=USER, document_uids=uids, document_library_tags_ids=["folder-a"], rerank=False)
    assert [hit.uid for hit in hits] == ["in-folder-a", "doc-0"]
    rebac.check_user_permission_or_raise.assert_awaited_once_with(USER, TeamPermission.CAN_USE_TEAM_KNOWLEDGE_BASES, "team-a")
    assert set(folders.get_tags_by_ids.call_args.args[0]) == {"folder-a", "folder-b"}
    assert service._hybrid.call_args_list[1].kwargs["metadata_terms_extra"] == {"scope": ["!session"], "document_uid": uids}
    rebac.lookup_user_resources.assert_not_called()


@pytest.mark.asyncio
async def test_denied_comparison_never_queries_vectors():
    service, rebac, _, _ = _service()
    rebac.check_user_permission_or_raise.side_effect = AuthorizationError(USER.uid, "read", Resource.TEAM)
    with pytest.raises(AuthorizationError):
        await service.similarity_search(anchor="compare", user=USER, document_uids=["doc-0"], document_library_tags_ids=["folder-a"], rerank=False)
    service._hybrid.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_comparison_document_rejects_whole_request():
    service, _, _, _ = _service()
    with pytest.raises(MetadataNotFound):
        await service.similarity_search(anchor="compare", user=USER, document_uids=["doc-0", "missing"], rerank=False)
    service._hybrid.assert_not_awaited()


@pytest.mark.asyncio
async def test_attachment_cannot_be_used_as_corpus_comparison():
    service, _, _, documents = _service()
    documents[0].kind = "attachment"
    with pytest.raises(AuthorizationError):
        await service.similarity_search(anchor="compare", user=USER, document_uids=["doc-0"], rerank=False)
    service._hybrid.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerank_batch_requires_editor_once_for_stored_team():
    vector, rebac, folders, documents = _service(1001)
    folders.get_tags_by_ids.return_value = [SimpleNamespace(id="folder-b", owner_id="team-a", deletion_task_id=None)]
    service = MetadataService.__new__(MetadataService)
    service.metadata_store = vector.metadata_service.metadata_store
    service.corpus_access = vector.tag_service.corpus_access
    await service.require_documents(USER, [doc.document_uid for doc in documents], write=True)
    rebac.check_user_permission_or_raise.assert_awaited_once_with(USER, TeamPermission.CAN_UPDATE_RESOURCES, "team-a")


@pytest.mark.asyncio
async def test_result_decoration_does_not_recheck_each_hit_or_remove_stale_hits():
    service, rebac, folders, _ = _service()
    folders.get_tags_by_ids.return_value = [SimpleNamespace(id="folder-a", name="A", full_path="Root/A")]
    hits = [VectorSearchHit(uid=f"doc-{i}", title="D", score=0.8, content="text", tag_ids=["folder-a"]) for i in range(1001)]
    hits.append(VectorSearchHit(uid="deleted", title="D", score=0.8, content="stale excerpt", tag_ids=["gone"]))
    await service._hydrate_hit_folders(hits)
    folders.get_tags_by_ids.assert_awaited_once()
    rebac.check_user_permission_or_raise.assert_not_awaited()
    assert len(hits) == 1002
    assert hits[0].tag_names == ["A"]
    assert hits[0].tag_full_paths == ["Root/A"]
    assert hits[-1].content == "stale excerpt"
    assert hits[-1].tag_names == []


def test_comparison_missing_folder_is_http_404(monkeypatch):
    from fastapi import APIRouter, FastAPI
    from fastapi.testclient import TestClient
    from fred_core import get_current_user
    from fred_core.kpi import NoOpKPIWriter

    from knowledge_flow_backend.features.vector_search import vector_search_controller as controller

    service, _, folders, _ = _service()
    folders.get_tags_by_ids.return_value = []
    monkeypatch.setattr(controller, "VectorSearchService", lambda: service)
    monkeypatch.setattr(controller, "get_kpi_writer", NoOpKPIWriter)
    router = APIRouter()
    controller.VectorSearchController(router)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: USER
    response = TestClient(app).post("/vector/similarity-search", json={"anchor": "comparison", "document_library_tags_ids": ["missing"]})
    assert response.status_code == 404
    service._hybrid.assert_not_awaited()
