"""
Provider-style adapters for routed chat-model selection.

This module is intentionally not wired by default into Fred runtime creation.
It is a safe integration seam to trial centralized model routing.
"""

from __future__ import annotations

import logging
from typing import Protocol

from fred_core import get_embeddings, get_model
from fred_core.common import ModelConfiguration
from langchain_core.language_models.chat_models import BaseChatModel

from ..contracts.context import BoundRuntimeContext
from ..contracts.models import AgentDefinition
from ..contracts.runtime import ChatModelFactoryPort
from .contracts import (
    ModelCapability,
    ModelSelection,
    ModelSelectionRequest,
    ModelSelectionSource,
)
from .resolver import ModelRoutingResolver

logger = logging.getLogger(__name__)


class ModelProvider(Protocol):
    """
    Generic model provider in genai-sdk style.

    It is capability-aware (`chat`, `language`, `embedding`, `image`) so the
    selection contract is not limited to chat models.
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
    - others (`chat`, `language`, `image`) -> `fred_core.get_model(...)`

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

    Current scope:
    - chat-model selection based on agent/team/user (+ optional purpose/operation)
    - no runtime behavior change unless this factory is explicitly injected
    """

    def __init__(
        self,
        *,
        resolver: ModelRoutingResolver,
        provider: ModelProvider | None = None,
        default_purpose: str = "chat",
    ) -> None:
        self._resolver = resolver
        self._provider = provider or FredCoreModelProvider()
        self._default_purpose = default_purpose

    def build(  # type: ignore[override]
        self, definition: AgentDefinition, binding: BoundRuntimeContext
    ) -> BaseChatModel:
        """
        Why this function exists:
        - satisfy `ChatModelFactoryPort` contract expected by v2 runtimes
        - provide a default routed chat selection entrypoint

        Who calls it:
        - v2 runtime wiring when a runtime needs one chat model factory result

        When it is called:
        - typically once while runtime/loop objects are being prepared
        - not guaranteed for per-operation routing (use `build_for_chat`)

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
        model, _ = self.build_for_chat(
            definition=definition,
            binding=binding,
            purpose=self._default_purpose,
            operation=None,
        )
        return model

    def build_for_chat(
        self,
        *,
        definition: AgentDefinition,
        binding: BoundRuntimeContext,
        purpose: str,
        operation: str | None,
    ) -> tuple[BaseChatModel, ModelSelection]:
        """
        Why this function exists:
        - expose explicit chat-model routing with `purpose` + `operation`
        - return both concrete model and routing decision metadata

        Who calls it:
        - ReAct runtime middleware (phase-aware routing: routing/planning)
        - HITL model resolver path
        - generic `build(...)` wrapper

        When it is called:
        - each time runtime requests a model for one operation unless caller caches
          the model instance (ReAct middleware/HITL currently do cache per operation)

        Expected inputs / invariants:
        - `purpose` must align with routing policy conventions (`chat` today)
        - `operation` is free text but meaningful values are runtime-defined
          (`routing`, `planning`, graph node names, etc.)

        Return / side effects:
        - returns `(BaseChatModel, ModelSelection)`
        - emits info/debug logs with routing source/profile/rule metadata

        Fallback / errors:
        - resolver may fallback to policy default profile
        - raises `TypeError` if provider returns a non-chat model object
        - resolver/provider exceptions propagate

        Observability signals to look at:
        - info log on rule hit: `[V2][MODEL_ROUTING] ... source=rule rule=...`
        - debug log on default hit: `[V2][MODEL_ROUTING] ... source=default ...`
        """
        selection = self.select(
            definition=definition,
            binding=binding,
            capability=ModelCapability.CHAT,
            purpose=purpose,
            operation=operation,
        )
        model = self._provider.build_model(
            selection.model, capability=selection.capability
        )
        if not isinstance(model, BaseChatModel):
            raise TypeError(
                "RoutedChatModelFactory expected a BaseChatModel for capability='chat'."
            )
        if selection.source == ModelSelectionSource.RULE:
            logger.info(
                "[V2][MODEL_ROUTING] agent=%s source=%s rule=%s profile=%s model=%s/%s team=%s user=%s",
                definition.agent_id,
                selection.source.value,
                selection.rule_id,
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
        purpose: str,
        operation: str | None,
    ) -> ModelSelection:
        """
        Why this function exists:
        - convert runtime context (`agent/team/user/operation`) into a resolver
          request object

        Who calls it:
        - `build_for_chat(...)` today
        - can also be used directly by future non-chat routing adapters

        When it is called:
        - once per model selection attempt

        Expected inputs / invariants:
        - capability and purpose are caller-driven routing dimensions
        - binding contains portable user/team context

        Return / side effects:
        - returns immutable `ModelSelection` (selected profile + model config)
        - no side effects

        Fallback / errors:
        - resolver fallback/default and errors are handled in `ModelRoutingResolver`

        Observability signals to look at:
        - this function does not log directly
        - inspect caller logs (`build_for_chat`) for emitted routing signals
        """
        request = ModelSelectionRequest(
            capability=capability,
            purpose=purpose,
            agent_id=definition.agent_id,
            team_id=binding.portable_context.team_id,
            user_id=binding.portable_context.user_id,
            operation=operation,
        )
        return self._resolver.resolve(request)


# Backward-compatible aliases within the isolated slice.
ChatModelProvider = ModelProvider
FredCoreChatModelProvider = FredCoreModelProvider
