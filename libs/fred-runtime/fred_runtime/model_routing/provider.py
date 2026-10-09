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
Provider-style adapters for routed chat-model selection.

`RoutedChatModelFactory` is wired by default at pod boot
(`fred_runtime.app.context._build_chat_model_factory`) into
`RuntimeContext.chat_model_factory`, reaching every `RuntimeServices`.
"""

from __future__ import annotations

import logging
from typing import Protocol

from fred_core.common import ModelConfiguration
from fred_core.model.factory import get_embeddings, get_model
from fred_sdk.contracts.capability.manifest import model_capability_id
from fred_sdk.contracts.context import (
    BoundRuntimeContext,
    ChatProfileOrigin,
    resolve_effective_chat_profile,
)
from fred_sdk.contracts.models import AgentDefinition
from fred_sdk.contracts.runtime import ChatModelFactoryPort
from langchain_core.language_models.chat_models import BaseChatModel

from .contracts import (
    ModelCapability,
    ModelNotUsableError,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
    TeamRoutingProfileDriftError,
    without_reasoning_settings,
)
from .resolver import ModelRoutingResolver

logger = logging.getLogger(__name__)

# The `source` each precedence level reports in the `[V2][MODEL_ROUTING]` log
# line. `ModelSelectionSource` is the operator-facing signal, `ChatProfileOrigin`
# the precedence level; the explicit table keeps the two decoupled.
_SOURCE_BY_CHAT_PROFILE_ORIGIN: dict[ChatProfileOrigin, ModelSelectionSource] = {
    ChatProfileOrigin.POD_AGENT_OVERRIDE: ModelSelectionSource.AGENT_OVERRIDE,
    ChatProfileOrigin.USER_CHOICE: ModelSelectionSource.USER_CHOICE,
    ChatProfileOrigin.INSTANCE_RECOMMENDATION: (
        ModelSelectionSource.INSTANCE_RECOMMENDATION
    ),
    ChatProfileOrigin.TEAM_DEFAULT: ModelSelectionSource.TEAM_POLICY,
    ChatProfileOrigin.POD_DEFAULT: ModelSelectionSource.DEFAULT,
}

# Sources logged at info level: anything a team, an editor or a user chose.
_INFO_LOGGED_SOURCES = frozenset(
    {
        ModelSelectionSource.AGENT_OVERRIDE,
        ModelSelectionSource.USER_CHOICE,
        ModelSelectionSource.INSTANCE_RECOMMENDATION,
        ModelSelectionSource.TEAM_POLICY,
    }
)


class ModelProvider(Protocol):
    """
    Generic model provider in genai-sdk style.

    It is capability-aware so chat and embeddings can use distinct client
    factories without inferring behavior from profile names.
    """

    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        pass


class FredCoreModelProvider(ModelProvider):
    """
    Default provider backed by fred-core model factories.

    Current mapping:
    - `embedding` -> `fred_core.get_embeddings(...)`
    - all other retained capabilities -> `fred_core.get_model(...)`

    Teams can replace this provider when image generation needs a dedicated
    non-chat client.
    """

    def build_model(
        self, model_config: ModelConfiguration, *, capability: ModelCapability
    ) -> object:
        if capability == ModelCapability.EMBEDDING:
            return get_embeddings(model_config)
        return get_model(model_config)


class RoutedChatModelFactory(ChatModelFactoryPort):
    """
    Runtime adapter that delegates model choice to a centralized resolver.

    Scope: chat-model selection based on agent/team, resolved once per turn.
    """

    def __init__(
        self,
        *,
        resolver: ModelRoutingResolver,
        provider: ModelProvider | None = None,
    ) -> None:
        self._resolver = resolver
        self._provider = provider or FredCoreModelProvider()

    def with_provider(self, provider: ModelProvider) -> RoutedChatModelFactory:
        """Same routing, models built by `provider` (a pod serving extra providers)."""
        return RoutedChatModelFactory(resolver=self._resolver, provider=provider)

    def build(  # type: ignore[override]
        self, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> BaseChatModel:
        """
        Why this function exists:
        - satisfy `ChatModelFactoryPort` contract expected by v2 runtimes
        - the single routed chat selection entrypoint, called once per turn
          at runtime activation (ReAct/Deep/Graph all call this the same way)

        Who calls it:
        - v2 runtime wiring when a runtime needs one chat model factory result

        Expected inputs / invariants:
        - `definition.agent_id` and `binding.portable_context` identify scope
        - factory was initialized with a valid resolver/provider

        Return / side effects:
        - returns one `BaseChatModel`
        - delegates actual selection/build to `build_for_chat(...)`

        Fallback / errors:
        - errors raised by resolver/provider/type checks propagate unchanged

        Observability signals to look at:
        - same signals as `build_for_chat` (`[V2][MODEL_ROUTING]` logs)
        """
        model, _ = self.build_for_chat(definition=definition, binding=binding)
        return model

    def build_for_chat(
        self,
        *,
        definition: AgentDefinition,
        binding: BoundRuntimeContext,
    ) -> tuple[BaseChatModel, ModelSelection]:
        """
        Why this function exists:
        - return both the concrete model and the routing decision metadata

        Who calls it:
        - `build(...)` — the only caller

        Return / side effects:
        - returns `(BaseChatModel, ModelSelection)`
        - emits info/debug logs with routing source/profile metadata

        Fallback / errors:
        - resolver may fall back to the policy default profile
        - raises `TypeError` if provider returns a non-chat model object
        - resolver/provider exceptions propagate

        Observability signals to look at:
        - info log on rule hit: `[V2][MODEL_ROUTING] ... source=rule ...`
        - debug log on default hit: `[V2][MODEL_ROUTING] ... source=default ...`

        Fail-closed enforcement (OBSERV-02 v3, `AGENT-CAPABILITY-RFC.md` §8.7):
        raises `ModelNotUsableError` — never silently substitutes a different
        model — when `binding.usable_model_ids` is not `None` (ReBAC active)
        and the resolved model isn't in it.

        Reasoning enforcement (REASON-01): the SINGLE point where reasoning is
        turned off. A turn reasons only when `RuntimeContext.reasoning is True`
        AND its model is in `reasoning_enabled_model_ids` (the platform
        ceiling). `False` and `None` both strip. Enforced here, at client
        construction, because the YAML already put `reasoning_effort` in
        `settings`: declining to add it would never reach the model.
        """
        selection = self.select(
            definition=definition,
            binding=binding,
            capability=ModelCapability.CHAT,
        )
        # The winning profile's own identity, never re-derived from
        # `model.name`: siblings on one gateway share that wire name.
        capability_id = selection.capability_id
        if (
            selection.source != ModelSelectionSource.PLATFORM_BINDING
            and binding.usable_model_ids is not None
        ):
            if capability_id not in binding.usable_model_ids:
                logger.warning(
                    "[V2][MODEL_ROUTING] denied: team=%s model=%s/%s (%s) not "
                    "in usable_model_ids",
                    binding.portable_context.team_id,
                    selection.model.provider,
                    selection.model.name,
                    capability_id,
                )
                raise ModelNotUsableError(
                    capability_id=capability_id,
                    provider=selection.model.provider or "",
                    name=selection.model.name or "",
                )
        # Cheap and allocation-free in the common case: `without_reasoning_settings`
        # returns the SAME object when the profile carries no reasoning setting,
        # which is every profile but the ones ops declared thinking-capable.
        model_config = selection.model
        platform_allows = capability_id in (
            binding.runtime_context.reasoning_enabled_model_ids or ()
        )
        # Only an explicit True reasons: callers that send nothing must not.
        turn_requested = binding.runtime_context.reasoning is True
        if not platform_allows or not turn_requested:
            model_config = without_reasoning_settings(model_config)
        model = self._provider.build_model(
            model_config, capability=selection.capability
        )
        if not isinstance(model, BaseChatModel):
            raise TypeError(
                "RoutedChatModelFactory expected a BaseChatModel for capability='chat'."
            )
        if selection.source in _INFO_LOGGED_SOURCES:
            logger.info(
                "[V2][MODEL_ROUTING] agent=%s source=%s profile=%s model=%s/%s team=%s user=%s",
                definition.agent_id,
                selection.source.value,
                selection.profile_id,
                selection.model.provider,
                selection.model.name,
                binding.portable_context.team_id,
                binding.portable_context.user_id,
            )
        else:
            logger.debug(
                "[V2][MODEL_ROUTING] agent=%s source=%s profile=%s model=%s/%s",
                definition.agent_id,
                selection.source.value,
                selection.profile_id,
                selection.model.provider,
                selection.model.name,
            )
        return model, selection

    def select(
        self,
        *,
        definition: AgentDefinition,
        binding: BoundRuntimeContext,
        capability: ModelCapability,
    ) -> ModelSelection:
        """
        Why this function exists:
        - convert runtime context (`agent/team`) into a resolver request object

        Who calls it:
        - `build_for_chat(...)` today
        - can also be used directly by future non-chat routing adapters

        When it is called:
        - once per turn

        Return / side effects:
        - returns immutable `ModelSelection` (selected profile + model config)
        - no side effects

        Fallback / errors:
        - for `chat`, the profile-valued levels are ordered by
          `fred_sdk.contracts.context.resolve_effective_chat_profile`, shared
          with control-plane. The user choice and the instance recommendation
          are validated first (`_accepted_choice`) and ignored when invalid. A
          team default that is unknown or non-chat raises
          `TeamRoutingProfileDriftError`; one whose model is team-disabled
          raises `ModelNotUsableError`. Never a silent substitution.
        - for every other capability, resolution stays pod-local and is handled
          by `ModelRoutingResolver.resolve` (no team layer exists for it: V1's
          only other capability, `embedding`, has no production consumer yet).

        Observability signals to look at:
        - this function does not log directly
        - inspect caller logs (`build_for_chat`) for emitted routing signals

        Platform binding precedence (unconditional): for the `chat`
        capability, when `binding.platform_chat_model_binding` is set, it is
        returned immediately, before any profile-valued level is consulted. A team-level override still only ever names a profile from
        *some* pod's local menu — the exact limitation an operator-asserted
        binding exists to route around — so if a stale team choice could
        still win, the operator's fix for a broken deployment would be
        silently defeatable.

        `binding.platform_chat_model_binding` is a TRUSTED field: the runtime
        resolves it itself, per turn, from control-plane's
        `ManagedAgentRuntimeBinding` server-to-server lookup — it can never
        be set by request-body content, so this precedence cannot be forged
        by a caller. V1 only ever populates it for the `chat` capability
        (checked explicitly below); other capabilities always fall through
        to the resolver.
        """
        platform_binding = (
            binding.platform_chat_model_binding
            if capability == ModelCapability.CHAT
            else None
        )
        if platform_binding is not None:
            return ModelSelection(
                source=ModelSelectionSource.PLATFORM_BINDING,
                capability=capability,
                profile_id=f"platform-binding:{capability.value}",
                model=ModelConfiguration(
                    provider=platform_binding.provider,
                    name=platform_binding.name,
                    settings=platform_binding.settings.model_dump(
                        mode="json", exclude_none=True
                    ),
                ),
                # No profile behind an operator binding, so the identity is the
                # wire name — the same derivation control-plane uses for it.
                capability_id=model_capability_id(
                    platform_binding.provider, platform_binding.name
                ),
            )
        if capability != ModelCapability.CHAT:
            return self._resolver.resolve(
                ModelSelectionRequest(
                    capability=capability, agent_id=definition.agent_id
                )
            )

        resolution = resolve_effective_chat_profile(
            agent_id=definition.agent_id,
            pod_agent_chat_profile_overrides=self._resolver.agent_overrides_for(
                capability
            ),
            pod_default_chat_profile_id=self._resolver.default_profile_id_for(
                capability
            ),
            user_chat_profile_id=self._accepted_choice(
                binding.runtime_context.chat_profile_id, binding, level="user_choice"
            ),
            instance_chat_profile_id=self._accepted_choice(
                binding.recommended_chat_profile_id,
                binding,
                level="instance_recommendation",
            ),
            team_chat_default_profile_id=binding.runtime_context.chat_default_profile_id,
        )
        if resolution is None:
            # Same failure the resolver's own default lookup raised before: the
            # catalog declares no chat default and no other level produced one.
            raise ValueError(
                f"No default profile configured for capability={capability.value!r}."
            )

        profile = self._resolver.profile_or_none(resolution.profile_id)
        team_origin = resolution.origin is ChatProfileOrigin.TEAM_DEFAULT
        if profile is None:
            if team_origin:
                raise TeamRoutingProfileDriftError(profile_id=resolution.profile_id)
            # A pod-origin id that resolves to nothing means the catalog passed
            # `ModelRoutingPolicy`'s own validation while naming a profile it
            # does not contain — an invariant violation in this package, not a
            # team's stale choice, so it must not be reported as team drift.
            raise KeyError(resolution.profile_id)
        if profile.capability != capability:
            # Only reachable for a team-origin id: the pod maps are
            # capability-filtered and the choice levels validated above.
            raise TeamRoutingProfileDriftError(
                profile_id=resolution.profile_id,
                expected_capability=capability,
                actual_capability=profile.capability,
            )
        if team_origin and profile.capability_id in binding.team_disabled_model_ids:
            # D4 forbids storing a disabled default; if one is seen, fail
            # closed rather than silently substitute another model.
            logger.warning(
                "[V2][MODEL_ROUTING] denied: team=%s default profile=%s (%s) is "
                "team-disabled",
                binding.portable_context.team_id,
                profile.profile_id,
                profile.capability_id,
            )
            raise ModelNotUsableError(
                capability_id=profile.capability_id,
                provider=profile.model.provider or "",
                name=profile.model.name or "",
            )
        return ModelSelection(
            source=_SOURCE_BY_CHAT_PROFILE_ORIGIN[resolution.origin],
            capability=capability,
            profile_id=profile.profile_id,
            model=profile.model.model_copy(deep=True),
            capability_id=profile.capability_id,
        )

    def _accepted_choice(
        self, profile_id: str | None, binding: BoundRuntimeContext, *, level: str
    ) -> str | None:
        """`profile_id` when it is a known chat profile whose model the team can
        use and has not disabled, else `None`. A stale or spoofed choice must
        never fail the turn, so it is logged and resolution falls through."""

        if profile_id is None:
            return None
        profile = self._resolver.profile_or_none(profile_id)
        if profile is None or profile.capability != ModelCapability.CHAT:
            reason = "unknown or non-chat profile"
        elif (
            binding.usable_model_ids is not None
            and profile.capability_id not in binding.usable_model_ids
        ):
            reason = "model not usable by the team"
        elif profile.capability_id in binding.team_disabled_model_ids:
            reason = "model disabled by the team"
        else:
            return profile_id
        # Debug: `select` runs once per model call, and the id is client input.
        logger.debug(
            "[V2][MODEL_ROUTING] %s ignored: team=%s profile=%r reason=%s",
            level,
            binding.portable_context.team_id,
            profile_id[:128],
            reason,
        )
        return None


# Backward-compatible aliases within the isolated slice.
ChatModelProvider = ModelProvider
FredCoreChatModelProvider = FredCoreModelProvider
