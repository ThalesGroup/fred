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

"""`_model_capabilities_for_source` (OBSERV-02 v3, `AGENT-CAPABILITY-RFC.md`
§8.7) — the HTTP fetch + projection half of `kind="model"` capabilities.

The aggregation-layer union/collision-guard behavior is covered alongside
the rest of `aggregate_capability_catalog`'s suite in
test_capability_enablement_1980.py; this file covers only this one
function's own contract: parses a well-formed response into
CapabilityCatalogEntry(kind="model"), and degrades to None (never raises)
on an unreachable pod or malformed payload — the same best-effort contract
`_agent_capabilities_for_source` already has.
"""

from __future__ import annotations

import httpx
import pytest
from control_plane_backend.product.service import _model_capabilities_for_source


@pytest.mark.asyncio
async def test_parses_a_well_formed_models_catalog_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "models": [
            {
                "id": "model__openai__gpt-5.1",
                "provider": "openai",
                "name": "gpt-5.1",
                "description": "OpenAI GPT-5.1",
            },
            {
                "id": "model__ollama__mistral-latest",
                "provider": "ollama",
                "name": "mistral:latest",
                "description": None,
            },
        ]
    }

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is not None
    assert [e.id for e in entries] == [
        "model__openai__gpt-5.1",
        "model__ollama__mistral-latest",
    ]
    assert all(e.kind == "model" for e in entries)
    # A missing/None description falls back to the model name, never a blank
    # string — CapabilityCatalogEntry.description requires min_length=1.
    assert entries[1].description == "mistral:latest"


@pytest.mark.asyncio
async def test_carries_thinking_profile_ids_through_the_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """REASON-01 §5.3 — the derived per-profile aptitude reaches control-plane.

    Carried verbatim from the pod, same as `profile_ids`: this is what decides
    whether the admin row renders a reasoning control at all, so losing it here
    would silently hide the toggle for every reasoning-capable model.
    """

    payload = {
        "models": [
            {
                "id": "model__openai__mistral-small-latest",
                "provider": "openai",
                "name": "mistral-small-latest",
                "profile_ids": ["chat.mistral.small", "language.mistral.small"],
                "chat_profile_ids": ["chat.mistral.small"],
                "thinking_profile_ids": ["chat.mistral.small"],
            },
            {
                "id": "model__openai__gpt-4o",
                "provider": "openai",
                "name": "gpt-4o",
                "profile_ids": ["chat.openai.gpt4o"],
            },
        ]
    }

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is not None
    assert entries[0].model_profile_ids == (
        "chat.mistral.small",
        "language.mistral.small",
    )
    assert entries[0].model_chat_profile_ids == ("chat.mistral.small",)
    assert entries[0].model_thinking_profile_ids == ("chat.mistral.small",)
    # A pod that advertises no thinking profiles for a model (or a pre-REASON-01
    # pod that never sends the key) reads as "cannot reason" — no toggle, which
    # is the safe direction (§5.6).
    assert entries[1].model_thinking_profile_ids == ()
    assert entries[1].model_chat_profile_ids == ()


@pytest.mark.asyncio
async def test_carries_the_ops_authored_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The label ops authored reaches control-plane verbatim.

    Verbatim matters more here than for the derived fields: the string is
    shown to users as-is, so normalizing it would be a second opinion about a
    name ops already settled. A pod that sends none reads as None, leaving
    the frontend on its id-splitting heuristic — the previous behaviour.
    """

    payload = {
        "models": [
            {
                "id": "model__anthropic__claude-sonnet-4-6",
                "provider": "anthropic",
                "name": "claude-sonnet-4-6",
                "display_name": "Claude Sonnet 4.6",
            },
            {
                "id": "model__openai__gpt-4o",
                "provider": "openai",
                "name": "gpt-4o",
            },
        ]
    }

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is not None
    assert entries[0].model_display_name == "Claude Sonnet 4.6"
    assert entries[1].model_display_name is None
    # The technical name is untouched — routing, the capability id and the
    # admin table all still key on it.
    assert entries[0].name == "claude-sonnet-4-6"


@pytest.mark.asyncio
async def test_ignores_malformed_entries_without_crashing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "models": [
            {"id": "model__openai__gpt-5.1", "provider": "openai", "name": "gpt-5.1"},
            {"provider": "openai"},  # missing id/name — dropped, not fatal
            "not-even-a-dict",  # dropped, not fatal
        ]
    }

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=payload, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is not None
    assert [e.id for e in entries] == ["model__openai__gpt-5.1"]


@pytest.mark.asyncio
async def test_unreachable_pod_returns_none_not_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError(
            "connection refused", request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is None


@pytest.mark.asyncio
async def test_unreachable_pod_logs_at_warning_not_debug(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """GitHub #2191: this used to log at DEBUG, so a model-catalog outage was
    invisible at default log level while the sibling tool fetch
    (`_available_capabilities_for_source`) logs the equivalent failure at
    WARNING — matching that level here closes the visibility gap."""

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        raise httpx.ConnectError(
            "connection refused", request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    with caplog.at_level("WARNING", logger="control_plane_backend.product.service"):
        entries = await _model_capabilities_for_source("http://pod")

    assert entries is None
    assert any(
        record.levelname == "WARNING" and "models catalog" in record.message
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_pod_on_pre_2110_code_without_the_route_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pod that hasn't shipped GET /agents/models-catalog yet 404s — the
    same "not fatal, just absent this pass" contract as unreachable."""

    async def _fake_get(self, url, *args, **kwargs):  # noqa: ANN001
        request = httpx.Request("GET", url)
        return httpx.Response(404, request=request)

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)

    entries = await _model_capabilities_for_source("http://pod")

    assert entries is None
