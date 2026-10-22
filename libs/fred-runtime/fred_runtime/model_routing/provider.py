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

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

import httpx

if TYPE_CHECKING:
    from .catalog import ModelCatalog

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

from fred_runtime.support.reasoning_replay import with_mistral_reasoning_replay

from .contracts import (
    ModelCapability,
    ModelNotUsableError,
    ModelProfile,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
    TeamRoutingProfileDriftError,
    clamp_reasoning_effort,
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
        ModelSelectionSource.PLATFORM_FALLBACK,
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


def _effective_reasoning_effort(
    profile: ModelProfile | None, choice: str
) -> str | None:
    """ "off" or a non-thinking profile: None. A profile with selectable levels:
    the nearest one. Otherwise (on/off): `ModelProfile.reasoning_on_effort`."""
    if choice == "off" or profile is None or not profile.supports_thinking:
        return None
    if profile.reasoning_levels:
        return clamp_reasoning_effort(choice, profile.reasoning_levels)
    return profile.reasoning_on_effort


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
        catalog: ModelCatalog | None = None,
        catalog_verified: bool = True,
    ) -> None:
        self._snapshot = (resolver, catalog)
        self._provider = provider or FredCoreModelProvider()
        self._refresh_lock = asyncio.Lock()
        self._catalog_verified = catalog_verified
        self._active_revisions: dict[str, int] = {}
        self._failed_urls: dict[tuple[str, str | None], float] = {}
        self._pending_refreshes: dict[
            tuple[str, str | None, int | None], asyncio.Task[ModelCatalog]
        ] = {}
        self._prepared: dict[str, tuple[ModelRoutingResolver, ModelCatalog, str]] = {}
        self._activation_backups: dict[str, tuple[ModelCatalog, str, int, bool]] = {}
        self._active_preparation_tokens: dict[str, str] = {}

    @property
    def catalog(self) -> ModelCatalog | None:
        return self._snapshot[1]

    @property
    def active_revision(self) -> int:
        return max(self._active_revisions.values(), default=0)

    def active_revision_for(self, source_id: str | None) -> int:
        return self._active_revisions.get(source_id or "", 0)

    @property
    def _resolver(self) -> ModelRoutingResolver:
        return self._snapshot[0]

    async def refresh_catalog(
        self,
        path: str,
        *,
        models_url: str | None = None,
        source_id: str | None = None,
        revision: int | None = None,
        force: bool = False,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> ModelCatalog:
        from .catalog import load_model_catalog

        async with self._refresh_lock:
            current = self.catalog or load_model_catalog(path)
            source = current.discovery_source(source_id)
            if source is None:
                raise ValueError(f"Unknown discovery source {source_id!r}")
            source_id = source.source_id
            refresh_key = (source_id, models_url)
            active_url = f"{source.base_url}/models"
            if (
                not force
                and revision is not None
                and revision < self.active_revision_for(source_id)
                and current is not None
            ):
                return current
            if (
                not force
                and models_url == active_url
                and current is not None
                and source_id in current.verified_discovery_source_ids
            ):
                if revision is not None:
                    self._active_revisions[source_id] = max(
                        revision, self.active_revision_for(source_id)
                    )
                return current
            if (
                not force
                and time.monotonic() < self._failed_urls.get(refresh_key, 0)
                and current is not None
            ):
                return current
            task_key = (*refresh_key, revision)
            task = self._pending_refreshes.get(task_key)
            if task is None:
                task = asyncio.create_task(
                    current.resolve_discovery_async(
                        models_url=models_url,
                        source_id=source_id,
                        allow_missing_default=True,
                        transport=transport,
                    )
                )
                self._pending_refreshes[task_key] = task
        try:
            catalog = await asyncio.shield(task)
            resolver = ModelRoutingResolver(catalog.to_policy())
        except asyncio.CancelledError:
            if task.cancelled():
                async with self._refresh_lock:
                    if self._pending_refreshes.get(task_key) is task:
                        self._pending_refreshes.pop(task_key)
            raise
        except Exception:
            async with self._refresh_lock:
                if self._pending_refreshes.get(task_key) is task:
                    self._pending_refreshes.pop(task_key)
                    self._failed_urls[refresh_key] = time.monotonic() + 5
            raise
        async with self._refresh_lock:
            if self._pending_refreshes.get(task_key) is task:
                if revision is not None and revision < self.active_revision_for(
                    source_id
                ):
                    self._pending_refreshes.pop(task_key)
                    return self.catalog or catalog
                current = self.catalog
                if current is not None and current is not catalog:
                    catalog = current.with_discovery_source_from(catalog, source_id)
                    resolver = ModelRoutingResolver(catalog.to_policy())
                self._snapshot = (resolver, catalog)
                self._catalog_verified = True
                if revision is not None:
                    self._active_revisions[source_id] = revision
                self._active_preparation_tokens.pop(source_id, None)
                self._failed_urls.pop(refresh_key, None)
                self._pending_refreshes.pop(task_key)
            return self.catalog or catalog

    async def prepare_catalog(
        self, path: str, *, models_url: str, source_id: str | None = None
    ) -> tuple[str, ModelCatalog]:
        from .catalog import load_model_catalog

        current = self.catalog or load_model_catalog(path)
        source = current.discovery_source(source_id)
        if source is None:
            raise ValueError(f"Unknown discovery source {source_id!r}")
        catalog = await current.resolve_discovery_async(
            models_url=models_url,
            source_id=source.source_id,
            allow_missing_default=True,
        )
        resolver = ModelRoutingResolver(catalog.to_policy())
        token = uuid4().hex
        async with self._refresh_lock:
            if len(self._prepared) >= 16:
                self._prepared.pop(next(iter(self._prepared)))
            self._prepared[token] = (resolver, catalog, source.source_id)
        return token, catalog

    async def activate_prepared_catalog(
        self, token: str, *, revision: int | None
    ) -> ModelCatalog:
        async with self._refresh_lock:
            prepared = self._prepared.get(token)
            if prepared is None:
                raise ValueError("Prepared model catalog is no longer available")
            source_id = prepared[2]
            if revision is None or revision <= self.active_revision_for(source_id):
                raise ValueError("Prepared catalog revision is stale")
            self._prepared.pop(token)
            current = self.catalog
            if current is None:
                raise ValueError("No active model catalog")
            candidate = current.with_discovery_source_from(prepared[1], prepared[2])
            prepared_resolver = ModelRoutingResolver(candidate.to_policy())
            self._activation_backups[token] = (
                current,
                source_id,
                self.active_revision_for(source_id),
                self._catalog_verified,
            )
            if len(self._activation_backups) > 16:
                self._activation_backups.pop(next(iter(self._activation_backups)))
            self._snapshot = (prepared_resolver, candidate)
            self._catalog_verified = True
            self._active_revisions[source_id] = revision
            self._active_preparation_tokens[source_id] = token
            self._failed_urls = {
                key: deadline
                for key, deadline in self._failed_urls.items()
                if key[0] != source_id
            }
            for key in tuple(self._pending_refreshes):
                if key[0] == source_id:
                    self._pending_refreshes.pop(key)
            return candidate

    async def rollback_prepared_catalog(self, token: str) -> ModelCatalog:
        async with self._refresh_lock:
            previous = self._activation_backups.pop(token, None)
            if (
                previous is not None
                and self._active_preparation_tokens.get(previous[1]) == token
            ):
                current = self.catalog
                if current is None:
                    raise ValueError("No active model catalog")
                catalog = current.with_discovery_source_from(previous[0], previous[1])
                self._snapshot = (ModelRoutingResolver(catalog.to_policy()), catalog)
                self._active_revisions[previous[1]] = previous[2]
                self._catalog_verified = previous[3] or bool(
                    catalog.verified_discovery_source_ids
                )
                self._active_preparation_tokens.pop(previous[1], None)
                for key in tuple(self._pending_refreshes):
                    if key[0] == previous[1]:
                        self._pending_refreshes.pop(key)
            current = self.catalog
            if current is None:
                raise ValueError("No active model catalog")
            return current

    def with_provider(self, provider: ModelProvider) -> RoutedChatModelFactory:
        """Same routing, models built by `provider` (a pod serving extra providers)."""
        return RoutedChatModelFactory(
            resolver=self._resolver,
            provider=provider,
            catalog=self.catalog,
            catalog_verified=self._catalog_verified,
        )

    def _chat_profile(
        self, profile_id: str | None
    ) -> tuple[ModelConfiguration, ModelProfile | None]:
        """(config, profile) for `profile_id` if it is a chat profile here, else
        the default, with one warning saying why."""
        if profile_id:
            profile = self._resolver.profile_or_none(profile_id)
            if profile is not None and profile.capability == ModelCapability.CHAT:
                return profile.model, profile
            logger.warning(
                "[MODEL_ROUTING] profile %r is %s; using the default chat profile",
                profile_id,
                "not in this pod's catalog"
                if profile is None
                else f"not a chat profile ({profile.capability.value})",
            )
        selection = self._resolver.resolve(
            ModelSelectionRequest(capability=ModelCapability.CHAT)
        )
        return selection.model, self._resolver.profile_or_none(selection.profile_id)

    def build_chat_for_profile(
        self, profile_id: str | None, *, reasoning_effort: str = "off"
    ) -> tuple[BaseChatModel, str | None, BaseChatModel | None]:
        """
        For platform helpers outside any agent turn (the creation assistant):
        the chat model of `profile_id` (else the pod default; no team routing)
        at `reasoning_effort` clamped to the profile (`_effective_reasoning_effort`),
        its name, and the same model without reasoning when it reasons, else
        None. Applied on copies: the shared catalog config is untouched.
        """
        config, profile = self._chat_profile(profile_id)
        plain = self._build_chat(without_reasoning_settings(config))
        effort = _effective_reasoning_effort(profile, reasoning_effort)
        if effort is None:
            return plain, config.name, None
        settings = {**(config.settings or {}), "reasoning_effort": effort}
        reasoning = self._build_chat(config.model_copy(update={"settings": settings}))
        return reasoning, config.name, plain

    def _build_chat(self, config: ModelConfiguration) -> BaseChatModel:
        model = self._provider.build_model(config, capability=ModelCapability.CHAT)
        if not isinstance(model, BaseChatModel):
            raise TypeError(
                "RoutedChatModelFactory expected a BaseChatModel for capability='chat'."
            )
        return model

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
            selection.source
            not in {
                ModelSelectionSource.PLATFORM_BINDING,
                ModelSelectionSource.PLATFORM_FALLBACK,
            }
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
        model = with_mistral_reasoning_replay(
            self._provider.build_model(model_config, capability=selection.capability)
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

        user_choice = self._accepted_choice(
            binding.runtime_context.chat_profile_id, binding, level="user_choice"
        )
        recommendation = self._accepted_choice(
            binding.recommended_chat_profile_id,
            binding,
            level="instance_recommendation",
        )
        removed = binding.confirmed_removed_chat_profiles
        if definition.agent_id not in self._resolver.agent_overrides_for(capability):
            candidates = (
                (binding.runtime_context.chat_profile_id, user_choice),
                (binding.recommended_chat_profile_id, recommendation),
                (binding.runtime_context.chat_default_profile_id, None),
            )
            for candidate, accepted in candidates:
                if accepted is not None:
                    break
                if (
                    candidate is None
                    or self._resolver.profile_or_none(candidate) is not None
                ):
                    continue
                removed_capability_id = removed.get(candidate)
                if removed_capability_id is None:
                    continue
                if removed_capability_id in binding.team_disabled_model_ids:
                    continue
                if (
                    binding.usable_model_ids is not None
                    and removed_capability_id not in binding.usable_model_ids
                ):
                    continue
                return self._platform_fallback_selection(binding, candidate)

        resolution = resolve_effective_chat_profile(
            agent_id=definition.agent_id,
            pod_agent_chat_profile_overrides=self._resolver.agent_overrides_for(
                capability
            ),
            pod_default_chat_profile_id=self._resolver.default_profile_id_for(
                capability
            ),
            user_chat_profile_id=user_choice,
            instance_chat_profile_id=recommendation,
            team_chat_default_profile_id=binding.runtime_context.chat_default_profile_id,
        )
        if resolution is None:
            source = next(
                (
                    item
                    for item in (self.catalog.discovery_sources if self.catalog else ())
                    if item.default_model_id is not None
                ),
                None,
            )
            if source is not None and source.default_model_id is not None:
                from hashlib import sha256

                profile_id = (
                    f"discovered.chat.{source.source_id}."
                    f"{sha256(source.default_model_id.encode('utf-8')).hexdigest()}"
                )
                removed_capability_id = removed.get(profile_id)
                if removed_capability_id is not None:
                    if removed_capability_id in binding.team_disabled_model_ids or (
                        binding.usable_model_ids is not None
                        and removed_capability_id not in binding.usable_model_ids
                    ):
                        raise ModelNotUsableError(
                            capability_id=removed_capability_id,
                            provider="openai",
                            name=source.default_model_id,
                        )
                    return self._platform_fallback_selection(binding, profile_id)
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

    def _platform_fallback_selection(
        self, binding: BoundRuntimeContext, removed_profile_id: str
    ) -> ModelSelection:
        fallback_profile_id = binding.platform_chat_model_fallback_profile_id
        if fallback_profile_id is not None:
            profile = self._resolver.profile_or_none(fallback_profile_id)
            discovered_ids = (
                set(self.catalog.discovered_profile_ids)
                if self.catalog is not None
                else set()
            )
            if (
                profile is None
                or profile.capability != ModelCapability.CHAT
                or fallback_profile_id in discovered_ids
            ):
                raise ValueError(
                    f"Platform fallback profile {fallback_profile_id!r} is unavailable"
                )
            return ModelSelection(
                source=ModelSelectionSource.PLATFORM_FALLBACK,
                capability=ModelCapability.CHAT,
                profile_id=profile.profile_id,
                model=profile.model.model_copy(deep=True),
                capability_id=profile.capability_id,
            )
        fallback = binding.platform_chat_model_fallback
        if fallback is None:
            raise ValueError(
                f"Chat profile {removed_profile_id!r} was removed and no platform fallback is configured"
            )
        settings = fallback.settings.model_dump(mode="json", exclude_none=True)
        matching = next(
            (
                profile
                for profile in self._resolver.policy.profiles
                if profile.capability == ModelCapability.CHAT
                and profile.model.provider == fallback.provider
                and profile.model.name == fallback.name
                and (profile.model.settings or {}).get("base_url")
                == settings.get("base_url")
            ),
            None,
        )
        return ModelSelection(
            source=ModelSelectionSource.PLATFORM_FALLBACK,
            capability=ModelCapability.CHAT,
            profile_id=(matching.profile_id if matching else "platform-fallback:chat"),
            model=ModelConfiguration(
                provider=fallback.provider,
                name=fallback.name,
                settings=settings,
            ),
            capability_id=(
                matching.capability_id
                if matching
                else model_capability_id(fallback.provider, fallback.name)
            ),
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
