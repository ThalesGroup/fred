from uuid import UUID

import fred_knowledge.vector.factory as factory_module
from fred_knowledge.configuration import OpenSearchVectorIndexConfig
from fred_sdk.contracts.weaver import InferenceAdmission
from langchain_community.embeddings import FakeEmbeddings

from knowledge_flow_backend.application_context import ApplicationContext

TEST_OPENSEARCH_PASSWORD = "test"  # pragma: allowlist secret
ORGANIZATION = UUID(int=7)


def admission() -> InferenceAdmission:
    return InferenceAdmission.model_validate(
        {
            "selection": {"key": {"source_id": "s", "upstream_model_id": "embed"}, "source": "default", "options": {}, "source_revision": 1, "snapshot_revision": 1, "policy_revision": 1},
            "connection": {"credential_binding": "b", "api_root": "https://models.invalid/v1", "wire": "openai_chat", "route": "standard", "dialect": "mistral", "auth": {"kind": "none"}},
        }
    )


def test_each_organization_searches_its_own_read_only_corpus(app_context, monkeypatch):
    ctx = ApplicationContext.get_instance()
    ctx.configuration.storage.vector_store = OpenSearchVectorIndexConfig(type="opensearch", index="fred-vectors")
    ctx.configuration.storage.opensearch.password = TEST_OPENSEARCH_PASSWORD

    created: list[dict] = []

    class DummyStore:
        def __init__(self, **kwargs) -> None:
            created.append(kwargs)

        def validate_index_or_fail(self) -> None:
            raise AssertionError("validate_index_or_fail should not be called")

    monkeypatch.setattr(factory_module, "OpenSearchVectorStoreAdapter", DummyStore)
    monkeypatch.setattr(ctx, "get_kpi_writer", lambda: None)
    monkeypatch.setattr(ctx.get_document_models(), "embeddings", lambda _: FakeEmbeddings(size=6))

    store = ctx.get_corpus_store(ORGANIZATION, admission())

    assert isinstance(store, DummyStore)
    assert ctx.get_corpus_store(ORGANIZATION, admission()) is store
    assert len(created) == 1
    assert created[0]["index"] == f"fred-vectors-{ORGANIZATION}"
    assert created[0]["read_only"] is True
    assert created[0]["embedding_model_name"] == "embed"
