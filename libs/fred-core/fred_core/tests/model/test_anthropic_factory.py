# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Offline unit tests for the anthropic factory branch (RUNTIME-07).

Fake ChatAnthropic injected via sys.modules — no network, no real SDK required.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_model


# ---------------------------------------------------------------------------
# Fake ChatAnthropic
# ---------------------------------------------------------------------------


class _FakeChatAnthropic:
    """Captures kwargs passed to ChatAnthropic constructor."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs

    def captured(self) -> dict[str, Any]:
        return dict(self._kwargs)


def _inject_fake_anthropic(monkeypatch: Any) -> list[dict[str, Any]]:
    """Inject a fake langchain_anthropic module and return the call-capture list."""
    calls: list[dict[str, Any]] = []

    class _CapturingFakeChatAnthropic(_FakeChatAnthropic):
        def __init__(self, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            calls.append(dict(kwargs))

    fake_module = ModuleType("langchain_anthropic")
    setattr(fake_module, "ChatAnthropic", _CapturingFakeChatAnthropic)
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)
    return calls


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(
    name: str = "claude-sonnet-4-5", settings: dict[str, Any] | None = None
) -> ModelConfiguration:
    return ModelConfiguration(provider="anthropic", name=name, settings=settings or {})


# ---------------------------------------------------------------------------
# Basic construction
# ---------------------------------------------------------------------------


def test_constructs_chat_anthropic(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    get_model(_cfg())

    assert len(calls) == 1
    assert calls[0]["model_name"] == "claude-sonnet-4-5"
    # http_client/http_async_client must NOT be passed — ChatAnthropic rejects them
    assert "http_client" not in calls[0]
    assert "http_async_client" not in calls[0]
    # timeout must be a plain float — ChatAnthropic rejects httpx.Timeout objects
    assert isinstance(calls[0]["timeout"], (float, int, type(None)))


def test_missing_name_raises_value_error(monkeypatch: Any) -> None:
    _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(ValueError, match="'name'"):
        get_model(ModelConfiguration(provider="anthropic", name=None, settings={}))


# ---------------------------------------------------------------------------
# base_url precedence
# ---------------------------------------------------------------------------


def test_base_url_from_settings_wins_over_env(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example.com")

    get_model(_cfg(settings={"base_url": "https://settings.example.com"}))

    assert calls[0].get("base_url") == "https://settings.example.com"


def test_base_url_from_env_when_settings_omits_it(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.example.com")

    get_model(_cfg())

    assert calls[0].get("base_url") == "https://env.example.com"


def test_no_base_url_kwarg_when_neither_source_set(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    get_model(_cfg())

    assert "base_url" not in calls[0]


# ---------------------------------------------------------------------------
# Auth mode A — ANTHROPIC_AUTH_TOKEN (gateway bearer)
# ---------------------------------------------------------------------------


def test_auth_token_injects_authorization_header(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "my-gateway-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    get_model(_cfg())

    assert calls[0].get("default_headers") == {
        "Authorization": "Bearer my-gateway-token"
    }
    # api_key must NOT be injected
    assert "api_key" not in calls[0]


# ---------------------------------------------------------------------------
# Auth mode B — ANTHROPIC_API_KEY (direct API)
# ---------------------------------------------------------------------------


def test_api_key_mode_no_authorization_header(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-api-key")

    get_model(_cfg())

    assert "default_headers" not in calls[0]
    assert "api_key" not in calls[0]


# ---------------------------------------------------------------------------
# Escape hatch — explicit settings.default_headers / api_key preserved
# ---------------------------------------------------------------------------


def test_explicit_default_headers_not_overridden(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ignored-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    custom_headers = {"X-Custom": "value"}

    get_model(_cfg(settings={"default_headers": custom_headers}))

    assert calls[0].get("default_headers") == custom_headers


def test_explicit_api_key_in_settings_not_overridden(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ignored-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    get_model(_cfg(settings={"api_key": "explicit-key"}))

    assert calls[0].get("api_key") == "explicit-key"
    assert "default_headers" not in calls[0]


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_missing_both_auth_inputs_raises_value_error(monkeypatch: Any) -> None:
    _inject_fake_anthropic(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_model(_cfg())


def test_missing_langchain_anthropic_raises_import_error(monkeypatch: Any) -> None:
    monkeypatch.delitem(sys.modules, "langchain_anthropic", raising=False)
    # Patch import to raise ImportError
    import builtins

    real_import = builtins.__import__

    def _mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "langchain_anthropic":
            raise ImportError("No module named 'langchain_anthropic'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _mock_import)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    with pytest.raises(ImportError, match="langchain-anthropic"):
        get_model(_cfg())


# ---------------------------------------------------------------------------
# No OpenAI shims applied to Anthropic
# ---------------------------------------------------------------------------


def test_no_openai_api_base_in_kwargs(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    get_model(_cfg(settings={"base_url": "https://gateway.example.com"}))

    assert "openai_api_base" not in calls[0]


def test_no_streaming_kwarg_forced(monkeypatch: Any) -> None:
    calls = _inject_fake_anthropic(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

    get_model(_cfg())

    # The OpenAI stream_usage/streaming defaults must NOT be injected for Anthropic.
    assert "stream_usage" not in calls[0]
    assert "streaming" not in calls[0]
