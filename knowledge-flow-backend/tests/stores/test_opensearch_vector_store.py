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

    def close(self) -> None:
        return None


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
    assert FakeVectorSearch.created[0].calls == [
        (5, ["cid-0", "cid-1", "cid-2", "cid-3", "cid-4"]),
        (2, ["cid-0", "cid-1"]),
        (3, ["cid-2", "cid-3", "cid-4"]),
        (1, ["cid-2"]),
        (2, ["cid-3", "cid-4"]),
    ]


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
