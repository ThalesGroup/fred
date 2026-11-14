# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

import uuid

import pytest
from fred_core.common import ModelConfiguration

from knowledge_flow_backend.common.model_api_keys import ModelRole, api_key_for_role, openai_api_key_for_model


@pytest.mark.parametrize(
    ("role", "variable"),
    [
        ("chat", "KNOWLEDGE_FLOW_CHAT_API_KEY"),
        ("vision", "KNOWLEDGE_FLOW_VISION_API_KEY"),
        ("embeddings", "KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY"),
        ("ocr", "KNOWLEDGE_FLOW_OCR_API_KEY"),
    ],
)
def test_role_key_overrides_fallback_and_blank_uses_fallback(role: ModelRole, variable: str, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ModelConfiguration(provider="openai", name="test-model")
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    monkeypatch.setenv(variable, "dedicated-key")
    assert openai_api_key_for_model(cfg, role) == "dedicated-key"

    monkeypatch.setenv(variable, "  ")
    assert openai_api_key_for_model(cfg, role) == "fallback-key"

    monkeypatch.delenv(variable)
    assert openai_api_key_for_model(cfg, role) == "fallback-key"


@pytest.mark.parametrize("role", ["chat", "vision", "embeddings", "ocr"])
def test_missing_keys_name_both_options(role: ModelRole, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = ModelConfiguration(provider="openai", name="test-model")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv(f"KNOWLEDGE_FLOW_{role.upper()}_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY") as error:
        openai_api_key_for_model(cfg, role)

    assert f"KNOWLEDGE_FLOW_{role.upper()}_API_KEY" in str(error.value)


def test_other_provider_does_not_require_openai_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = ModelConfiguration(provider="ollama", name="test-model")

    assert openai_api_key_for_model(cfg, "chat") is None


def test_reranker_key_precedence_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    preferred_key = str(uuid.uuid4())
    dedicated_key = str(uuid.uuid4())
    global_key = str(uuid.uuid4())
    monkeypatch.setenv("CUSTOM_RERANKER_KEY", preferred_key)
    monkeypatch.setenv("KNOWLEDGE_FLOW_RERANKER_API_KEY", dedicated_key)
    monkeypatch.setenv("OPENAI_API_KEY", global_key)

    assert api_key_for_role("reranker", preferred_variable="CUSTOM_RERANKER_KEY") == preferred_key
    monkeypatch.setenv("CUSTOM_RERANKER_KEY", "  ")
    assert api_key_for_role("reranker", preferred_variable="CUSTOM_RERANKER_KEY") == dedicated_key
    monkeypatch.setenv("KNOWLEDGE_FLOW_RERANKER_API_KEY", "  ")
    assert api_key_for_role("reranker", preferred_variable="CUSTOM_RERANKER_KEY") == global_key
    assert api_key_for_role("reranker") == global_key


def test_reranker_missing_keys_name_all_options(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("CUSTOM_RERANKER_KEY", "KNOWLEDGE_FLOW_RERANKER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ValueError, match="Missing API key for reranker model") as error:
        api_key_for_role("reranker", preferred_variable="CUSTOM_RERANKER_KEY")

    for variable in ("CUSTOM_RERANKER_KEY", "KNOWLEDGE_FLOW_RERANKER_API_KEY", "OPENAI_API_KEY"):
        assert variable in str(error.value)
