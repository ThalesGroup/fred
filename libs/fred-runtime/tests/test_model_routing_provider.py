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
Offline unit tests for `RoutedChatModelFactory` / `provider.py` — new
scaffolding, since this module had zero existing unit coverage before the
platform-wide model binding override feature (only `ModelRoutingResolver`,
`resolve_team_override`, and catalog loading were covered, in
`test_model_routing.py`).

Focus: the platform-binding bypass added to `select()` and the
`usable_model_ids` gate-skip added to `build_for_chat` — both must be correct
independently of everything the resolver/team-policy layers already do,
which `test_model_routing.py` continues to cover on its own.

Trusted-channel hardening: the platform binding moved from the client-forwarded
`RuntimeContext.platform_model_bindings` (removed) to the TRUSTED
`BoundRuntimeContext.platform_chat_model_binding`, and the bypass is now
chat-only (V1 scope) rather than capability-generic. Tests below exercise the
new field and prove a value smuggled onto `RuntimeContext` (which no longer
has a field for it at all) cannot reach `select()`.

No mocks, no network, no filesystem side effects. `FakeListChatModel`
(langchain_core's own test double) stands in for a real chat model so
`build_for_chat`'s `isinstance(model, BaseChatModel)` check has something
real to check against.
"""

from __future__ import annotations

import pytest
from fred_core.common import ModelConfiguration
from fred_runtime.model_routing.contracts import (
    ModelCapability,
    ModelNotUsableError,
    ModelProfile,
    ModelRoutingPolicy,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
    TeamRoutingProfileDriftError,
)
from fred_runtime.model_routing.provider import ModelProvider, RoutedChatModelFactory
from fred_runtime.model_routing.resolver import ModelRoutingResolver
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ModelBinding,
    PortableContext,
    PortableEnvironment,
    RuntimeContext,
)
from fred_sdk.contracts.models import AgentDefinition, ExecutionCategory
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel

# ---------------------------------------------------------------------------
# Fixtures / test doubles
# ---------------------------------------------------------------------------


class _FakeAgentDefinition(AgentDefinition):
    """`AgentDefinition` declares no abstract methods of its own — a bare
    subclass is instantiable and is all `select`/`build_for_chat` need
    (they only read `definition.agent_id`)."""


def _agent_definition(agent_id: str = "rico") -> AgentDefinition:
    return _FakeAgentDefinition(
        agent_id=agent_id,
        role="role",
        description="description",
        execution_category=ExecutionCategory.REACT,
    )


def _model_config(
    provider: str = "openai", name: str = "gpt-4o", settings: dict | None = None
) -> ModelConfiguration:
    return ModelConfiguration(provider=provider, name=name, settings=settings or {})


def _profile(
    profile_id: str,
    capability: ModelCapability = ModelCapability.CHAT,
    provider: str = "openai",
    name: str = "gpt-4o",
) -> ModelProfile:
    return ModelProfile(
        profile_id=profile_id,
        capability=capability,
        model=_model_config(provider=provider, name=name),
    )


def _policy(
    *,
    profile_id: str = "default.chat",
    capability: ModelCapability = ModelCapability.CHAT,
    agent_profile_overrides: dict[str, str] | None = None,
    extra_profiles: tuple[ModelProfile, ...] = (),
) -> ModelRoutingPolicy:
    return ModelRoutingPolicy(
        default_profile_by_capability={capability: profile_id},
        profiles=(_profile(profile_id, capability=capability), *extra_profiles),
        agent_profile_overrides=agent_profile_overrides or {},
    )


def _portable_context() -> PortableContext:
    return PortableContext(
        request_id="req-1",
        correlation_id="corr-1",
        actor="tester",
        tenant="tenant-1",
        environment=PortableEnvironment.DEV,
    )


def _binding(
    *,
    runtime_context: RuntimeContext | None = None,
    usable_model_ids: tuple[str, ...] | None = None,
    platform_chat_model_binding: ModelBinding | None = None,
) -> BoundRuntimeContext:
    return BoundRuntimeContext(
        runtime_context=runtime_context or RuntimeContext(),
        portable_context=_portable_context(),
        usable_model_ids=usable_model_ids,
        platform_chat_model_binding=platform_chat_model_binding,
    )


class _RaisingResolver:
    """Stands in for `ModelRoutingResolver` and fails the test if it is ever
    consulted — used to prove the platform-binding bypass in `select()` is
    unconditional and returns before the resolver runs at all."""

    def resolve(self, request: ModelSelectionRequest) -> ModelSelection:
        raise AssertionError(
            f"resolver.resolve() must not be called when a platform binding "
            f"exists for capability={request.capability!r}"
        )

    def profile_or_none(self, profile_id: str) -> ModelProfile | None:
        raise AssertionError("resolver.profile_or_none() must not be called")


class _RecordingProvider(ModelProvider):
    """Real `ModelProvider` double: records the `ModelConfiguration` it was
    asked to build and returns a `FakeListChatModel` so `build_for_chat`'s
    `isinstance(model, BaseChatModel)` check passes."""

    def __init__(self) -> None:
        self.calls: list[tuple[ModelConfiguration, ModelCapability]] = []

    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        self.calls.append((model_config, capability))
        return FakeListChatModel(responses=["ok"])


def _factory(
    *, resolver: object, provider: ModelProvider | None = None
) -> RoutedChatModelFactory:
    return RoutedChatModelFactory(resolver=resolver, provider=provider)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# select() — platform binding bypass
# ---------------------------------------------------------------------------


class TestSelectPlatformBindingBypass:
    def test_platform_binding_wins_and_resolver_is_never_consulted(self) -> None:
        binding = ModelBinding(provider="ollama", name="internal-model")
        factory = _factory(resolver=_RaisingResolver())

        selection = factory.select(
            definition=_agent_definition(),
            binding=_binding(platform_chat_model_binding=binding),
            capability=ModelCapability.CHAT,
        )

        assert selection.source == ModelSelectionSource.PLATFORM_BINDING
        assert selection.capability == ModelCapability.CHAT
        assert selection.profile_id == "platform-binding:chat"
        assert selection.model.provider == "ollama"
        assert selection.model.name == "internal-model"

    def test_platform_binding_wins_over_matching_static_override(self) -> None:
        # A real resolver whose *static* agent_profile_overrides would pick a
        # distinctly different model if it were ever consulted.
        policy = _policy(
            agent_profile_overrides={"rico": "override.chat"},
            extra_profiles=(
                _profile("override.chat", provider="azure", name="static-override"),
            ),
        )
        resolver = ModelRoutingResolver(policy)
        platform_binding = ModelBinding(provider="ollama", name="internal-model")
        factory = _factory(resolver=resolver)

        selection = factory.select(
            definition=_agent_definition("rico"),
            binding=_binding(platform_chat_model_binding=platform_binding),
            capability=ModelCapability.CHAT,
        )

        assert selection.source == ModelSelectionSource.PLATFORM_BINDING
        assert selection.model.provider == "ollama"
        assert selection.model.name == "internal-model"
        # The static override, if it had won, would have produced this model —
        # confirm it did not.
        assert selection.model.name != "static-override"

    def test_platform_binding_wins_over_matching_team_policy_override(self) -> None:
        # Resolver falls through to DEFAULT (no static override), which is
        # exactly the case where `resolve_team_override` would normally kick
        # in and win — the team-level `agent_profile_overrides`/
        # `chat_default_profile_id` on RuntimeContext.
        resolver = ModelRoutingResolver(_policy())
        platform_binding = ModelBinding(provider="ollama", name="internal-model")
        runtime_context = RuntimeContext(
            chat_default_profile_id="default.chat",  # would resolve if reached
            agent_profile_overrides={"rico": "default.chat"},
        )
        factory = _factory(resolver=resolver)

        selection = factory.select(
            definition=_agent_definition("rico"),
            binding=_binding(
                runtime_context=runtime_context,
                platform_chat_model_binding=platform_binding,
            ),
            capability=ModelCapability.CHAT,
        )

        assert selection.source == ModelSelectionSource.PLATFORM_BINDING
        assert selection.model.provider == "ollama"
        assert selection.model.name == "internal-model"

    @pytest.mark.parametrize(
        "capability",
        [ModelCapability.EMBEDDING, ModelCapability.LANGUAGE, ModelCapability.IMAGE],
    )
    def test_platform_binding_never_applies_outside_chat_in_v1(
        self, capability: ModelCapability
    ) -> None:
        """V1 scope: the platform binding is chat-only. Even
        when `platform_chat_model_binding` is set, a non-chat capability
        request must fall through to the resolver untouched — proving
        `select()`'s capability check, not just the (now chat-only) field
        name, actually gates the bypass."""
        binding = ModelBinding.model_validate(
            {
                "provider": "vertex-ai",
                "name": "text-embedding-004",
                "settings": {"project": "proj-1", "location": "us-central1"},
            }
        )
        resolver = ModelRoutingResolver(_policy(capability=capability))
        factory = _factory(resolver=resolver)

        selection = factory.select(
            definition=_agent_definition(),
            binding=_binding(platform_chat_model_binding=binding),
            capability=capability,
        )

        assert selection.source == ModelSelectionSource.DEFAULT
        assert selection.model.provider != "vertex-ai"

    def test_forged_runtime_context_field_cannot_reach_select(self) -> None:
        """A caller-supplied `RuntimeContext` cannot express a platform
        binding at all — the field was removed entirely from the
        client-forwarded contract. Constructing it with the old kwarg is
        silently ignored (unknown field), and `select()` still falls through
        to the resolver exactly as if no platform binding existed."""
        runtime_context = RuntimeContext.model_validate(
            {
                "platform_model_bindings": {
                    "chat": {"provider": "attacker", "name": "forged-model"}
                }
            }
        )
        assert not hasattr(runtime_context, "platform_model_bindings")
        resolver = ModelRoutingResolver(_policy())
        factory = _factory(resolver=resolver)

        selection = factory.select(
            definition=_agent_definition("rico"),
            binding=_binding(runtime_context=runtime_context),
            capability=ModelCapability.CHAT,
        )

        assert selection.source == ModelSelectionSource.DEFAULT
        assert selection.model.provider != "attacker"

    def test_no_platform_binding_regression_unchanged(self) -> None:
        """No platform binding at all: fully existing resolver/team-policy
        behavior, exercised exactly as before this feature."""
        resolver = ModelRoutingResolver(_policy())
        factory = _factory(resolver=resolver)

        selection = factory.select(
            definition=_agent_definition("rico"),
            binding=_binding(runtime_context=RuntimeContext()),
            capability=ModelCapability.CHAT,
        )

        assert selection.source == ModelSelectionSource.DEFAULT
        assert selection.profile_id == "default.chat"

    def test_no_platform_binding_team_policy_drift_still_raises(self) -> None:
        """Regression guard: team routing policy naming a profile absent from
        this deployment's catalog still raises `TeamRoutingProfileDriftError`
        exactly as before, when no platform binding masks it."""
        resolver = ModelRoutingResolver(_policy())
        runtime_context = RuntimeContext(chat_default_profile_id="ghost.profile")
        factory = _factory(resolver=resolver)

        with pytest.raises(TeamRoutingProfileDriftError):
            factory.select(
                definition=_agent_definition("rico"),
                binding=_binding(runtime_context=runtime_context),
                capability=ModelCapability.CHAT,
            )


# ---------------------------------------------------------------------------
# build_for_chat() — usable_model_ids gate skip for platform-bound selections
# ---------------------------------------------------------------------------


class TestBuildForChatUsableModelIdsGateSkip:
    def test_platform_binding_bypasses_empty_usable_model_ids(self) -> None:
        """THE critical gate-bypass regression test. Without the
        `selection.source != PLATFORM_BINDING` guard in `build_for_chat`,
        every team's every turn breaks the moment a platform binding is set
        on any ReBAC-enabled deployment, because a platform-bound
        (provider, name) pair by design may not correspond to any
        pod-declared, ReBAC-admitted capability id. `usable_model_ids=()`
        (empty, not None) is the sharpest version of that: ReBAC active,
        nothing enabled for this team at all — and it must still not raise.
        """
        binding_model = ModelBinding(provider="ollama", name="internal-model")
        provider = _RecordingProvider()
        factory = _factory(resolver=_RaisingResolver(), provider=provider)

        model, selection = factory.build_for_chat(
            definition=_agent_definition(),
            binding=_binding(
                usable_model_ids=(), platform_chat_model_binding=binding_model
            ),
        )

        assert selection.source == ModelSelectionSource.PLATFORM_BINDING
        assert isinstance(model, BaseChatModel)
        assert len(provider.calls) == 1
        built_config, built_capability = provider.calls[0]
        assert built_config.provider == "ollama"
        assert built_config.name == "internal-model"
        assert built_capability == ModelCapability.CHAT

    def test_non_platform_selection_still_gated_by_usable_model_ids(self) -> None:
        """Regression guard: the ReBAC gate itself is untouched for every
        selection source other than PLATFORM_BINDING."""
        resolver = ModelRoutingResolver(_policy())
        provider = _RecordingProvider()
        factory = _factory(resolver=resolver, provider=provider)

        with pytest.raises(ModelNotUsableError):
            factory.build_for_chat(
                definition=_agent_definition("rico"),
                binding=_binding(runtime_context=RuntimeContext(), usable_model_ids=()),
            )
        assert provider.calls == []

    def test_no_platform_binding_no_rebac_restriction_unchanged(self) -> None:
        """Regression guard: `usable_model_ids=None` (ReBAC disabled) with no
        platform binding builds successfully exactly as before."""
        resolver = ModelRoutingResolver(_policy())
        provider = _RecordingProvider()
        factory = _factory(resolver=resolver, provider=provider)

        model, selection = factory.build_for_chat(
            definition=_agent_definition("rico"),
            binding=_binding(runtime_context=RuntimeContext(), usable_model_ids=None),
        )

        assert selection.source == ModelSelectionSource.DEFAULT
        assert isinstance(model, BaseChatModel)
