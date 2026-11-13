# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Knowledge Flow calls an admitted model only through a destination it attests itself."""

import asyncio
import json

import pytest
import httpx
from fred_sdk.contracts.weaver import InferenceAdmission, InferenceCredentialBinding

from fred_knowledge import models
from fred_knowledge.models import DocumentModelError, DocumentModels

ROOT = "https://models.invalid/v1"


def admission(options: dict | None = None, revision: int = 1, **connection) -> InferenceAdmission:
    return InferenceAdmission.model_validate(
        {
            "selection": {
                "key": {"source_id": "s", "upstream_model_id": "embed"},
                "source": "default",
                "options": options or {},
                "source_revision": revision,
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


def test_a_new_revision_builds_a_new_client(monkeypatch, built):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))
    first = documents.embeddings(admission())
    assert documents.embeddings(admission(revision=2)) is not first
    assert DocumentModels.identity(admission()) != DocumentModels.identity(admission(revision=2))


@pytest.mark.parametrize("wire", ["openai_chat", "openai_responses"])
def test_chat_follows_the_admitted_protocol_and_options_only(monkeypatch, wire):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))
    unset = documents.chat(admission(wire=wire))
    assert (unset.model_name, unset.openai_api_base, unset.use_responses_api) == ("embed", ROOT, wire == "openai_responses")
    # No client default replaces an option the Control Plane left unset.
    assert unset.temperature is None and "temperature" not in unset._get_request_payload([])
    chosen = documents.chat(admission({"temperature": 0.3, "top_p": 0.5}, wire=wire))
    assert (chosen.temperature, chosen.top_p) == (0.3, 0.5)


def test_a_gateway_header_is_refused_before_any_client(monkeypatch, built):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    monkeypatch.setenv("GATEWAY_KEY", "gateway")  # pragma: allowlist secret
    binding = InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY", gateway_key_env="GATEWAY_KEY")
    documents = DocumentModels((binding,))
    with pytest.raises(DocumentModelError, match="standard route"):
        documents.embeddings(admission(auth={"kind": "api_key", "gateway_key_header": "X-Gateway-Key"}))
    assert built == []


def test_rerank_uses_the_attested_endpoint_and_indices(monkeypatch):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))

    async def send(request, *, stream):
        assert request.url == f"{ROOT}/rerank"
        assert request.headers["Authorization"] == "Bearer secret"
        assert json.loads(request.content) == {"model": "embed", "query": "question", "documents": ["first", "second"], "top_n": 2}
        assert stream is True
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.9}]}, request=request)

    monkeypatch.setattr(documents._rerank_client, "send", send)

    async def check():
        assert await documents.rerank(admission(wire="rerank"), "question", ["first", "second"], 2) == [1, 0]
        await documents.close()

    asyncio.run(check())


def test_rerank_refuses_invalid_indices(monkeypatch):
    monkeypatch.setenv("LOCAL_KEY", "secret")  # pragma: allowlist secret
    documents = DocumentModels((InferenceCredentialBinding(credential_binding="b", api_root=ROOT, api_key_env="LOCAL_KEY"),))

    async def send(request, *, stream):
        return httpx.Response(200, json={"results": [{"index": 2, "relevance_score": 1.0}]}, request=request)

    monkeypatch.setattr(documents._rerank_client, "send", send)

    async def check():
        with pytest.raises(DocumentModelError, match="Invalid rerank response"):
            await documents.rerank(admission(wire="rerank"), "question", ["first"], 1)
        await documents.close()

    asyncio.run(check())
