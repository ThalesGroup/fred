# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""A stage uses only the models the Control Plane admitted for it."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fred_knowledge.models import DocumentModels
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from knowledge_flow_worker import application_context
from knowledge_flow_worker.application_context import ApplicationContext
from knowledge_flow_worker.core.processors.input.common.image_describer import VisionImageDescriber, build_image_describer
from knowledge_flow_worker.features.manager_processing.contracts import StageModels
from tests.model_admissions import admission, extraction_models, indexing_models


def test_images_are_described_only_with_the_admitted_vision_model(monkeypatch):
    built = []
    monkeypatch.setattr(DocumentModels, "chat", lambda self, admission: built.append(admission) or FakeListChatModel(responses=["x"]))
    context = ApplicationContext.get_instance()
    assert build_image_describer() is None
    context.admit_models(extraction_models("vision-x"))
    describer = build_image_describer()
    assert isinstance(describer, VisionImageDescriber)
    assert context.get_vision()[1] == "vision-x"
    assert [a.selection.key.upstream_model_id for a in built] == ["vision-x"]
    # The next stage's admission replaces it: no model survives from another organization.
    context.admit_models(extraction_models())
    assert build_image_describer() is None


def test_indexing_embeds_only_with_the_admitted_corpus_model():
    context = ApplicationContext.get_instance()
    with pytest.raises(RuntimeError, match="No embedding model was admitted"):
        context.get_embedder()
    context.admit_models(indexing_models())
    assert context.get_embedder() is not None


@pytest.fixture
def corpus_stores(monkeypatch):
    """Corpus stores built by the context, without a vector backend."""
    built = []

    def build(embedder, store, *, organization_id, embedding_model_name, **_):
        built.append(SimpleNamespace(embedder=embedder, organization_id=organization_id, model=embedding_model_name))
        return built[-1]

    context = application_context.get_app_context()
    monkeypatch.setattr(context.configuration, "manager_processing", SimpleNamespace(vector_store=None))
    monkeypatch.setattr(context, "_corpus_stores", {})
    monkeypatch.setattr(application_context, "build_vector_store", build)
    monkeypatch.setattr(context, "get_text_splitter", lambda: None)
    monkeypatch.setattr(context, "get_kpi_writer", lambda: None)
    return context, built


def test_a_new_admission_is_never_served_by_a_cached_corpus_client(corpus_stores):
    context, built = corpus_stores
    organization = uuid4()
    context.admit_models(indexing_models())
    first = context.get_corpus_store(organization)
    assert context.get_corpus_store(organization) is first
    assert first.embedder is context.get_embedder()
    # The same offer under a new source revision is another admitted client.
    revised = admission().model_copy(update={"selection": admission().selection.model_copy(update={"source_revision": 2})})
    context.admit_models(StageModels(embedding=revised, vision=None))
    second = context.get_corpus_store(organization)
    assert second is not first and second.embedder is context.get_embedder()
    assert second.embedder is not first.embedder


def test_two_organizations_keep_their_own_corpus_and_embedding(corpus_stores):
    context, built = corpus_stores
    acme, globex = uuid4(), uuid4()
    context.admit_models(StageModels(embedding=admission("acme-embed"), vision=None))
    a = context.get_corpus_store(acme)
    context.admit_models(StageModels(embedding=admission("globex-embed"), vision=None))
    g = context.get_corpus_store(globex)
    assert (a.organization_id, a.model) == (acme, "acme-embed")
    assert (g.organization_id, g.model) == (globex, "globex-embed")
    assert a.embedder is not g.embedder
    # Maintenance needs no admitted model and never reuses an indexing client.
    context.admit_models(StageModels(embedding=None, vision=None))
    maintenance = context.get_corpus_store(acme)
    assert maintenance is not a and maintenance.embedder is None
