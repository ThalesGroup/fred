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
from fred_sdk.contracts.context import BoundRuntimeContext
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
from .resolver import ModelRoutingResolver, resolve_team_override

logger = logging.getLogger(__name__)


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

        Reasoning enforcement (REASON-01, `MODEL-REASONING-ENABLEMENT-RFC.md`) —
        the SINGLE point where reasoning is turned off, for every level:

        - **level 2**, the platform admin's per-model toggle, snapshotted at
          session prep on `RuntimeContext.reasoning_enabled_model_ids`. Off by
          default, so an absent list means no model reasons;
        - **level 4**, the user's per-question choice, on
          `RuntimeContext.reasoning`. `None` means the agent never offered the
          choice, so levels 1-2 decide alone; `False` means this turn must not
          reason whatever the platform allows.

        Level 2 is a ceiling: `reasoning=True` on a model the admin has not
        enabled still does not reason (§5.3). Both are enforced HERE, at client
        construction, because the YAML has already put `reasoning_effort` in
        `settings` — a switch that only declined to *add* it would never reach
        the model (§5.6.2), which is precisely the failure mode this feature
        exists to avoid.
        """
        selection = self.select(
            definition=definition,
            binding=binding,
            capability=ModelCapability.CHAT,
        )
        capability_id = model_capability_id(
            selection.model.provider or "", selection.model.name or ""
        )
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
        # `is False`, not falsy: `None` means "no per-question choice offered"
        # and must NOT strip, while `False` means the user actively said no.
        turn_declined = binding.runtime_context.reasoning is False
        if not platform_allows or turn_declined:
            model_config = without_reasoning_settings(model_config)
        model = self._provider.build_model(
            model_config, capability=selection.capability
        )
        if not isinstance(model, BaseChatModel):
            raise TypeError(
                "RoutedChatModelFactory expected a BaseChatModel for capability='chat'."
            )
        if selection.source in (
            ModelSelectionSource.AGENT_OVERRIDE,
            ModelSelectionSource.TEAM_POLICY,
        ):
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
        - resolver fallback/default and errors are handled in `ModelRoutingResolver`
        - when the static resolver falls through to the capability default, a
          second, narrower pass applies the team's own routing policy if one
          exists — see `resolve_team_override`. A static
          `models_catalog.yaml` override always wins over team policy; team
          policy only fills the gap a static override left open. Raises
          `TeamRoutingProfileDriftError` if the team policy names a profile
          this deployment's catalog doesn't have.

        Observability signals to look at:
        - this function does not log directly
        - inspect caller logs (`build_for_chat`) for emitted routing signals

        Platform binding precedence (unconditional): for the `chat`
        capability, when `binding.platform_chat_model_binding` is set, it is
        returned immediately, before the resolver (and therefore before the
        static `agent_profile_overrides` / team-policy layers below) is even
        consulted. A team-level override still only ever names a profile from
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
            )
        request = ModelSelectionRequest(
            capability=capability,
            agent_id=definition.agent_id,
        )
        selection = self._resolver.resolve(request)
        if (
            selection.source != ModelSelectionSource.DEFAULT
            or capability != ModelCapability.CHAT
        ):
            return selection

        team_profile_id = resolve_team_override(
            agent_profile_overrides=binding.runtime_context.agent_profile_overrides,
            chat_default_profile_id=binding.runtime_context.chat_default_profile_id,
            agent_id=definition.agent_id,
        )
        if team_profile_id is None:
            return selection

        profile = self._resolver.profile_or_none(team_profile_id)
        if profile is None:
            raise TeamRoutingProfileDriftError(profile_id=team_profile_id)
        if profile.capability != capability:
            raise TeamRoutingProfileDriftError(
                profile_id=team_profile_id,
                expected_capability=capability,
                actual_capability=profile.capability,
            )
        return ModelSelection(
            source=ModelSelectionSource.TEAM_POLICY,
            capability=capability,
            profile_id=profile.profile_id,
            model=profile.model.model_copy(deep=True),
        )


# Backward-compatible aliases within the isolated slice.
ChatModelProvider = ModelProvider
FredCoreChatModelProvider = FredCoreModelProvider
