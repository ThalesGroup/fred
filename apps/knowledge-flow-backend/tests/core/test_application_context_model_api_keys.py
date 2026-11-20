# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Any

import pytest
from fred_core.common import ModelConfiguration

from knowledge_flow_backend import application_context as context_module
from knowledge_flow_backend.application_context import ApplicationContext


def test_model_factories_receive_distinct_keys(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    monkeypatch.setenv("KNOWLEDGE_FLOW_CHAT_API_KEY", "chat-key")
    monkeypatch.setenv("KNOWLEDGE_FLOW_VISION_API_KEY", "vision-key")
    monkeypatch.setenv("KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY", "embedding-key")
    app_context.configuration.vision_model = ModelConfiguration(provider="openai", name="vision-model")
    app_context._embedder_instance = None
    calls: list[tuple[str, str | None]] = []
    overlap = Barrier(2)

    def fake_model(_cfg: ModelConfiguration, *, openai_api_key: str | None = None) -> Any:
        overlap.wait(timeout=5)
        assert context_module.os.environ["OPENAI_API_KEY"] == "fallback-key"  # pragma: allowlist secret
        calls.append(("chat", openai_api_key))
        return object()

    def fake_embeddings(_cfg: ModelConfiguration, *, openai_api_key: str | None = None) -> Any:
        calls.append(("embeddings", openai_api_key))
        return object()

    monkeypatch.setattr(context_module, "get_model", fake_model)
    monkeypatch.setattr(context_module, "get_embeddings", fake_embeddings)
    environment_before = dict(context_module.os.environ)

    with ThreadPoolExecutor(max_workers=2) as executor:
        chat = executor.submit(app_context.get_utility_model)
        vision = executor.submit(app_context.get_vision_model)
        chat.result()
        vision.result()
    app_context.get_embedder()

    assert set(calls) == {
        ("chat", "chat-key"),
        ("chat", "vision-key"),
        ("embeddings", "embedding-key"),
    }
    assert dict(context_module.os.environ) == environment_before


def test_embedding_key_permits_startup_without_global_key(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("KNOWLEDGE_FLOW_EMBEDDINGS_API_KEY", "embedding-key")
    monkeypatch.setattr(ApplicationContext, "_instance", None)

    context = ApplicationContext(app_context.configuration.model_copy(deep=True))

    assert isinstance(context, ApplicationContext)


def test_only_global_key_reaches_all_model_factories(app_context: ApplicationContext, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    for role in ("CHAT", "VISION", "EMBEDDINGS"):
        monkeypatch.delenv(f"KNOWLEDGE_FLOW_{role}_API_KEY", raising=False)
    app_context.configuration.vision_model = ModelConfiguration(provider="openai", name="vision-model")
    app_context._embedder_instance = None
    keys: list[str | None] = []

    def fake_factory(_cfg: ModelConfiguration, *, openai_api_key: str | None = None) -> Any:
        keys.append(openai_api_key)
        return object()

    monkeypatch.setattr(context_module, "get_model", fake_factory)
    monkeypatch.setattr(context_module, "get_embeddings", fake_factory)

    app_context.get_utility_model()
    app_context.get_vision_model()
    app_context.get_embedder()

    assert keys == ["fallback-key"] * 3
