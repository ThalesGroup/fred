# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""A stage uses only the models the Control Plane admitted for it."""

import pytest
from fred_knowledge.models import DocumentModels
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from knowledge_flow_worker.application_context import ApplicationContext
from knowledge_flow_worker.core.processors.input.common.image_describer import VisionImageDescriber, build_image_describer
from tests.model_admissions import extraction_models, indexing_models


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
