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

"""
Offline unit tests for `fred_sdk.contracts.context`, scoped to the
platform-model-binding types added alongside the `ModelCapability` relocation
and the trusted-channel hardening that followed it:

- `ModelCapability` — relocated here from `fred_runtime.model_routing.contracts`
- `ModelBinding` — the narrower sibling of `ModelConfiguration` used for
  this feature's wire payload, restricted to a supported provider and a
  strict, non-secret-shaped settings allowlist (no credential/auth/header/
  cookie/client-object field — see `ModelBinding`'s own docstring for the
  precise guarantee)
- `BoundRuntimeContext.platform_chat_model_binding` — the TRUSTED field the
  runtime resolves itself per turn; `RuntimeContext` (client-forwarded) has
  no platform-binding field at all, by construction, so a forged/stale
  request body can no longer influence chat model selection.

There is no dedicated `test_context.py` predating this file — `RuntimeContext`
was previously only exercised as a generic fixture inside
`test_execution_contracts.py` (RUNTIME-07 rev. 2 request/response contracts,
unrelated to model routing). A new small file is a better fit than folding
these cases into that file: the subject here is `context.py`'s own types, not
the execution-request contract `test_execution_contracts.py` covers.

No mocks, no network, no filesystem side effects.
"""

from __future__ import annotations

from typing import Any

import pytest
from fred_core.model.models import ModelProvider
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ModelBinding,
    ModelBindingSettings,
    ModelCapability,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# ModelCapability — relocation sanity
# ---------------------------------------------------------------------------


def test_model_capability_values_unchanged() -> None:
    assert ModelCapability.CHAT.value == "chat"
    assert ModelCapability.LANGUAGE.value == "language"
    assert ModelCapability.EMBEDDING.value == "embedding"
    assert ModelCapability.IMAGE.value == "image"


# ---------------------------------------------------------------------------
# ModelBinding.provider — restricted to fred_core.model.models.ModelProvider
# ---------------------------------------------------------------------------

# The minimal settings each provider needs to construct successfully,
# mirroring exactly what `fred_core.model.factory.get_model()`'s own
# `_require_settings(...)` calls require per provider (see
# `_PROVIDER_REQUIRED_SETTINGS` in `context.py`). `openai`, `ollama`, and
# `anthropic` need nothing beyond the provider + non-empty `name` every
# binding already requires.
PROVIDER_MINIMAL_VALID_SETTINGS: dict[str, dict[str, Any]] = {
    "openai": {},
    "ollama": {},
    "anthropic": {},
    "azure-openai": {
        "azure_endpoint": "https://example.openai.azure.com",
        "azure_openai_api_version": "2024-05-01",
    },
    "azure-apim": {
        "azure_ad_client_id": "client-id",
        "azure_ad_client_scope": "scope",
        "azure_apim_base_url": "https://apim.example.internal",
        "azure_apim_resource_path": "/openai",
        "azure_openai_api_version": "2024-05-01",
        "azure_tenant_id": "tenant-id",
    },
    "vertex-ai": {"project": "proj-1", "location": "us-central1"},
    "vertex-ai-model-garden": {
        "project": "proj-1",
        "location": "us-central1",
        "model_family": "mistral",
    },
}


def test_model_binding_accepts_every_supported_provider() -> None:
    for provider in list(ModelProvider):
        binding = ModelBinding.model_validate(
            {
                "provider": provider.value,
                "name": "some-model",
                "settings": PROVIDER_MINIMAL_VALID_SETTINGS[provider.value],
            }
        )
        assert binding.provider == provider.value


@pytest.mark.parametrize(
    "provider",
    ["attacker", "mock", "mistral", "vertex", "azure", "gpt", "", "OpenAI"],
)
def test_model_binding_rejects_every_unsupported_provider(provider: str) -> None:
    with pytest.raises(ValidationError):
        ModelBinding(provider=provider, name="some-model")


def test_model_binding_json_schema_advertises_exact_provider_enum() -> None:
    """The generated JSON Schema (and therefore OpenAPI/generated TypeScript)
    must advertise exactly the providers `SupportedChatProvider` validates
    against — not a hand-maintained copy that can drift."""

    schema = ModelBinding.model_json_schema()
    assert schema["properties"]["provider"]["enum"] == [
        p.value for p in list(ModelProvider)
    ]


# ---------------------------------------------------------------------------
# ModelBinding — provider-specific required settings (mirrors
# fred_core.model.factory.get_model()'s own _require_settings(...) calls)
# ---------------------------------------------------------------------------

PROVIDER_REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("azure-openai", "azure_endpoint"),
    ("azure-openai", "azure_openai_api_version"),
    ("azure-apim", "azure_ad_client_id"),
    ("azure-apim", "azure_ad_client_scope"),
    ("azure-apim", "azure_apim_base_url"),
    ("azure-apim", "azure_apim_resource_path"),
    ("azure-apim", "azure_openai_api_version"),
    ("azure-apim", "azure_tenant_id"),
    ("vertex-ai", "project"),
    ("vertex-ai", "location"),
    ("vertex-ai-model-garden", "project"),
    ("vertex-ai-model-garden", "location"),
    ("vertex-ai-model-garden", "model_family"),
]


@pytest.mark.parametrize(
    "provider", ["azure-openai", "azure-apim", "vertex-ai", "vertex-ai-model-garden"]
)
def test_model_binding_rejects_provider_with_empty_settings(provider: str) -> None:
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": provider, "name": "some-model", "settings": {}}
        )


@pytest.mark.parametrize("provider,omitted_field", PROVIDER_REQUIRED_FIELDS)
def test_model_binding_rejects_provider_missing_one_required_field(
    provider: str, omitted_field: str
) -> None:
    settings = dict(PROVIDER_MINIMAL_VALID_SETTINGS[provider])
    settings.pop(omitted_field)
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": provider, "name": "some-model", "settings": settings}
        )


@pytest.mark.parametrize("provider,required_field", PROVIDER_REQUIRED_FIELDS)
def test_model_binding_rejects_provider_with_whitespace_only_required_field(
    provider: str, required_field: str
) -> None:
    if required_field in ("azure_endpoint", "azure_apim_base_url"):
        pytest.skip(
            "URL-typed field — whitespace is already rejected as a malformed URL"
        )
    if required_field == "model_family":
        pytest.skip(
            "model_family is a closed Literal — whitespace is not representable"
        )
    settings = dict(PROVIDER_MINIMAL_VALID_SETTINGS[provider])
    settings[required_field] = "   "
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": provider, "name": "some-model", "settings": settings}
        )


# ---------------------------------------------------------------------------
# ModelBinding.settings — ModelBindingSettings strict contract
# ---------------------------------------------------------------------------
#
# There is no deny-list validator anymore: `ModelBindingSettings` is a
# closed, typed allowlist (`extra="forbid"`) with no credential/auth/header/
# cookie/client-object field, so every forbidden shape below is rejected the
# same way any other unknown key would be — structurally, not heuristically.

REJECTED_SETTINGS_MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("api_key", {"api_key": "sk-not-a-real-key"}),  # pragma: allowlist secret
    ("APIToken", {"APIToken": "t"}),  # pragma: allowlist secret
    ("IDToken", {"IDToken": "t"}),  # pragma: allowlist secret
    ("APISecret", {"APISecret": "s"}),  # pragma: allowlist secret
    ("TLSKey", {"TLSKey": "k"}),  # pragma: allowlist secret
    ("headers", {"headers": {"X-Custom": "v"}}),
    ("headers.Authorization", {"headers": {"Authorization": "Bearer x"}}),
    ("cookies", {"cookies": {"session": "abc"}}),
    ("auth", {"auth": {"user": "u", "pass": "p"}}),
    ("client object", {"client": {"transport": "custom"}}),
    ("http_client", {"http_client": "opaque-handle"}),
    ("http_async_client", {"http_async_client": "opaque-handle"}),
    ("unknown extra key", {"totally_unknown_key": "anything"}),
    ("nested unknown object", {"totally_unknown_key": {"connect": 5, "nested": "x"}}),
    ("timeout (process-wide, pod-local only)", {"timeout": {"connect": 5}}),
    (
        "http_client_limits (process-wide, pod-local only)",
        {"http_client_limits": {"max_connections": 10}},
    ),
]


@pytest.mark.parametrize("label,forged_settings", REJECTED_SETTINGS_MATRIX)
def test_model_binding_settings_rejects_every_forbidden_shape(
    label: str, forged_settings: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": "openai", "name": "gpt-5", "settings": forged_settings}
        )


URL_REJECTED_MATRIX: list[tuple[str, str]] = [
    ("non-http(s) scheme", "ftp://internal.example/v1"),
    ("username userinfo", "https://admin@internal.example/v1"),
    (
        "password userinfo",
        "https://admin:" + "synthetic-value" + "@internal.example/v1",
    ),
    ("malformed URL", "not-a-url"),
    ("scheme only, no host", "https://"),
]


@pytest.mark.parametrize("label,url", URL_REJECTED_MATRIX)
def test_model_binding_settings_rejects_invalid_base_url(label: str, url: str) -> None:
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": "openai", "name": "gpt-5", "settings": {"base_url": url}}
        )


def test_model_binding_settings_accepts_valid_http_and_https_on_prem_urls() -> None:
    for url in ("http://on-prem.internal:8080/v1", "https://on-prem.internal/v1"):
        binding = ModelBinding.model_validate(
            {"provider": "openai", "name": "gpt-5", "settings": {"base_url": url}}
        )
        assert binding.settings.base_url == url


# ---------------------------------------------------------------------------
# ModelBindingSettings — type-preserving, fail-closed numeric/boolean fields:
# a value is rejected outright ("4096" for an int field, 1 for a bool field)
# rather than coerced.
# ---------------------------------------------------------------------------

REJECTED_TYPE_AND_RANGE_MATRIX: list[tuple[str, dict[str, Any]]] = [
    ("max_tokens as string", {"max_tokens": "4096"}),
    ("max_retries as bool", {"max_retries": True}),
    ("streaming as int", {"streaming": 1}),
    ("stream_usage as int", {"stream_usage": 0}),
    ("request_timeout as string", {"request_timeout": "5"}),
    ("temperature as bool", {"temperature": True}),
    ("top_p as string", {"top_p": "0.5"}),
    ("temperature non-finite (inf)", {"temperature": float("inf")}),
    ("top_p non-finite (nan)", {"top_p": float("nan")}),
    ("request_timeout non-finite (-inf)", {"request_timeout": float("-inf")}),
    ("request_timeout negative", {"request_timeout": -1.0}),
    ("max_retries negative", {"max_retries": -1}),
    ("max_tokens zero", {"max_tokens": 0}),
    ("max_tokens negative", {"max_tokens": -1}),
    ("top_p below range", {"top_p": -0.01}),
    ("top_p above range", {"top_p": 1.01}),
]


@pytest.mark.parametrize("label,forged_settings", REJECTED_TYPE_AND_RANGE_MATRIX)
def test_model_binding_settings_rejects_every_type_and_range_violation(
    label: str, forged_settings: dict[str, Any]
) -> None:
    with pytest.raises(ValidationError):
        ModelBinding.model_validate(
            {"provider": "openai", "name": "gpt-5", "settings": forged_settings}
        )


def test_model_binding_settings_accepts_the_boundary_values() -> None:
    """The exact values the matrix above rejects one unit outside of must
    still be accepted — proves the bounds are inclusive/exclusive where
    intended, not accidentally rejecting valid input too."""

    binding = ModelBinding.model_validate(
        {
            "provider": "openai",
            "name": "gpt-5",
            "settings": {
                "max_tokens": 1,
                "top_p": 0.0,
                "max_retries": 0,
                "request_timeout": 0.0,
            },
        }
    )
    assert binding.settings.max_tokens == 1
    assert binding.settings.top_p == 0.0
    assert binding.settings.max_retries == 0
    assert binding.settings.request_timeout == 0.0

    top_p_one = ModelBinding.model_validate(
        {"provider": "openai", "name": "gpt-5", "settings": {"top_p": 1.0}}
    )
    assert top_p_one.settings.top_p == 1.0


def test_model_binding_constructs_with_clean_settings() -> None:
    binding = ModelBinding.model_validate(
        {
            "provider": "openai",
            "name": "gpt-5",
            "settings": {"base_url": "https://example.internal", "temperature": 0.5},
        }
    )
    assert binding.provider == "openai"
    assert binding.name == "gpt-5"
    assert binding.settings.temperature == 0.5


def test_model_binding_defaults_to_empty_settings() -> None:
    binding = ModelBinding(provider="openai", name="gpt-5")
    assert binding.settings == ModelBindingSettings()


def test_model_binding_requires_non_empty_provider_and_name() -> None:
    with pytest.raises(ValidationError):
        ModelBinding(provider="", name="gpt-5")
    with pytest.raises(ValidationError):
        ModelBinding(provider="openai", name="")


def test_model_binding_is_frozen() -> None:
    binding = ModelBinding(provider="openai", name="gpt-5")
    with pytest.raises(Exception):
        binding.provider = "azure"  # type: ignore[misc]


def test_model_binding_settings_preserves_json_types_round_trip() -> None:
    """Boolean, integer, float, and string settings round-trip through
    construction and `model_dump(mode="json")` without cross-type coercion —
    the round trip the persistence boundary (control-plane's
    `PlatformModelBindingStore`) relies on. JSON's grammar itself has only a
    single numeric type; what's preserved here is pydantic's own strict
    int-vs-float validation (an int-shaped literal stays an int, a
    float-shaped literal stays a float on the way back in), not a distinction
    JSON carries on its own."""

    binding = ModelBinding.model_validate(
        {
            "provider": "openai",
            "name": "gpt-5",
            "settings": {
                "streaming": True,
                "max_tokens": 4096,
                "temperature": 0.2,
                "azure_openai_api_version": "2024-05-01",
                "reasoning_effort": "high",
            },
        }
    )
    dumped = binding.settings.model_dump(mode="json", exclude_none=True)
    assert dumped == {
        "streaming": True,
        "max_tokens": 4096,
        "temperature": 0.2,
        "azure_openai_api_version": "2024-05-01",
        "reasoning_effort": "high",
    }
    assert isinstance(dumped["streaming"], bool)
    assert isinstance(dumped["max_tokens"], int)
    assert isinstance(dumped["temperature"], float)

    restored = ModelBinding.model_validate(
        {"provider": "openai", "name": "gpt-5", "settings": dumped}
    )
    assert restored.settings == binding.settings


# ---------------------------------------------------------------------------
# RuntimeContext — platform binding is NOT a field
# ---------------------------------------------------------------------------


def test_runtime_context_has_no_platform_model_bindings_field() -> None:
    """The client-forwarded contract must not be able to express a platform
    binding at all — the whole point of moving it to `BoundRuntimeContext` is
    that no request-body content can ever set it. A forged
    `platform_model_bindings` key in incoming JSON is silently ignored by
    pydantic (unknown field), not accepted."""

    assert "platform_model_bindings" not in RuntimeContext.model_fields
    ctx = RuntimeContext.model_validate(
        {
            "session_id": "s-1",
            "platform_model_bindings": {"chat": {"provider": "x", "name": "y"}},
        }
    )
    assert not hasattr(ctx, "platform_model_bindings")
    assert ctx.session_id == "s-1"


# ---------------------------------------------------------------------------
# BoundRuntimeContext.platform_chat_model_binding — the trusted field
# ---------------------------------------------------------------------------


def _bound_context(
    *, platform_chat_model_binding: ModelBinding | None = None
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(),
        portable_context=PortableContext(
            request_id="r-1",
            correlation_id="r-1",
            actor="u-1",
            tenant="default",
            environment=PortableEnvironment.DEV,
        ),
        platform_chat_model_binding=platform_chat_model_binding,
    )


def test_bound_runtime_context_platform_chat_model_binding_defaults_to_none() -> None:
    bound = _bound_context()
    assert bound.platform_chat_model_binding is None


def test_bound_runtime_context_platform_chat_model_binding_round_trips() -> None:
    bound = _bound_context(
        platform_chat_model_binding=ModelBinding.model_validate(
            {
                "provider": "openai",
                "name": "gpt-4o-mini",
                "settings": {"temperature": 0.2},
            }
        )
    )
    dumped = bound.model_dump(mode="json")
    restored = BoundRuntimeContext.model_validate(dumped)
    assert restored.platform_chat_model_binding is not None
    assert restored.platform_chat_model_binding.provider == "openai"
    assert restored.platform_chat_model_binding.name == "gpt-4o-mini"
    assert restored.platform_chat_model_binding.settings == ModelBindingSettings(
        temperature=0.2
    )
