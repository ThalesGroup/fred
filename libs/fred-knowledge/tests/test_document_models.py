# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Knowledge Flow calls an admitted model only through a destination it attests itself."""

import pytest
from fred_sdk.contracts.weaver import InferenceAdmission, InferenceCredentialBinding

from fred_knowledge import models
from fred_knowledge.models import DocumentModelError, DocumentModels

ROOT = "https://models.invalid/v1"


def admission(**connection) -> InferenceAdmission:
    return InferenceAdmission.model_validate(
        {
            "selection": {
                "key": {"source_id": "s", "upstream_model_id": "embed"},
                "source": "default",
                "options": {},
                "source_revision": 1,
                "snapshot_revision": 1,
                "policy_revision": 1,
            },
            "connection": {
                "credential_binding": "b",
                "api_root": ROOT,
                "wire": "openai_chat",
                "route": "standard",
                "dialect": "mistral",
                "auth": {"kind": "api_key"},
                **connection,
            },
        }
    )


@pytest.fixture
def built(monkeypatch):
    calls = []
    monkeypatch.setattr(models, "get_embeddings", lambda config, inference_api_key: calls.append((config, inference_api_key)) or object())
    return calls


def test_the_local_key_reaches_only_the_attested_destination(monkeypatch, built):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))
    first = documents.embeddings(admission())
    assert documents.embeddings(admission()) is first, "one client per admitted offer"
    config, key = built[0]
    assert (config.name, config.settings["base_url"], key.get_secret_value()) == ("embed", ROOT, "secret")
    # Non-OpenAI dialects skip OpenAI's tokenizer-based length check.
    assert config.settings["check_embedding_ctx_length"] is False


@pytest.mark.parametrize(
    "connection",
    [
        {"credential_binding": "other"},
        {"api_root": "https://elsewhere.invalid/v1"},
        {"auth": {"kind": "none"}},
    ],
)
def test_an_unattested_connection_is_refused(monkeypatch, built, connection):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))
    with pytest.raises(DocumentModelError, match="not attested"):
        documents.embeddings(admission(**connection))
    assert built == []


def test_unsupported_forms_and_missing_keys_are_explicit(monkeypatch, built):
    monkeypatch.delenv("LOCAL_KEY", raising=False)
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))
    with pytest.raises(DocumentModelError, match="credential is unavailable"):
        documents.embeddings(admission())
    with pytest.raises(DocumentModelError, match="standard route"):
        documents.embeddings(admission(route="azure_deployment", api_version="2024-10-21"))
    assert built == []
