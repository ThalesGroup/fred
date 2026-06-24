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
#
# Tests for the native Anthropic provider added in RUNTIME-07.

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_model
from fred_core.model.models import ModelProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_anthropic_module() -> tuple[ModuleType, list[dict[str, Any]]]:
    """Returns (fake_module, calls_list) where calls_list captures ctor kwargs."""
    calls: list[dict[str, Any]] = []

    class _FakeChatAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    fake_module = ModuleType("langchain_anthropic")
    setattr(fake_module, "ChatAnthropic", _FakeChatAnthropic)
    return fake_module, calls


def _anthropic_cfg(
    name: str = "claude-sonnet-4-5", settings: dict[str, Any] | None = None
) -> ModelConfiguration:
    return ModelConfiguration(provider="anthropic", name=name, settings=settings or {})


# ---------------------------------------------------------------------------
# Enum
# ---------------------------------------------------------------------------


def test_model_provider_has_anthropic_value() -> None:
    """ANTHROPIC must be registered in the ModelProvider enum."""
    assert ModelProvider.ANTHROPIC.value == "anthropic"


def test_anthropic_value_is_distinct_from_other_providers() -> None:
    values = [p.value for p in ModelProvider]
    assert values.count("anthropic") == 1


# ---------------------------------------------------------------------------
# get_model – validation errors
# ---------------------------------------------------------------------------


def test_get_model_anthropic_requires_name(monkeypatch: Any) -> None:
    """Missing model name must raise ValueError before touching the env."""
    cfg = ModelConfiguration(provider="anthropic", name=None, settings={})
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    with pytest.raises(ValueError, match="name"):
        get_model(cfg)


def test_get_model_anthropic_requires_api_key_env(monkeypatch: Any) -> None:
    """Missing ANTHROPIC_API_KEY must raise ValueError."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_model(_anthropic_cfg())


def test_get_model_anthropic_raises_import_error_when_package_missing(
    monkeypatch: Any,
) -> None:
    """When langchain_anthropic is not installed, ImportError with helpful message."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setitem(sys.modules, "langchain_anthropic", None)  # type: ignore[arg-type]
    with pytest.raises(ImportError, match="langchain-anthropic"):
        get_model(_anthropic_cfg())


# ---------------------------------------------------------------------------
# get_model – successful construction
# ---------------------------------------------------------------------------


def test_get_model_anthropic_constructs_chat_anthropic(monkeypatch: Any) -> None:
    """Happy-path: correct kwargs forwarded to ChatAnthropic."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    get_model(_anthropic_cfg("claude-haiku-3-5"))

    assert len(calls) == 1
    assert calls[0]["model"] == "claude-haiku-3-5"
    # base_url not in kwargs when not supplied
    assert "base_url" not in calls[0]


def test_get_model_anthropic_passes_base_url_when_set(monkeypatch: Any) -> None:
    """base_url in settings must be forwarded to ChatAnthropic."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    cfg = _anthropic_cfg(settings={"base_url": "https://synapse.example.com/v1"})
    get_model(cfg)

    assert calls[0]["base_url"] == "https://synapse.example.com/v1"


def test_get_model_anthropic_omits_base_url_when_empty(monkeypatch: Any) -> None:
    """An empty base_url string must NOT be forwarded (falsy guard)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    cfg = _anthropic_cfg(settings={"base_url": ""})
    get_model(cfg)

    assert "base_url" not in calls[0]


def test_get_model_anthropic_includes_chat_defaults(monkeypatch: Any) -> None:
    """temperature and max_retries defaults must be forwarded to ChatAnthropic."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    get_model(_anthropic_cfg())

    assert calls[0]["temperature"] == 0.0
    assert calls[0]["max_retries"] == 0


def test_get_model_anthropic_allows_temperature_override(monkeypatch: Any) -> None:
    """Explicit temperature in settings overrides the default of 0.0."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    cfg = _anthropic_cfg(settings={"temperature": 0.7})
    get_model(cfg)

    assert calls[0]["temperature"] == 0.7


def test_get_model_anthropic_base_url_not_in_settings_after_construction(
    monkeypatch: Any,
) -> None:
    """base_url should be popped from settings and not appear twice."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    fake_module, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake_module)

    cfg = _anthropic_cfg(settings={"base_url": "https://synapse.example.com/v1"})
    get_model(cfg)

    # base_url appears exactly once at top-level, not as a settings sub-key
    kwarg_keys = list(calls[0].keys())
    assert kwarg_keys.count("base_url") == 1
