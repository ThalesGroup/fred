# Copyright Thales 2026
# Licensed under the Apache License, Version 2.0.

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fred_core.common import ModelConfiguration
from fred_core.model import factory
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from pydantic import SecretStr


@pytest.mark.parametrize("kind", ["chat", "embeddings"])
def test_explicit_openai_key_is_forwarded_without_global_key(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        factory,
        "get_shared_stack",
        lambda *_args, **_kwargs: (
            SimpleNamespace(timeout=httpx.Timeout(30), limits=httpx.Limits()),
            None,
            None,
        ),
    )
    captured: dict[str, Any] = {}

    class FakeWrapper:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        factory, "ChatOpenAI" if kind == "chat" else "OpenAIEmbeddings", FakeWrapper
    )
    cfg = ModelConfiguration(
        provider="openai",
        name="test-model",
        settings={"base_url": "https://example.test/v1"},
    )

    if kind == "chat":
        factory.get_model(
            cfg,
            openai_api_key="dedicated-key",  # pragma: allowlist secret
        )
    else:
        factory.get_embeddings(
            cfg,
            openai_api_key="dedicated-key",  # pragma: allowlist secret
        )

    assert captured["api_key"] == "dedicated-key"  # pragma: allowlist secret
    assert captured["openai_api_base"] == "https://example.test/v1"
    assert cfg.settings is not None
    assert "api_key" not in cfg.settings


@pytest.mark.parametrize("kind", ["chat", "embeddings"])
def test_default_openai_key_is_still_required(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = ModelConfiguration(provider="openai", name="test-model")

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        if kind == "chat":
            factory.get_model(cfg)
        else:
            factory.get_embeddings(cfg)


def test_real_openai_wrappers_keep_separate_explicit_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = ModelConfiguration(provider="openai", name="test-model")

    chat = factory.get_model(cfg, openai_api_key="chat-key")
    embeddings = factory.get_embeddings(cfg, openai_api_key="embedding-key")

    assert isinstance(chat, ChatOpenAI)
    assert isinstance(embeddings, OpenAIEmbeddings)
    assert isinstance(chat.openai_api_key, SecretStr)
    assert isinstance(embeddings.openai_api_key, SecretStr)
    assert chat.openai_api_key.get_secret_value() == "chat-key"
    assert embeddings.openai_api_key.get_secret_value() == "embedding-key"


def test_real_openai_wrappers_retain_global_key_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key")
    cfg = ModelConfiguration(provider="openai", name="test-model")

    chat = factory.get_model(cfg)
    embeddings = factory.get_embeddings(cfg)

    assert isinstance(chat, ChatOpenAI)
    assert isinstance(embeddings, OpenAIEmbeddings)
    assert isinstance(chat.openai_api_key, SecretStr)
    assert isinstance(embeddings.openai_api_key, SecretStr)
    assert chat.openai_api_key.get_secret_value() == "fallback-key"
    assert embeddings.openai_api_key.get_secret_value() == "fallback-key"


@pytest.mark.parametrize("kind", ["chat", "embeddings"])
def test_explicit_openai_key_does_not_change_ollama_auth(
    kind: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        factory,
        "get_shared_stack",
        lambda *_args, **_kwargs: (
            SimpleNamespace(timeout=httpx.Timeout(30), limits=httpx.Limits()),
            None,
            None,
        ),
    )
    captured: dict[str, Any] = {}

    class FakeWrapper:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(
        factory, "ChatOllama" if kind == "chat" else "OllamaEmbeddings", FakeWrapper
    )
    cfg = ModelConfiguration(provider="ollama", name="test-model")

    if kind == "chat":
        factory.get_model(cfg, openai_api_key="unused-key")  # pragma: allowlist secret
    else:
        factory.get_embeddings(
            cfg,
            openai_api_key="unused-key",  # pragma: allowlist secret
        )

    assert "api_key" not in captured
