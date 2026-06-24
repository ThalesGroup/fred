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

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from fred_core.common import ModelConfiguration
from fred_core.model.factory import _apply_anthropic_auth, get_model


def _make_fake_anthropic_module() -> tuple[ModuleType, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    class _FakeChatAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs)

    fake = ModuleType("langchain_anthropic")
    setattr(fake, "ChatAnthropic", _FakeChatAnthropic)
    return fake, calls


def test_anthropic_api_key_no_bearer(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    cfg = ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5", settings={})
    model = get_model(cfg)

    assert isinstance(model, fake.ChatAnthropic)
    assert calls[0]["model"] == "claude-sonnet-4-5"
    assert "default_headers" not in calls[0]


def test_anthropic_auth_token_injects_bearer(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "my-gateway-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    cfg = ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5", settings={})
    get_model(cfg)

    assert calls[0]["default_headers"] == {"Authorization": "Bearer my-gateway-token"}


def test_anthropic_base_url_from_settings(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.gateway/")

    cfg = ModelConfiguration(
        provider="anthropic",
        name="claude-sonnet-4-5",
        settings={"base_url": "https://explicit.gateway/"},
    )
    get_model(cfg)

    assert calls[0]["base_url"] == "https://explicit.gateway/"


def test_anthropic_base_url_from_env(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://env.gateway/")

    cfg = ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5", settings={})
    get_model(cfg)

    assert calls[0]["base_url"] == "https://env.gateway/"


def test_anthropic_no_base_url(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    cfg = ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5", settings={})
    get_model(cfg)

    assert "base_url" not in calls[0]


def test_anthropic_missing_name_raises(monkeypatch: Any) -> None:
    fake, _ = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "tok")

    cfg = ModelConfiguration(provider="anthropic", name=None, settings={})
    with pytest.raises(ValueError, match="name"):
        get_model(cfg)


def test_anthropic_no_auth_raises(monkeypatch: Any) -> None:
    fake, _ = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    cfg = ModelConfiguration(provider="anthropic", name="claude-sonnet-4-5", settings={})
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        get_model(cfg)


def test_anthropic_explicit_api_key_escape_hatch(monkeypatch: Any) -> None:
    fake, calls = _make_fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "langchain_anthropic", fake)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "gateway-token")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    cfg = ModelConfiguration(
        provider="anthropic",
        name="claude-sonnet-4-5",
        settings={"api_key": "direct-sk-ant"},
    )
    get_model(cfg)

    assert "default_headers" not in calls[0]
    assert calls[0]["api_key"] == "direct-sk-ant"


# ---------------------------------------------------------------------------
# Direct tests of _apply_anthropic_auth helper
# ---------------------------------------------------------------------------


def test_apply_anthropic_auth_bearer_mode(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "bearer-tok")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    settings: dict[str, Any] = {}
    _apply_anthropic_auth(settings)
    assert settings == {"default_headers": {"Authorization": "Bearer bearer-tok"}}


def test_apply_anthropic_auth_api_key_mode(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xyz")
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    settings: dict[str, Any] = {}
    _apply_anthropic_auth(settings)
    assert settings == {}


def test_apply_anthropic_auth_escape_hatch_api_key(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ignored-token")
    settings: dict[str, Any] = {"api_key": "explicit"}
    _apply_anthropic_auth(settings)
    assert "default_headers" not in settings


def test_apply_anthropic_auth_escape_hatch_headers(monkeypatch: Any) -> None:
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "ignored-token")
    settings: dict[str, Any] = {"default_headers": {"X-Custom": "val"}}
    _apply_anthropic_auth(settings)
    assert settings["default_headers"] == {"X-Custom": "val"}
