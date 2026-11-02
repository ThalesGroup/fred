import fred_knowledge.vector.factory as app_context_module
from fred_knowledge.configuration import OpenSearchVectorIndexConfig
from langchain_community.embeddings import FakeEmbeddings

from knowledge_flow_backend.application_context import ApplicationContext

TEST_OPENSEARCH_PASSWORD = "test"  # pragma: allowlist secret


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
