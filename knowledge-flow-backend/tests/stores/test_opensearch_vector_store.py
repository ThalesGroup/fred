from __future__ import annotations

from copy import deepcopy

import pytest
from langchain_community.embeddings import FakeEmbeddings
from langchain_core.embeddings import Embeddings

from knowledge_flow_backend import application_context as app_context_module
from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.common.structures import OpenSearchVectorIndexConfig
from knowledge_flow_backend.core.stores.vector import opensearch_vector_store as ovs


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
        password="secret",
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
        password="secret",
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
            password="secret",
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
    ctx.configuration.storage.opensearch.password = "secret"

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
