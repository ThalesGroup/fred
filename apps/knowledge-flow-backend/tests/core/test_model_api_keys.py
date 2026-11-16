# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

import uuid

import pytest

from knowledge_flow_backend.common.model_api_keys import reranker_api_key


def test_reranker_key_precedence_and_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    dedicated_key = str(uuid.uuid4())
    global_key = str(uuid.uuid4())
    monkeypatch.setenv("KNOWLEDGE_FLOW_RERANKER_API_KEY", dedicated_key)
    monkeypatch.setenv("OPENAI_API_KEY", global_key)

    assert reranker_api_key() == dedicated_key
    monkeypatch.setenv("KNOWLEDGE_FLOW_RERANKER_API_KEY", "  ")
    assert reranker_api_key() == global_key
    monkeypatch.delenv("KNOWLEDGE_FLOW_RERANKER_API_KEY")
    assert reranker_api_key() == global_key


def test_reranker_missing_keys_name_all_options(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("KNOWLEDGE_FLOW_RERANKER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ValueError, match="Missing API key for reranker model") as error:
        reranker_api_key()

    for variable in ("KNOWLEDGE_FLOW_RERANKER_API_KEY", "OPENAI_API_KEY"):
        assert variable in str(error.value)
