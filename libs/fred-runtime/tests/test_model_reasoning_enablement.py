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
Reasoning enablement, levels 1 and 2 (REASON-01,
`MODEL-REASONING-ENABLEMENT-RFC.md`).

Level 1 — `ModelProfile.supports_thinking` and the boot-time consistency
validator (§4.3).

Level 2 — the platform toggle's enforcement point (§5.6.2). The load-bearing
tests here are `test_toggle_off_*`: they build the REAL `ChatOpenAI` client
through the real `fred-core` factory and inspect the outbound request payload,
because the failure this level exists to prevent is precisely a flag that looks
wired and never reaches the model. `AGENT-THINKING-API-RFC.md` §C.8 records that
exact bug in-tree for `allow_parallel_calls` ("Decorative. Never reaches the
model"), which is why asserting on an intermediate object would not be enough.

Offline: `get_model` constructs a client, it never calls the provider — the
`OPENAI_API_KEY` below only satisfies the factory's presence check.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fred_core.common import ModelConfiguration
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelProfile,
    ModelRoutingPolicy,
    without_reasoning_settings,
)
from fred_runtime.model_routing.provider import RoutedChatModelFactory
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_sdk.contracts.capability.manifest import model_capability_id
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from langchain_core.messages import HumanMessage

# pyright: reportArgumentType=false
# ^ `definition` is a SimpleNamespace exposing only `.agent_id`, the single
#   attribute the factory reads — same convention as test_model_enforcement.py.

THINKING_MODEL_ID = model_capability_id("openai", "mistral-small-latest")


@pytest.fixture(autouse=True)
def _openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-used-offline")


# ---------------------------------------------------------------------------
# Level 1 — declared aptitude and its consistency validator (§4/§4.3)
# ---------------------------------------------------------------------------


def _profile(
    *,
    supports_thinking: bool = False,
    settings: dict[str, Any] | None = None,
    profile_id: str = "chat.mistral.small",
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        capability=ModelCapability.CHAT,
        model=ModelConfiguration(
            provider="openai",
            name="mistral-small-latest",
            settings=settings if settings is not None else {},
        ),
        supports_thinking=supports_thinking,
    )


def test_supports_thinking_defaults_to_false() -> None:
    # Additive with a safe default (§4.2 option A): every profile authored
    # before REASON-01 keeps loading, and declares no aptitude.
    assert _profile().supports_thinking is False


def test_reasoning_setting_without_declared_aptitude_fails_at_load() -> None:
    # §4.3 — always an authoring mistake, and it must fail loudly at pod boot
    # rather than be silently tolerated: an undeclared reasoning profile would
    # never surface an admin toggle, so its reasoning could never be turned off.
    with pytest.raises(ValueError) as excinfo:
        _profile(settings={"reasoning_effort": "high"})

    message = str(excinfo.value)
    assert "chat.mistral.small" in message
    assert "reasoning_effort" in message
    assert "supports_thinking" in message


def test_reasoning_setting_with_declared_aptitude_loads() -> None:
    profile = _profile(supports_thinking=True, settings={"reasoning_effort": "high"})

    assert profile.supports_thinking is True
    assert profile.model.settings == {"reasoning_effort": "high"}


def test_declared_aptitude_without_a_reasoning_setting_is_legal() -> None:
    # §4.3's converse, explicitly meaningful: "supported, shipped off" is the
    # state levels 3-4 need in order to have something to turn on.
    assert _profile(supports_thinking=True).supports_thinking is True


def test_the_validator_does_not_fire_on_unrelated_settings() -> None:
    profile = _profile(settings={"base_url": "https://api.mistral.ai/v1"})

    assert profile.supports_thinking is False


# ---------------------------------------------------------------------------
# without_reasoning_settings — the strip primitive (§5.6.2)
# ---------------------------------------------------------------------------


def test_strip_removes_only_the_reasoning_keys() -> None:
    model = ModelConfiguration(
        provider="openai",
        name="mistral-small-latest",
        settings={
            "base_url": "https://api.mistral.ai/v1",
            "max_retries": 2,
            "reasoning_effort": "high",
        },
    )

    stripped = without_reasoning_settings(model)

    assert stripped.settings == {
        "base_url": "https://api.mistral.ai/v1",
        "max_retries": 2,
    }
    # The catalog's own profile config must survive untouched — this runs on
    # every model build, and mutating the shared config would disable reasoning
    # process-wide after the first non-reasoning turn.
    assert model.settings is not None
    assert model.settings["reasoning_effort"] == "high"


def test_strip_returns_the_same_object_when_there_is_nothing_to_remove() -> None:
    # Not cosmetic: this is the per-operation model-build path, and almost every
    # profile has no reasoning setting at all. No copy, no allocation for them.
    model = ModelConfiguration(provider="openai", name="gpt-5.1", settings={"a": 1})

    assert without_reasoning_settings(model) is model


def test_strip_handles_a_profile_with_no_settings_at_all() -> None:
    model = ModelConfiguration(provider="openai", name="gpt-5.1", settings=None)

    assert without_reasoning_settings(model) is model


# ---------------------------------------------------------------------------
# Level 2 — enforcement at client construction (§5.6.2)
# ---------------------------------------------------------------------------


def _factory() -> RoutedChatModelFactory:
    """A real factory over a real provider: nothing about the model build is
    faked, because what is under test is what the built client sends."""

    policy = ModelRoutingPolicy(
        default_profile_by_capability={ModelCapability.CHAT: "chat.mistral.small"},
        profiles=(
            _profile(
                supports_thinking=True,
                settings={
                    "base_url": "https://api.mistral.ai/v1",
                    "reasoning_effort": "high",
                },
            ),
        ),
    )
    return RoutedChatModelFactory(resolver=ModelRoutingResolver(policy))


def _binding(
    reasoning_enabled_model_ids: list[str] | None,
    *,
    reasoning: bool | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=RuntimeContext(
            team_id="team-a",
            user_id="u1",
            reasoning_enabled_model_ids=reasoning_enabled_model_ids,
            reasoning=reasoning,
        ),
        portable_context=PortableContext(
            request_id="r1",
            correlation_id="r1",
            actor="u1",
            tenant="default",
            environment=PortableEnvironment.DEV,
            team_id="team-a",
            user_id="u1",
        ),
    )


def _outbound_params(model: Any) -> dict[str, Any]:
    """What the constructed client would actually put on the wire."""

    payload = model._get_request_payload([HumanMessage("hi")], stop=None)
    return {key: value for key, value in payload.items() if key != "messages"}


def _build(
    reasoning_enabled_model_ids: list[str] | None,
    *,
    reasoning: bool | None = None,
) -> dict[str, Any]:
    model, selection = _factory().build_for_chat(
        definition=SimpleNamespace(agent_id="agent-1"),
        binding=_binding(
            reasoning_enabled_model_ids,
            reasoning=reasoning,
        ),
    )
    assert selection.profile_id == "chat.mistral.small"
    return _outbound_params(model)


def test_toggle_off_builds_a_client_that_sends_no_reasoning_setting() -> None:
    """§5.6.2, the minimum bar for this level.

    The profile ships `reasoning_effort: high` in its YAML settings. With the
    platform toggle off, the constructed client must carry NO reasoning setting
    at all — a toggle that merely declined to *add* one would leave the model
    reasoning, because the catalog already put it there.
    """

    params = _build([])

    assert "reasoning_effort" not in params
    # Nothing else got dropped on the way — this is a targeted removal.
    assert params["model"] == "mistral-small-latest"


def test_toggle_absent_entirely_also_sends_no_reasoning_setting() -> None:
    # §5.6 — off by default. `None` (no control-plane snapshot at all: an older
    # frontend, or direct template execution) means exactly what `[]` means.
    # This is the deliberate semantic difference from `usable_model_ids`, where
    # `None` means "unrestricted".
    assert "reasoning_effort" not in _build(None)


def test_a_different_model_being_enabled_does_not_enable_this_one() -> None:
    assert "reasoning_effort" not in _build([model_capability_id("openai", "gpt-5.1")])


def test_toggle_on_builds_a_client_that_sends_the_reasoning_setting() -> None:
    # The other half of the proof: the strip is conditional, not unconditional.
    # Without this, "no reasoning setting" would pass by simply never working.
    params = _build([THINKING_MODEL_ID])

    assert params["reasoning_effort"] == "high"


def test_the_toggle_does_not_leak_into_the_next_build() -> None:
    # The profile lives in the catalog and is reused for every turn. A strip
    # implemented by mutation would silently disable reasoning platform-wide
    # after the first toggle-off turn.
    assert "reasoning_effort" not in _build([])
    assert _build([THINKING_MODEL_ID])["reasoning_effort"] == "high"


# ---------------------------------------------------------------------------
# Level 4 — the user's per-question choice, on the same enforcement point (§7)
# ---------------------------------------------------------------------------


def test_a_turn_that_declines_reasoning_sends_no_reasoning_setting() -> None:
    """Level 4, enforced where level 2 is: at client construction.

    The platform toggle is on and the profile ships `reasoning_effort: high`, so
    the model WOULD reason. The agent offers the composer toggle and the user
    left it off — this turn must not reason, and that has to be true of the
    request payload, not merely of a flag somewhere.
    """

    params = _build([THINKING_MODEL_ID], reasoning=False)

    assert "reasoning_effort" not in params


def test_a_turn_that_asks_for_reasoning_keeps_it() -> None:
    params = _build([THINKING_MODEL_ID], reasoning=True)

    assert params["reasoning_effort"] == "high"


def test_no_per_question_choice_leaves_levels_1_and_2_in_charge() -> None:
    # `None` means the agent never offered the toggle, which is NOT the same as
    # the user answering no — the pre-REASON-01 behaviour must be preserved for
    # every agent that does not opt in.
    params = _build([THINKING_MODEL_ID], reasoning=None)

    assert params["reasoning_effort"] == "high"


def test_level_2_stays_a_ceiling_the_user_cannot_raise() -> None:
    # §5.3: "Off means they never do, for anyone, whatever levels 3 and 4 say."
    # The user asked for reasoning on a model whose reasoning the platform admin
    # has NOT enabled — it must still not reason.
    params = _build([], reasoning=True)

    assert "reasoning_effort" not in params
