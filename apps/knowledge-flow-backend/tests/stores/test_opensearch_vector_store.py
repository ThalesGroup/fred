from __future__ import annotations

from copy import deepcopy

import pytest
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from knowledge_flow_backend import application_context as app_context_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import OpenSearchVectorIndexConfig
from knowledge_flow_backend.core.stores.vector import opensearch_vector_store as ovs

TEST_OPENSEARCH_PASSWORD = "secret"  # pragma: allowlist secret


class DummyEmbeddings(Embeddings):
    def __init__(self, size: int) -> None:
        self.size = size

    def embed_query(self, text: str) -> list[float]:
        return [0.0] * self.size

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.size for _ in texts]


def _deep_merge(dst: dict, src: dict) -> dict:
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = deepcopy(value)
    return dst


class FakeSearchPipeline:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists
        self.put_calls: list[tuple[str, dict]] = []

    def get(self, id: str) -> dict:
        if not self.exists:
            raise ovs.NotFoundError(404, "not found", {})
        return {"id": id}

    def put(self, id: str, body: dict) -> dict:
        self.exists = True
        self.put_calls.append((id, deepcopy(body)))
        return {"acknowledged": True}


class FakeIndices:
    def __init__(self, index_name: str, index_body: dict | None = None) -> None:
        self.index_name = index_name
        self.create_calls: list[tuple[str, dict]] = []
        self.put_mapping_calls: list[tuple[str, dict]] = []
        self._mappings: dict[str, dict] = {}
        self._settings: dict[str, dict] = {}
        if index_body is not None:
            self._store_index(index_name, index_body)

    def _store_index(self, index: str, body: dict) -> None:
        self._mappings[index] = deepcopy(body["mappings"])
        self._settings[index] = {"settings": deepcopy(body["settings"])}

    def exists(self, index: str) -> bool:
        return index in self._mappings

    def create(self, index: str, body: dict) -> dict:
        self.create_calls.append((index, deepcopy(body)))
        self._store_index(index, body)
        return {"acknowledged": True}

    def get_mapping(self, index: str) -> dict:
        return {index: {"mappings": deepcopy(self._mappings[index])}}

    def get_settings(self, index: str) -> dict:
        return {index: deepcopy(self._settings[index])}

    def put_mapping(self, index: str, body: dict) -> dict:
        self.put_mapping_calls.append((index, deepcopy(body)))
        current = self._mappings.setdefault(index, {"properties": {}})
        _deep_merge(current, body)
        return {"acknowledged": True}


class FakeOpenSearchClient:
    def __init__(
        self,
        *,
        index_name: str,
        index_body: dict | None = None,
        pipeline_exists: bool = True,
    ) -> None:
        self.indices = FakeIndices(index_name=index_name, index_body=index_body)
        self.search_pipeline = FakeSearchPipeline(exists=pipeline_exists)
        self.update_by_query_calls: list[tuple[str, dict]] = []
        self.update_by_query_response: dict = {"updated": 1}
        self.search_calls: list[dict] = []
        self.search_responses: list[dict] = []
        self.search_request_timeouts: list[int | None] = []

    def close(self) -> None:
        return None

    def update_by_query(self, *, index: str, body: dict, params: dict | None = None) -> dict:
        self.update_by_query_calls.append((index, deepcopy(body)))
        return self.update_by_query_response

    def search(self, *, index: str, body: dict, request_timeout: int | None = None) -> dict:
        self.search_calls.append(deepcopy(body))
        self.search_request_timeouts.append(request_timeout)
        if self.search_responses:
            return self.search_responses.pop(0)
        return {"aggregations": {}}


def test_opensearch_vector_store_creates_missing_index(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
    )

    assert store.index_name == "fred-vectors"
    assert len(fake_client.indices.create_calls) == 1
    _, body = fake_client.indices.create_calls[0]
    assert body["mappings"]["properties"]["vector_field"]["dimension"] == 8
    assert fake_client.search_pipeline.put_calls == []


def test_opensearch_vector_store_validates_existing_index(monkeypatch):
    mapping = ovs.build_vector_index_mapping(12)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    validate_calls: list[tuple[str, int]] = []

    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)
    monkeypatch.setattr(
        ovs,
        "validate_index_mapping",
        lambda client, index_name, expected: validate_calls.append((index_name, expected["mappings"]["properties"]["vector_field"]["dimension"])),
    )

    ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=12),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
    )

    assert fake_client.indices.create_calls == []
    assert validate_calls == [("fred-vectors", 12)]


def test_opensearch_vector_store_rejects_incompatible_dimension(monkeypatch):
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)

    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    with pytest.raises(ValueError, match="Dimension mismatch"):
        ovs.OpenSearchVectorStoreAdapter(
            embedding_model=DummyEmbeddings(size=9),
            embedding_model_name="custom-model",
            kpi=None,
            host="http://localhost:9200",
            index="fred-vectors",
            username="admin",
            password=TEST_OPENSEARCH_PASSWORD,
        )


def _make_store_for_existing_index(monkeypatch, fake_client: FakeOpenSearchClient) -> ovs.OpenSearchVectorStoreAdapter:
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)
    return ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=4),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
    )


def test_set_document_name_logs_error_when_no_chunks_matched(monkeypatch, caplog):
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.update_by_query_response = {"updated": 0}
    store = _make_store_for_existing_index(monkeypatch, fake_client)

    with caplog.at_level("ERROR"):
        store.set_document_name(document_uid="doc-1", document_name="new-name.pdf")

    assert any("matched 0 vector chunks" in r.message for r in caplog.records)


def test_set_document_name_logs_error_on_reported_failures(monkeypatch, caplog):
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.update_by_query_response = {"updated": 2, "failures": [{"cause": "version_conflict"}]}
    store = _make_store_for_existing_index(monkeypatch, fake_client)

    with caplog.at_level("ERROR"):
        store.set_document_name(document_uid="doc-1", document_name="new-name.pdf")

    assert any("reported 1 failure" in r.message for r in caplog.records)


def test_set_document_name_does_not_log_error_on_full_success(monkeypatch, caplog):
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.update_by_query_response = {"updated": 3}
    store = _make_store_for_existing_index(monkeypatch, fake_client)

    with caplog.at_level("INFO"):
        store.set_document_name(document_uid="doc-1", document_name="new-name.pdf")

    assert not any(r.levelname == "ERROR" for r in caplog.records)
    assert any("updated document_name on 3 vector chunks" in r.message for r in caplog.records)


def test_application_context_opensearch_factory_does_not_call_validate_index_or_fail(
    app_context,
    monkeypatch,
):
    ctx = ApplicationContext.get_instance()
    ctx._vector_store_instance = None
    ctx.configuration.storage.vector_store = OpenSearchVectorIndexConfig(
        type="opensearch",
        index="fred-vectors",
    )
    ctx.configuration.storage.opensearch.password = TEST_OPENSEARCH_PASSWORD

    created: list[dict] = []

    class DummyStore:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)

        def validate_index_or_fail(self) -> None:
            raise AssertionError("validate_index_or_fail should not be called")

    monkeypatch.setattr(app_context_module, "OpenSearchVectorStoreAdapter", DummyStore)
    monkeypatch.setattr(ctx, "get_kpi_writer", lambda: None)

    store = ctx.get_create_vector_store(FakeEmbeddings(size=6))

    assert isinstance(store, DummyStore)
    assert created
    assert created[0]["index"] == "fred-vectors"


def test_opensearch_vector_store_add_documents_batches_by_bulk_size(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, bulk_size: int, **kwargs) -> None:
            self.bulk_size = bulk_size
            self.calls: list[tuple[int, list[str]]] = []
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            if len(documents) > self.bulk_size:
                raise RuntimeError("batch exceeds bulk size")
            self.calls.append((len(documents), list(ids)))
            return list(ids)

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=2,
    )

    docs = [
        Document(
            page_content=f"chunk {i}",
            metadata={ovs.CHUNK_ID_FIELD: f"cid-{i}", "document_uid": "doc-1"},
        )
        for i in range(5)
    ]

    assigned_ids = store.add_documents(docs)

    assert assigned_ids == [f"cid-{i}" for i in range(5)]
    assert len(FakeVectorSearch.created) == 1
    assert FakeVectorSearch.created[0].calls == [
        (2, ["cid-0", "cid-1"]),
        (2, ["cid-2", "cid-3"]),
        (1, ["cid-4"]),
    ]
    assert all(d.metadata.get("embedding_model") == "custom-model" for d in docs)
    assert all(d.metadata.get("vector_index") == "fred-vectors" for d in docs)
    assert all("token_count" in d.metadata for d in docs)
    assert all("ingested_at" in d.metadata for d in docs)


def test_opensearch_vector_store_add_documents_rejects_mismatched_ids(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeVectorSearch:
        def __init__(self, *args, **kwargs) -> None:
            return None

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=2,
    )

    docs = [Document(page_content="chunk", metadata={ovs.CHUNK_ID_FIELD: "cid-1"})]

    with pytest.raises(RuntimeError, match="Unexpected error during vector indexing"):
        store.add_documents(docs, ids=["cid-1", "cid-2"])


def test_opensearch_vector_store_add_documents_splits_embedding_batches_on_provider_limit(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeEmbeddingBatchLimitError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider rejected embedding batch")
            self.status_code = 400
            self.code = "3210"
            self.type = "invalid_request_prompt"
            self.body = {
                "code": "3210",
                "type": "invalid_request_prompt",
                "raw_status_code": 400,
            }

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[int, list[str]]] = []
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            self.calls.append((len(documents), list(ids)))
            if len(documents) > 2:
                raise FakeEmbeddingBatchLimitError()
            return list(ids)

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=5,
    )

    docs = [
        Document(
            page_content=f"chunk {i}",
            metadata={ovs.CHUNK_ID_FIELD: f"cid-{i}", "document_uid": "doc-1"},
        )
        for i in range(5)
    ]

    assigned_ids = store.add_documents(docs)

    assert assigned_ids == [f"cid-{i}" for i in range(5)]
    assert len(FakeVectorSearch.created) == 1
    # The failed 5-doc attempt lowers the learned cap to 2, so the 3-doc right
    # half is pre-split without re-attempting a size known to fail.
    assert FakeVectorSearch.created[0].calls == [
        (5, ["cid-0", "cid-1", "cid-2", "cid-3", "cid-4"]),
        (2, ["cid-0", "cid-1"]),
        (1, ["cid-2"]),
        (2, ["cid-3", "cid-4"]),
    ]


def test_opensearch_vector_store_reuses_learned_embedding_batch_size_across_bulk_slices(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeEmbeddingBatchLimitError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider rejected embedding batch")
            self.status_code = 400
            self.code = "3210"
            self.type = "invalid_request_prompt"
            self.body = {
                "code": "3210",
                "type": "invalid_request_prompt",
                "raw_status_code": 400,
            }

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[int, list[str]]] = []
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            self.calls.append((len(documents), list(ids)))
            if len(documents) > 2:
                raise FakeEmbeddingBatchLimitError()
            return list(ids)

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=4,
    )

    docs = [
        Document(
            page_content=f"chunk {i}",
            metadata={ovs.CHUNK_ID_FIELD: f"cid-{i}", "document_uid": "doc-1"},
        )
        for i in range(8)
    ]

    assigned_ids = store.add_documents(docs)

    assert assigned_ids == [f"cid-{i}" for i in range(8)]
    # Only the very first slice pays a failed provider call; every later slice
    # is cut at the learned cap (2) up front.
    assert FakeVectorSearch.created[0].calls == [
        (4, ["cid-0", "cid-1", "cid-2", "cid-3"]),
        (2, ["cid-0", "cid-1"]),
        (2, ["cid-2", "cid-3"]),
        (2, ["cid-4", "cid-5"]),
        (2, ["cid-6", "cid-7"]),
    ]


def test_opensearch_vector_store_does_not_reattempt_a_batch_size_that_just_failed(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeEmbeddingBatchLimitError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider rejected embedding batch")
            self.status_code = 400
            self.code = "3210"
            self.type = "invalid_request_prompt"
            self.body = {
                "code": "3210",
                "type": "invalid_request_prompt",
                "raw_status_code": 400,
            }

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[int, list[str]]] = []
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            self.calls.append((len(documents), list(ids)))
            if len(documents) > 2:
                raise FakeEmbeddingBatchLimitError()
            return list(ids)

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=8,
    )

    docs = [
        Document(
            page_content=f"chunk {i}",
            metadata={ovs.CHUNK_ID_FIELD: f"cid-{i}", "document_uid": "doc-1"},
        )
        for i in range(8)
    ]

    assigned_ids = store.add_documents(docs)

    assert assigned_ids == [f"cid-{i}" for i in range(8)]
    # 8 fails -> cap 4; 4 fails -> cap 2. The right 4-doc half is then pre-split
    # instead of re-attempting size 4, which the left half just saw fail.
    calls = FakeVectorSearch.created[0].calls
    assert calls == [
        (8, [f"cid-{i}" for i in range(8)]),
        (4, ["cid-0", "cid-1", "cid-2", "cid-3"]),
        (2, ["cid-0", "cid-1"]),
        (2, ["cid-2", "cid-3"]),
        (2, ["cid-4", "cid-5"]),
        (2, ["cid-6", "cid-7"]),
    ]
    assert [size for size, _ in calls].count(4) == 1


def test_opensearch_vector_store_retries_single_oversized_document_with_smaller_text_splitter(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)
    configured_chunk_size = ApplicationContext.get_instance().get_text_splitter().chunk_size

    class FakeEmbeddingBatchLimitError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider rejected embedding batch")
            self.status_code = 400
            self.code = "3210"
            self.type = "invalid_request_prompt"
            self.body = {
                "code": "3210",
                "type": "invalid_request_prompt",
                "raw_status_code": 400,
            }

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[int, list[str]]] = []
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            self.calls.append((len(documents), list(ids)))
            if len(documents) == 1:
                raise FakeEmbeddingBatchLimitError()
            assert all(len(doc.page_content) <= configured_chunk_size // 2 for doc in documents)
            return list(ids)

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=100,
    )

    long_text = ("## Section\n\n" + ("very long attachment content " * 220)) * 4
    docs = [
        Document(
            page_content=long_text,
            metadata={ovs.CHUNK_ID_FIELD: "cid-long", "document_uid": "doc-1"},
        )
    ]

    assigned_ids = store.add_documents(docs)

    assert len(assigned_ids) > 1
    assert assigned_ids == [f"cid-long::part::{index}" for index in range(len(assigned_ids))]
    assert FakeVectorSearch.created[0].calls[0] == (1, ["cid-long"])
    assert FakeVectorSearch.created[0].calls[1] == (len(assigned_ids), assigned_ids)


def test_opensearch_vector_store_retries_transient_embedding_failure_without_splitting(monkeypatch):
    fake_client = FakeOpenSearchClient(index_name="fred-vectors")
    monkeypatch.setattr(ovs, "OpenSearch", lambda *args, **kwargs: fake_client)

    class FakeEmbeddingBatchLimitError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider rejected embedding batch")
            self.status_code = 400
            self.code = "3210"
            self.type = "invalid_request_prompt"
            self.body = {
                "code": "3210",
                "type": "invalid_request_prompt",
                "raw_status_code": 400,
            }

    class FakeTransientEmbeddingError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("provider temporarily overloaded")
            self.status_code = 503
            self.type = "server_error"
            self.body = {
                "type": "server_error",
                "raw_status_code": 503,
            }

    class FakeVectorSearch:
        created: list["FakeVectorSearch"] = []

        def __init__(self, *args, **kwargs) -> None:
            self.calls: list[tuple[int, list[str]]] = []
            self.attempts = 0
            FakeVectorSearch.created.append(self)

        def add_documents(self, documents: list[Document], ids: list[str] | None = None) -> list[str]:
            assert ids is not None
            self.calls.append((len(documents), list(ids)))
            if self.attempts == 0:
                self.attempts += 1
                try:
                    raise FakeEmbeddingBatchLimitError()
                except FakeEmbeddingBatchLimitError as limit_error:
                    raise FakeTransientEmbeddingError() from limit_error
            return list(ids)

    sleep_calls: list[float] = []

    monkeypatch.setattr(ovs, "OpenSearchVectorSearch", FakeVectorSearch)
    monkeypatch.setattr(ovs.time, "sleep", lambda seconds: sleep_calls.append(seconds))

    store = ovs.OpenSearchVectorStoreAdapter(
        embedding_model=DummyEmbeddings(size=8),
        embedding_model_name="custom-model",
        kpi=None,
        host="http://localhost:9200",
        index="fred-vectors",
        username="admin",
        password=TEST_OPENSEARCH_PASSWORD,
        bulk_size=4,
    )

    docs = [
        Document(
            page_content=f"chunk {i}",
            metadata={ovs.CHUNK_ID_FIELD: f"cid-{i}", "document_uid": "doc-1"},
        )
        for i in range(4)
    ]

    assigned_ids = store.add_documents(docs)

    assert assigned_ids == [f"cid-{i}" for i in range(4)]
    assert len(FakeVectorSearch.created) == 1
    assert FakeVectorSearch.created[0].calls == [
        (4, ["cid-0", "cid-1", "cid-2", "cid-3"]),
        (4, ["cid-0", "cid-1", "cid-2", "cid-3"]),
    ]
    assert sleep_calls == [ovs.EMBEDDING_RETRY_BASE_DELAY_SECONDS]


def test_list_document_uids_pages_past_a_single_page_via_composite_aggregation(monkeypatch):
    """A one-shot `terms` agg silently truncates once an index holds more distinct
    document_uids than its `size`. This must page through `after_key` until
    exhausted instead, or a real deployment's own audit tool (`MetadataService.
    audit_stores`) would eventually treat correctly-vectorized documents that fell
    off the truncated list as `missing_vectors` and reset them (#2234)."""
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.search_responses = [
        {
            "aggregations": {
                "by_doc": {
                    "after_key": {"doc_uid": "doc-2"},
                    "buckets": [
                        {"key": {"doc_uid": "doc-1"}, "doc_count": 5},
                        {"key": {"doc_uid": "doc-2"}, "doc_count": 3},
                    ],
                }
            }
        },
        {
            "aggregations": {
                "by_doc": {
                    "after_key": {"doc_uid": "doc-3"},
                    "buckets": [{"key": {"doc_uid": "doc-3"}, "doc_count": 1}],
                }
            }
        },
        {"aggregations": {"by_doc": {"buckets": []}}},
    ]
    store = _make_store_for_existing_index(monkeypatch, fake_client)

    result = store.list_document_uids(page_size=2)

    assert result == ["doc-1", "doc-2", "doc-3"]
    assert len(fake_client.search_calls) == 3
    assert fake_client.search_calls[0]["aggs"]["by_doc"]["composite"]["size"] == 2
    assert "after" not in fake_client.search_calls[0]["aggs"]["by_doc"]["composite"]
    assert fake_client.search_calls[1]["aggs"]["by_doc"]["composite"]["after"] == {"doc_uid": "doc-2"}
    assert fake_client.search_calls[2]["aggs"]["by_doc"]["composite"]["after"] == {"doc_uid": "doc-3"}


def test_list_document_uids_returns_empty_list_when_store_raises(monkeypatch):
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)

    def _raise(*, index: str, body: dict, request_timeout: int | None = None) -> dict:
        raise RuntimeError("boom")

    fake_client.search = _raise  # type: ignore[method-assign]
    store = _make_store_for_existing_index(monkeypatch, fake_client)

    assert store.list_document_uids() == []


# ── scan_document_uids_composite (module-level, pure) -- #2234 3a repair path ─
# Extracted so the repair action's `list_strict_vector_document_uids` activity
# can page through document_uids using only a raw, already-configured
# `OpenSearch` client (`ApplicationContext.get_opensearch_client()`) -- never an
# `OpenSearchVectorStoreAdapter` instance, whose `__init__` calls `ensure_ready()`
# (embedder call, possible index/pipeline creation). These tests exercise the
# helper directly, the same way the activity does, independent of the adapter.


def test_scan_document_uids_composite_pages_multiple_times_via_after_key():
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.search_responses = [
        {
            "aggregations": {
                "by_doc": {
                    "after_key": {"doc_uid": "doc-2"},
                    "buckets": [
                        {"key": {"doc_uid": "doc-1"}, "doc_count": 5},
                        {"key": {"doc_uid": "doc-2"}, "doc_count": 3},
                    ],
                }
            }
        },
        {
            "aggregations": {
                "by_doc": {
                    "after_key": {"doc_uid": "doc-3"},
                    "buckets": [{"key": {"doc_uid": "doc-3"}, "doc_count": 1}],
                }
            }
        },
        {"aggregations": {"by_doc": {"buckets": []}}},
    ]

    result = ovs.scan_document_uids_composite(fake_client, "fred-vectors", page_size=2, strict=True)

    assert result == ["doc-1", "doc-2", "doc-3"]
    assert len(fake_client.search_calls) == 3


def test_scan_document_uids_composite_passes_a_bounded_request_timeout():
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    fake_client.search_responses = [{"aggregations": {"by_doc": {"buckets": []}}}]

    ovs.scan_document_uids_composite(fake_client, "fred-vectors", request_timeout=7)

    assert fake_client.search_request_timeouts == [7]


def test_scan_document_uids_composite_strict_raises_when_an_intermediate_page_fails():
    """The failure happens on page 2, *after* page 1 already returned real
    document_uids -- strict mode must still raise (never return the partial
    list collected so far), so a caller that must never treat "scan failed" as
    "these N document_uids are the complete answer" gets a hard error."""
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)
    call_count = {"n": 0}
    first_page = {
        "aggregations": {
            "by_doc": {
                "after_key": {"doc_uid": "doc-1"},
                "buckets": [{"key": {"doc_uid": "doc-1"}, "doc_count": 5}],
            }
        }
    }

    def _search(*, index: str, body: dict, request_timeout: int | None = None) -> dict:
        call_count["n"] += 1
        fake_client.search_calls.append(deepcopy(body))
        if call_count["n"] == 1:
            return first_page
        raise RuntimeError("boom on page 2")

    fake_client.search = _search  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom on page 2"):
        ovs.scan_document_uids_composite(fake_client, "fred-vectors", page_size=1, strict=True)

    assert call_count["n"] == 2


def test_scan_document_uids_composite_non_strict_swallows_and_returns_empty_on_first_page_failure():
    mapping = ovs.build_vector_index_mapping(4)
    fake_client = FakeOpenSearchClient(index_name="fred-vectors", index_body=mapping)

    def _raise(*, index: str, body: dict, request_timeout: int | None = None) -> dict:
        raise RuntimeError("boom")

    fake_client.search = _raise  # type: ignore[method-assign]

    assert ovs.scan_document_uids_composite(fake_client, "fred-vectors", strict=False) == []
