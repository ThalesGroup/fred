# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Selection transport, prefiltering and the shared published read boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_core.documents.access import SearchScope
from fred_core.documents.selection import DocumentScope
from fred_core.documents.transport import DOCUMENT_CONTEXT_HEADER, DocumentAccessContext
from fred_core.security.delegation import AssertedUser

from knowledge_flow_backend.core.stores.vector.base_vector_store import SearchFilter
from knowledge_flow_backend.core.stores.vector.chromadb_vector_store import _build_where
from knowledge_flow_backend.core.stores.vector.opensearch_vector_store import OpenSearchVectorStoreAdapter
from knowledge_flow_backend.features.content import published_markdown as markdown_module
from knowledge_flow_backend.features.extract import service as extract_module
from knowledge_flow_backend.features.summarize import service as summarize_module
from knowledge_flow_backend.features.vector_search import vector_search_service as search_module
from knowledge_flow_backend.features.vector_search.vector_search_structures import SearchRequest
from knowledge_flow_backend.security.weaver_admission import delegated_person

SPACE, FOLDER, DOC, CONVERSATION = [UUID(int=i) for i in range(1, 5)]
PERSON = AssertedUser(uid="alice", client_id="pod", run_id="turn", agent_id="agent")
SCOPE = DocumentScope.from_ids([str(FOLDER)]).intersect(DocumentScope.from_ids(document_ids=[str(DOC)]))


@pytest.mark.parametrize("scope", [DocumentScope(), DocumentScope.from_ids([], []), SCOPE])
def test_markdown_get_transports_scope_and_delegated_person(monkeypatch, scope):
    person = object()
    reader = AsyncMock(return_value="selected content")
    monkeypatch.setattr(markdown_module, "published_markdown", reader)
    app, router = FastAPI(), APIRouter()
    markdown_module.MarkdownController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: person
    with TestClient(app) as client:
        response = client.get(f"/documents/{DOC}/markdown", headers={DOCUMENT_CONTEXT_HEADER: DocumentAccessContext(space_id=SPACE, document_scope=scope).model_dump_json()})
    assert response.status_code == 200
    reader.assert_awaited_once_with(person, str(DOC), DocumentAccessContext(space_id=SPACE, document_scope=scope))


@pytest.mark.parametrize("value", ["", "null", "{}garbage", '{"selections":[{"document_ids":["old-id"]}]}'])
def test_malformed_selection_never_becomes_unrestricted(monkeypatch, value):
    reader = AsyncMock()
    monkeypatch.setattr(markdown_module, "published_markdown", reader)
    app, router = FastAPI(), APIRouter()
    markdown_module.MarkdownController(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: object()
    with TestClient(app) as client:
        assert client.get(f"/documents/{DOC}/markdown", headers={DOCUMENT_CONTEXT_HEADER: value}).status_code == 400
    reader.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["summarize", "extract"])
async def test_summary_and_extraction_cannot_bypass_the_published_scope(monkeypatch, operation):
    module = summarize_module if operation == "summarize" else extract_module
    reader = AsyncMock(side_effect=HTTPException(status_code=404, detail="document_not_found"))
    monkeypatch.setattr(module, "published_markdown", reader)
    person = object()
    if operation == "summarize":
        service = summarize_module.SummarizeService.__new__(summarize_module.SummarizeService)
        request = summarize_module.SummarizeDocumentRequest()
        call = service.summarize_document
    else:
        service = extract_module.ExtractService()
        request = extract_module.ExtractDocumentRequest(instruction="all")
        call = service.extract_document
    with pytest.raises(HTTPException) as failure:
        await call(person, str(DOC), request, DocumentAccessContext(space_id=SPACE, document_scope=SCOPE, conversation_id=CONVERSATION, attachment_ids=(DOC,)))
    assert failure.value.status_code == 404
    reader.assert_awaited_once_with(person, str(DOC), DocumentAccessContext(space_id=SPACE, document_scope=SCOPE, conversation_id=CONVERSATION, attachment_ids=(DOC,)))


@pytest.mark.asyncio
async def test_selection_does_not_replace_space_authorization(monkeypatch):
    admission = AsyncMock(side_effect=HTTPException(status_code=403))
    monkeypatch.setattr(markdown_module, "require_space_read", admission)
    with pytest.raises(HTTPException) as failure:
        await markdown_module.published_markdown(PERSON, str(DOC), DocumentAccessContext(space_id=SPACE, document_scope=SCOPE))
    assert failure.value.status_code == 403
    admission.assert_awaited_once()


def test_index_filters_preserve_union_intersection_and_direct_folder_semantics():
    selection = DocumentScope.from_ids([str(FOLDER)], [str(UUID(int=4))]).intersect(DocumentScope.from_ids(document_ids=[str(DOC)]))
    scope = SearchScope((SPACE,), selection, {FOLDER: f"/{FOLDER}/"})
    sf = SearchFilter(metadata_any=scope.selection_terms)
    assert sf.matches_selection({"document_uid": str(DOC), "folder_path": f"/{FOLDER}/"})
    assert not sf.matches_selection({"document_uid": str(DOC), "folder_path": f"/{FOLDER}/child/"})
    assert not sf.matches_selection({"document_uid": str(UUID(int=4)), "folder_path": "other"})
    os = OpenSearchVectorStoreAdapter.__new__(OpenSearchVectorStoreAdapter)
    clauses = os._to_filter_clause(sf)
    assert clauses[0]["bool"]["minimum_should_match"] == 1
    assert len(clauses[0]["bool"]["should"]) == 2
    assert clauses[1]["bool"]["should"] == [{"terms": {"metadata.document_uid": [str(DOC)]}}]
    assert "prefix" not in str(clauses)
    assert "$and" in _build_where(sf)
    assert os._to_filter_clause(SearchFilter(metadata_any=({},))) == [{"match_none": {}}]


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["strict", "hybrid", "semantic"])
async def test_search_prefilters_before_top_k_and_retains_sql_verification(monkeypatch, policy):
    service = search_module.VectorSearchService.__new__(search_module.VectorSearchService)
    service._require_corpus_ready = AsyncMock()
    service._semantic = AsyncMock(return_value=[])
    service._strict = AsyncMock(return_value=[])
    service._hybrid = AsyncMock(return_value=[])
    service.vector_store = SimpleNamespace()
    service._visible_hits = AsyncMock(return_value=[])
    service._record_search_stats = MagicMock()
    service._kpi_search_dims = MagicMock(return_value={})
    engine = MagicMock()
    conn = engine.connect.return_value.__aenter__.return_value
    context = SimpleNamespace(get_pg_async_engine=lambda: engine)
    monkeypatch.setattr(search_module.ApplicationContext, "get_instance", lambda: context)
    scope = SearchScope((SPACE,), SCOPE, {FOLDER: f"/{FOLDER}/"})
    resolver = AsyncMock(return_value=scope)
    monkeypatch.setattr(search_module, "resolve_scope", resolver)
    request = SearchRequest(question="q", search_policy=policy)
    person = PERSON
    await service.search(question=request.question, user=person, top_k=8, policy_name=request.search_policy, context=DocumentAccessContext(space_id=SPACE, document_scope=SCOPE))
    resolver.assert_awaited_once_with(conn, DocumentAccessContext(space_id=SPACE, document_scope=SCOPE), user_id=PERSON.uid)
    strategy = getattr(service, f"_{policy}")
    assert strategy.call_args.kwargs["metadata_any"] == scope.selection_terms
    assert strategy.call_args.kwargs["metadata_terms_extra"] == {"space_id": [str(SPACE)], "session_id": [""]}
    service._visible_hits.assert_awaited_once_with(scope, [], person)


def test_corpus_filter_preserves_the_empty_session_term_inside_knn():
    store = OpenSearchVectorStoreAdapter.__new__(OpenSearchVectorStoreAdapter)
    store._phase_timer = MagicMock()
    store._embedding_model = SimpleNamespace(embed_query=lambda _: [0.0, 1.0])
    store.client = MagicMock()
    store._client.search.return_value = {"hits": {"hits": []}}
    store._index = "test-index"
    store._build_ann_hits = MagicMock(return_value=[])
    search_filter = SearchFilter(metadata_terms={"space_id": [str(SPACE)], "session_id": [""]})
    clauses = store._to_filter_clause(search_filter)
    assert {"terms": {"metadata.session_id": [""]}} in clauses
    store.ann_search("q", k=8, search_filter=search_filter)
    body = store._client.search.call_args.kwargs["body"]
    assert body["query"]["knn"]["vector_field"]["filter"]["bool"]["filter"] == clauses
    assert "post_filter" not in body


OPERATIONS = [
    ("POST", "/documents/search", {"question": "q"}, None),
    ("GET", f"/documents/{DOC}/chunks", None, None),
    ("GET", f"/documents/{DOC}/markdown", None, None),
    ("POST", f"/documents/{DOC}/summarize", {}, None),
    ("POST", f"/documents/{DOC}/extract", {"instruction": "all"}, None),
    ("GET", "/tabular/documents", None, None),
    ("GET", "/tabular/documents/schemas", None, {"document_uids": str(DOC)}),
    ("POST", "/tabular/query", {"sql": "select 1"}, None),
    ("POST", "/tabular/search", {"keyword": "Paris"}, None),
]


@pytest.fixture
def document_app(monkeypatch):
    from knowledge_flow_backend.features.document_scope import declare_document_context_openapi
    from knowledge_flow_backend.features.extract.controller import ExtractController
    from knowledge_flow_backend.features.summarize.controller import SummarizeController
    from knowledge_flow_backend.features.tabular.controller import TabularController
    from knowledge_flow_backend.features.vector_search import vector_search_controller as vector_controller

    monkeypatch.setattr(vector_controller, "VectorSearchService", MagicMock)
    monkeypatch.setattr(vector_controller, "get_kpi_writer", MagicMock)
    monkeypatch.setattr(summarize_module.SummarizeService, "__init__", lambda self: None)
    app, router = FastAPI(), APIRouter(prefix="/custom/kf")
    for controller in (vector_controller.VectorSearchController, markdown_module.MarkdownController, SummarizeController, ExtractController, TabularController):
        controller(router)
    app.include_router(router)
    app.dependency_overrides[delegated_person] = lambda: object()
    declare_document_context_openapi(app)
    return app


@pytest.mark.parametrize("method,path,body,query", OPERATIONS)
@pytest.mark.parametrize(
    "raw,status,detail",
    [
        (None, 403, "document_context_required"),
        ("", 400, "invalid_document_context"),
        ("null", 400, "invalid_document_context"),
        (f'{{"space_id":"{SPACE}","document_scope":{{}},"attachment_ids":["{DOC}"]}}', 400, "invalid_document_context"),
        (f'{{"space_id":"{SPACE}","document_scope":{{}},"conversation_id":"bad"}}', 400, "invalid_document_context"),
        ('{"space_id":"bad","document_scope":{}}', 400, "invalid_document_context"),
        (f'{{"space_id":"{SPACE}"}}', 400, "invalid_document_context"),
        (f'{{"space_id":"{SPACE}","document_scope":{{}},"extra":true}}', 400, "invalid_document_context"),
    ],
)
def test_all_operations_require_the_same_context(document_app, method, path, body, query, raw, status, detail):
    headers = {} if raw is None else {DOCUMENT_CONTEXT_HEADER: raw}
    # Old query authority cannot rescue a missing or invalid header.
    params = {**(query or {}), "space_id": str(SPACE), "document_scope": "{}"}
    with TestClient(document_app) as client:
        response = client.request(method, "/custom/kf" + path, json=body, params=params, headers=headers)
    assert response.status_code == status
    assert response.json() == {"detail": detail}


def test_document_context_is_documented_on_exactly_nine_operations(document_app):
    schema = document_app.openapi()
    operations = [operation for path in schema["paths"].values() for operation in path.values()]
    assert len(operations) == 9
    for operation in operations:
        headers = [p for p in operation["parameters"] if p["name"] == DOCUMENT_CONTEXT_HEADER]
        assert len(headers) == 1
        assert headers[0]["required"] is True
        assert headers[0]["content"]["application/json"]["schema"] == {"$ref": "#/components/schemas/DocumentAccessContext"}
        assert not any(p["name"] in ("space_id", "document_scope", "conversation_id", "attachment_ids") for p in operation["parameters"])
    assert set(schema["components"]["schemas"]["DocumentAccessContext"]["required"]) == {"space_id", "document_scope"}
    assert "DocumentScope" in schema["components"]["schemas"]
    assert "DocumentSelection" in schema["components"]["schemas"]


@pytest.mark.parametrize("method,path,body,query", [item for item in OPERATIONS if item[0] == "POST"])
@pytest.mark.parametrize("field,value", [("space_id", str(SPACE)), ("document_scope", {}), ("conversation_id", str(CONVERSATION)), ("attachment_ids", [str(DOC)])])
def test_business_bodies_cannot_supply_authority(document_app, monkeypatch, method, path, body, query, field, value):
    from knowledge_flow_backend.features.tabular.controller import tabular_service

    document_app.dependency_overrides[tabular_service] = lambda: object()
    header = DocumentAccessContext(space_id=SPACE, document_scope=SCOPE).model_dump_json()
    with TestClient(document_app) as client:
        response = client.request(method, "/custom/kf" + path, json={**body, field: value}, headers={DOCUMENT_CONTEXT_HEADER: header})
    assert response.status_code == 422
    assert any(error["type"] == "extra_forbidden" and error["loc"] == ["body", field] for error in response.json()["detail"])


def test_authentication_precedes_context_validation(document_app):
    async def refused():
        raise HTTPException(403, detail="delegated_call_required")

    document_app.dependency_overrides[delegated_person] = refused
    with TestClient(document_app) as client:
        response = client.get(f"/custom/kf/documents/{DOC}/markdown", headers={DOCUMENT_CONTEXT_HEADER: "invalid"})
    assert response.json() == {"detail": "delegated_call_required"}


@pytest.mark.asyncio
@pytest.mark.parametrize("corpus", [DocumentScope(), DocumentScope.from_ids([str(FOLDER)]), DocumentScope.from_ids([], [])])
async def test_search_union_prefilters_concurrently_then_verifies_sql_and_bounds(monkeypatch, corpus):
    import asyncio
    from uuid import uuid5

    from langchain_core.documents import Document

    from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorHit

    attachment_id, generation = UUID(int=8), UUID(int=9)
    context = DocumentAccessContext(space_id=SPACE, document_scope=corpus, conversation_id=CONVERSATION, attachment_ids=(attachment_id,))
    scope = SearchScope((SPACE,), corpus, {FOLDER: f"/{FOLDER}/"}, CONVERSATION, (attachment_id,), PERSON.uid)
    engine = MagicMock()
    conn = engine.connect.return_value.__aenter__.return_value
    result = MagicMock()
    facts = dict(space_id=SPACE, deletion_id=None, space_deletion_id=None, retrievable=True, retrievable_pending=False, generation_id=generation, vector_ordinals=[0, 1])
    result.mappings.return_value.all.return_value = [
        dict(facts, id=DOC, folder_id=FOLDER, session_id=None),
        dict(facts, id=attachment_id, folder_id=None, session_id=CONVERSATION, session_user_id=PERSON.uid, session_deletion_id=None),
    ]
    conn.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(search_module.ApplicationContext, "get_instance", lambda: SimpleNamespace(get_pg_async_engine=lambda: engine))
    monkeypatch.setattr(search_module, "resolve_scope", AsyncMock(return_value=scope))
    service = search_module.VectorSearchService.__new__(search_module.VectorSearchService)
    service._require_corpus_ready = AsyncMock()
    service.vector_store = SimpleNamespace()
    service._record_search_stats = MagicMock()
    service._kpi_search_dims = MagicMock(return_value={})
    service._to_hit = AsyncMock(side_effect=lambda doc, score, rank, user: SimpleNamespace(content=doc.page_content, score=score, rank=rank))
    started = []
    both_started = asyncio.Event()

    def hit(uid, ordinal, score, label):
        return BaseVectorHit(document=Document(page_content=label, metadata={"document_uid": str(uid), "chunk_uid": str(uuid5(generation, str(ordinal)))}), score=score)

    async def strategy(**kwargs):
        started.append(kwargs)
        if len(started) == (1 if corpus.is_empty else 2):
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        assert kwargs["k"] == 2
        if kwargs["metadata_terms_extra"]["session_id"] == [""]:
            assert kwargs["metadata_any"] == scope.selection_terms
            return [hit(DOC, 0, 900, "corpus")]
        assert kwargs["metadata_any"] == ()
        assert kwargs["metadata_terms_extra"] == {"space_id": [str(SPACE)], "session_id": [str(CONVERSATION)], "document_uid": [str(attachment_id)]}
        # Positive prefilter is insufficient: this old/unpublished ordinal must be dropped.
        return [hit(attachment_id, 5, 1.0, "stale"), hit(attachment_id, 1, 0.25, "attachment")]

    service._semantic = strategy
    hits = await service.search(question="q", user=PERSON, top_k=2, policy_name=search_module.SearchPolicyName.semantic, context=context)
    assert [hit.content for hit in hits] == (["attachment"] if corpus.is_empty else ["corpus", "attachment"])
    assert len(hits) <= 2
    assert hits[-1].score == (0.25 if corpus.is_empty else 1 / 62)
    conn.execute.assert_awaited_once()
    assert "g.id = d.published_generation" in str(conn.execute.call_args.args[0])


def test_rank_fusion_deduplicates_and_ignores_incomparable_scores():
    from langchain_core.documents import Document

    from knowledge_flow_backend.core.stores.vector.base_vector_store import BaseVectorHit

    def hit(uid, score):
        return BaseVectorHit(document=Document(page_content=uid, metadata={"chunk_uid": uid}), score=score)

    rankings = [[hit("a", 999), hit("b", 20), hit("a", 1000)], [hit("c", 0.001), hit("b", 0.0001)]]
    merged = search_module._merge_rankings(rankings)
    assert [doc.page_content for doc, _ in merged] == ["b", "a", "c"]
    assert merged == search_module._merge_rankings(rankings)
    assert [score for _, score in merged] == [2 / 62, 1 / 61, 1 / 61]


@pytest.mark.asyncio
async def test_direct_attachment_chunks_require_sql_publication_and_requested_document(monkeypatch):
    from uuid import uuid5

    generation = UUID(int=15)
    scope = SearchScope((SPACE,), DocumentScope.from_ids([], []), {}, CONVERSATION, (DOC,), PERSON.uid)
    engine = MagicMock()
    conn = engine.connect.return_value.__aenter__.return_value
    result = MagicMock()
    result.mappings.return_value.all.return_value = [
        dict(
            id=DOC,
            space_id=SPACE,
            session_id=CONVERSATION,
            session_user_id=PERSON.uid,
            session_deletion_id=None,
            folder_id=None,
            deletion_id=None,
            space_deletion_id=None,
            retrievable=True,
            retrievable_pending=False,
            generation_id=generation,
            vector_ordinals=[0],
        )
    ]
    conn.execute = AsyncMock(return_value=result)
    monkeypatch.setattr(search_module.ApplicationContext, "get_instance", lambda: SimpleNamespace(get_pg_async_engine=lambda: engine))
    monkeypatch.setattr(search_module, "resolve_scope", AsyncMock(return_value=scope))
    service = search_module.VectorSearchService.__new__(search_module.VectorSearchService)
    service._require_corpus_ready = AsyncMock()
    service._to_hit = AsyncMock(side_effect=lambda doc, score, rank, user: doc.page_content)
    rows = [dict(text=str(i), metadata={"document_uid": str(DOC), "chunk_uid": str(uuid5(generation, str(i))), "chunk_index": i}) for i in (0, 2)]
    rows.append(dict(text="injected", metadata={"document_uid": str(FOLDER), "chunk_uid": str(uuid5(generation, "0")), "chunk_index": 0}))
    service.vector_store = SimpleNamespace(get_chunks_for_document=lambda _: rows)
    context = DocumentAccessContext(space_id=SPACE, document_scope=scope.document_scope, conversation_id=CONVERSATION, attachment_ids=(DOC,))
    assert await service.get_document_chunks_ordered(user=PERSON, document_uid=str(DOC), context=context, limit=10) == ["0"]
