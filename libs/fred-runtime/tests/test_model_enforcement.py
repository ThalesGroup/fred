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
kind="model" runtime enforcement (OBSERV-02 v3, `AGENT-CAPABILITY-RFC.md` §8.7):

- `RoutedChatModelFactory.build_for_chat`'s fail-closed gate against
  `BoundRuntimeContext.usable_model_ids`.
- `usable_model_capability_ids` — the pod-side ReBAC query computed once per
  turn, mirroring control-plane's `usable_capability_ids`.
"""

# pyright: reportArgumentType=false
# ^ `definition` is a plain SimpleNamespace exposing only `.agent_id` — the
#   one attribute `RoutedChatModelFactory.select()` actually reads — not a
#   real (abstract) AgentDefinition. Same convention as the control-plane
#   suite's lightweight-fake-in-place-of-real-protocol tests.
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from conftest import ToolFriendlyFakeChatModel
from fred_core.common import ModelConfiguration
from fred_runtime.model_routing.authz import usable_model_capability_ids
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelNotUsableError,
    ModelProfile,
    ModelRoutingPolicy,
)
from fred_runtime.model_routing.provider import ModelProvider, RoutedChatModelFactory
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.capability.manifest import model_capability_id

# ---------------------------------------------------------------------------
# 1. RoutedChatModelFactory.build_for_chat — fail-closed gate
# ---------------------------------------------------------------------------


class _FakeProvider(ModelProvider):
    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> Any:
        return ToolFriendlyFakeChatModel(responses=[])


def _factory() -> RoutedChatModelFactory:
    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "p1"},
        profiles=(
            ModelProfile(
                profile_id="p1",
                capability=ModelCapability.CHAT,
                model=ModelConfiguration(provider="openai", name="gpt-5.1"),
            ),
        ),
    )
    return RoutedChatModelFactory(
        resolver=ModelRoutingResolver(policy), provider=_FakeProvider()
    )


def _binding(usable_model_ids: tuple[str, ...] | None) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(team_id="team-a", user_id="u1"),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="r1",
            actor="u1",
            tenant="default",
            environment=PortableEnvironment.DEV,
            team_id="team-a",
            user_id="u1",
        ),
        usable_model_ids=usable_model_ids,
    )


_DEFINITION = SimpleNamespace(agent_id="test-agent")


def test_usable_model_ids_none_means_no_restriction() -> None:
    # ReBAC disabled/not computed — same dev-permissive posture as every
    # other pod-side check.
    model, selection = _factory().build_for_chat(
        definition=_DEFINITION,
        binding=_binding(None),
        purpose="chat",
        operation=None,
    )
    assert model is not None
    assert selection.model.provider == "openai"


def test_allowed_model_resolves_normally() -> None:
    allowed_id = model_capability_id("openai", "gpt-5.1")
    model, _ = _factory().build_for_chat(
        definition=_DEFINITION,
        binding=_binding((allowed_id,)),
        purpose="chat",
        operation=None,
    )
    assert model is not None


def test_disallowed_model_fails_closed() -> None:
    # The team's usable set does not contain this profile's model at all.
    with pytest.raises(ModelNotUsableError) as exc_info:
        _factory().build_for_chat(
            definition=_DEFINITION,
            binding=_binding(("model__azure__gpt-4o",)),
            purpose="chat",
            operation=None,
        )
    assert exc_info.value.capability_id == model_capability_id("openai", "gpt-5.1")


def test_empty_usable_set_denies_everything() -> None:
    # Distinguishes "ReBAC active, zero models granted" from "not computed".
    with pytest.raises(ModelNotUsableError):
        _factory().build_for_chat(
            definition=_DEFINITION,
            binding=_binding(()),
            purpose="chat",
            operation=None,
        )


def test_build_for_operation_also_enforces() -> None:
    # build() and build_for_operation() both funnel through build_for_chat —
    # confirming the gate isn't bypassable via the other entry point.
    with pytest.raises(ModelNotUsableError):
        _factory().build_for_operation(
            definition=_DEFINITION,
            binding=_binding(()),
            purpose="chat",
            operation="planning",
        )
    with pytest.raises(ModelNotUsableError):
        _factory().build(definition=_DEFINITION, binding=_binding(()))


# ---------------------------------------------------------------------------
# 2. usable_model_capability_ids — pod-side ReBAC query
# ---------------------------------------------------------------------------


class _FakeRef:
    def __init__(self, id_: str) -> None:
        self.id = id_


class _FakeRebac:
    def __init__(self, *, enabled: bool, ids: list[str]) -> None:
        self.enabled = enabled
        self._ids = ids
        self.calls: list[tuple[Any, ...]] = []

    async def lookup_resources(
        self, subject: Any, permission: Any, resource_type: Any, **kwargs: Any
    ) -> list[_FakeRef]:
        self.calls.append((subject, permission, resource_type))
        return [_FakeRef(i) for i in self._ids]


@pytest.mark.asyncio
async def test_returns_none_when_rebac_is_none() -> None:
    assert await usable_model_capability_ids(None, "team-a") is None


@pytest.mark.asyncio
async def test_returns_none_when_rebac_disabled() -> None:
    rebac = _FakeRebac(enabled=False, ids=[])
    assert await usable_model_capability_ids(rebac, "team-a") is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_filters_to_model_prefixed_ids_only() -> None:
    rebac = _FakeRebac(
        enabled=True,
        ids=["model__openai__gpt-5.1", "doc_access", "agent__runtime-a__sentinel"],
    )
    result = await usable_model_capability_ids(rebac, "team-a")  # type: ignore[arg-type]
    assert result == frozenset({"model__openai__gpt-5.1"})


@pytest.mark.asyncio
async def test_empty_result_is_a_real_empty_frozenset_not_none() -> None:
    rebac = _FakeRebac(enabled=True, ids=[])
    result = await usable_model_capability_ids(rebac, "team-a")  # type: ignore[arg-type]
    assert result == frozenset()
    assert result is not None
