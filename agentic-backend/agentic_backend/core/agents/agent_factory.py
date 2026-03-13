# Copyright Thales 2025
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

import asyncio
import logging
from abc import abstractmethod
from typing import Callable, Optional, Tuple, cast

from fred_core import KeycloakUser

from agentic_backend.agents.v2 import BasicReActDefinition
from agentic_backend.agents.v2.definition_refs import BASIC_REACT_DEFINITION_REF
from agentic_backend.agents.v2.production.basic_react.model_routing_presets import (
    build_default_policy_with_basic_react_presets,
)
from agentic_backend.application_context import get_kpi_writer, get_pg_async_engine
from agentic_backend.common.catalog_overrides import (
    MODEL_ROUTING_PRESETS_ENABLED_ENV,
    ModelRoutingBootstrapConfig,
)
from agentic_backend.common.structures import AgentSettings, Configuration
from agentic_backend.core.agents.agent_cache import ActiveAgentCache, AgentCacheStats
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_reference,
)
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.agent_service import AgentService
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.catalog import (
    apply_profile_defaults_to_settings,
    apply_react_profile_to_definition,
    build_bound_runtime_context,
    build_definition_from_settings,
    definition_to_agent_settings,
    instantiate_definition_class,
)
from agentic_backend.core.agents.v2.context import BoundRuntimeContext
from agentic_backend.core.agents.v2.graph_runtime import GraphRuntime
from agentic_backend.core.agents.v2.model_routing import (
    ModelRoutingResolver,
    RoutedChatModelFactory,
    load_model_routing_policy_from_catalog,
)
from agentic_backend.core.agents.v2.models import (
    AgentDefinition,
    GraphAgentDefinition,
    ReActAgentDefinition,
)
from agentic_backend.core.agents.v2.react_runtime import ReActRuntime
from agentic_backend.core.agents.v2.runtime import (
    ChatModelFactoryPort,
    RuntimeServices,
    ToolInvokerPort,
)
from agentic_backend.core.agents.v2.session_agent import V2SessionAgent
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer
from agentic_backend.core.agents.v2.toolset_registry import (
    ToolsetRuntimePorts,
    build_registered_tool_handlers,
)
from agentic_backend.integrations.v2_runtime.adapters import (
    CompositeToolInvoker,
    DefaultFredChatModelFactory,
    FredArtifactPublisher,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredResourceReader,
    build_langfuse_tracer,
)

logger = logging.getLogger(__name__)

RuntimeAgentInstance = AgentFlow | V2SessionAgent
ModelRoutingBootstrapProvider = Callable[[], ModelRoutingBootstrapConfig]


def _internal_profile_agent_id(profile_id: str) -> str:
    return f"internal.react_profile.{profile_id}"


class BaseAgentFactory:
    @abstractmethod
    async def create_and_init(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        pass

    @abstractmethod
    async def create_and_init_internal_profile(
        self,
        user: KeycloakUser,
        profile_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        pass

    @abstractmethod
    async def teardown_session_agents(self, session_id: str) -> None:
        pass

    @abstractmethod
    def release_agent(self, session_id: str, agent_id: str) -> None:
        pass

    # Lightweight observability hook
    def list_active_keys(self) -> list[tuple[str, str]]:
        """List cached (session_id, agent_id) keys if implemented; empty by default."""
        return []

    def get_cache_stats(self) -> Optional[AgentCacheStats]:
        return None


class NoOpAgentFactory(BaseAgentFactory):
    async def create_and_init(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        raise NotImplementedError("NoOpAgentFactory cannot create agents.")

    async def create_and_init_internal_profile(
        self,
        user: KeycloakUser,
        profile_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        raise NotImplementedError(
            "NoOpAgentFactory cannot create internal profile agents."
        )

    async def teardown_session_agents(self, session_id: str) -> None:
        pass

    def release_agent(self, session_id: str, agent_id: str) -> None:
        return

    def list_active_keys(self) -> list[tuple[str, str]]:
        return []


class AgentFactory(BaseAgentFactory):
    """
    Build and cache runtime agent instances for one `(session_id, agent_id)` pair.

    Pragmatic role in the stack:
    - reads authoritative agent settings through `AgentManager`/`AgentService`
    - loads/instantiates agent classes through `AgentLoader`
    - wires runtime dependencies (tools, tracing, checkpointer, model factory)
    - keeps warm instances in cache so multi-turn sessions preserve runtime state
    """

    def __init__(
        self,
        configuration: Configuration,
        manager: AgentManager,
        loader: AgentLoader,
        model_routing_bootstrap_provider: ModelRoutingBootstrapProvider,
    ):
        """
        Args:
            configuration:
                Loaded backend configuration (YAML + env-resolved values).
            manager:
                Agent catalog orchestrator. Responsible for bootstrapping configured
                agents and serving the authoritative `AgentSettings` by id.
            loader:
                Class-path loader used to import/instantiate the concrete agent
                implementation declared in settings.
            model_routing_bootstrap_provider:
                Centralized provider returning `ModelRoutingBootstrapConfig`
                (catalog path, catalog existence, preset toggle). This keeps env/path
                parsing out of factory logic.
        """
        self._configuration = configuration
        self._agent_cache: ActiveAgentCache[Tuple[str, str], RuntimeAgentInstance] = (
            ActiveAgentCache(max_size=configuration.ai.max_concurrent_agents)
        )
        self.service = AgentService(agent_manager=manager)
        self.loader = loader
        self._model_routing_bootstrap_provider = model_routing_bootstrap_provider
        self._main_event_loop = asyncio.get_event_loop()
        self._v2_checkpointer: FredSqlCheckpointer | None = None
        self._routed_chat_model_factory = self._build_routed_chat_model_factory()

    def refresh_model_routing(self) -> None:
        """
        Rebuild the routed chat-model factory from current catalog/env settings.

        This affects newly created v2 runtimes. Existing warm session runtimes
        keep their currently bound chat model until they are recreated.
        """
        self._routed_chat_model_factory = self._build_routed_chat_model_factory()

    # ---------- Public entry point ----------
    async def create_and_init(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        """
        Returns a warm agent. Reuses cache when possible; otherwise:
          1) instantiate from authoritative settings,
          2) set runtime context,
          3) initialize runtime lifecycle.
        """
        cache_key = (session_id, agent_id)
        cached = self._agent_cache.get(cache_key)
        if cached is not None:
            self._agent_cache.acquire(cache_key)
            # Why: tokens/context may change between requests; always refresh on reuse.
            if isinstance(cached, AgentFlow):
                cached.set_runtime_context(runtime_context)
            else:
                cached_portable = cached.binding.portable_context
                cached.rebind(
                    build_bound_runtime_context(
                        user=user,
                        runtime_context=runtime_context,
                        agent_id=agent_id,
                        agent_name=cached_portable.agent_name,
                        team_id=cached_portable.team_id,
                    )
                )
            logger.info(
                "[AGENTS] Reusing cached agent '%s' for session '%s'",
                agent_id,
                session_id,
            )
            return cached, True

        # Build fresh
        settings, agent = await self._instantiate_from_settings(
            user=user,
            agent_id=agent_id,
            runtime_context=runtime_context,
        )
        if isinstance(agent, AgentFlow):
            # Always apply merged settings and bind context before runtime initialization.
            # The explicit bind keeps compatibility with legacy async_init() overrides that
            # do not call super().async_init(...).
            agent.apply_settings(settings)
            agent.set_runtime_context(runtime_context)
            await self._initialize_agent(user, agent, settings, runtime_context)

        # Cache and return
        self._agent_cache.set(cache_key, agent)
        self._agent_cache.acquire(cache_key)
        logger.info(
            "[AGENTS] Created and cached agent '%s' for session '%s'",
            agent_id,
            session_id,
        )
        return agent, False

    async def create_and_init_internal_profile(
        self,
        user: KeycloakUser,
        profile_id: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[RuntimeAgentInstance, bool]:
        internal_agent_id = _internal_profile_agent_id(profile_id)
        cache_key = (session_id, internal_agent_id)
        cached = self._agent_cache.get(cache_key)
        if cached is not None:
            self._agent_cache.acquire(cache_key)
            if isinstance(cached, AgentFlow):
                cached.set_runtime_context(runtime_context)
            else:
                cached_portable = cached.binding.portable_context
                cached.rebind(
                    build_bound_runtime_context(
                        user=user,
                        runtime_context=runtime_context,
                        agent_id=internal_agent_id,
                        agent_name=cached_portable.agent_name,
                        team_id=cached_portable.team_id,
                    )
                )
            logger.info(
                "[AGENTS] Reusing cached internal profile '%s' for session '%s'",
                profile_id,
                session_id,
            )
            return cached, True

        settings, agent = await self._instantiate_from_internal_profile(
            user=user,
            profile_id=profile_id,
            runtime_context=runtime_context,
        )
        if isinstance(agent, AgentFlow):
            agent.apply_settings(settings)
            agent.set_runtime_context(runtime_context)
            await self._initialize_agent(user, agent, settings, runtime_context)

        self._agent_cache.set(cache_key, agent)
        self._agent_cache.acquire(cache_key)
        logger.info(
            "[AGENTS] Created and cached internal profile '%s' for session '%s'",
            profile_id,
            session_id,
        )
        return agent, False

    # ---------- Helpers (why-focused, no duplication) ----------

    async def _instantiate_from_settings(
        self,
        user: KeycloakUser,
        agent_id: str,
        runtime_context: RuntimeContext,
    ) -> Tuple[AgentSettings, RuntimeAgentInstance]:
        """
        Why: the Manager is the single source of truth for settings/class_path.
        Keeps class loading + validation in one place.
        """
        settings = await self.service.get_agent_by_id(user, agent_id)
        if not settings:
            raise ValueError(f"Agent '{agent_id}' not found in catalog.")
        resolved = resolve_agent_reference(
            class_path=settings.class_path,
            definition_ref=settings.definition_ref,
        )
        if resolved.implementation_kind == AgentImplementationKind.FLOW:
            agent_cls = self.loader._import_agent_class(resolved.class_path)
            agent = cast(AgentFlow, agent_cls(agent_settings=settings))
            return settings, agent

        definition = build_definition_from_settings(
            definition_class=resolved.cls,
            settings=settings,
        )
        effective_settings = apply_profile_defaults_to_settings(
            definition=definition,
            settings=settings,
        )
        if not isinstance(definition, (ReActAgentDefinition, GraphAgentDefinition)):
            raise NotImplementedError(
                f"V2 execution category '{definition.execution_category.value}' is not wired yet."
            )

        return effective_settings, self._build_v2_session_agent(
            user=user,
            runtime_context=runtime_context,
            definition=definition,
            effective_settings=effective_settings,
        )

    async def _instantiate_from_internal_profile(
        self,
        user: KeycloakUser,
        profile_id: str,
        runtime_context: RuntimeContext,
    ) -> Tuple[AgentSettings, RuntimeAgentInstance]:
        base_definition = instantiate_definition_class(BasicReActDefinition)
        definition = apply_react_profile_to_definition(base_definition, profile_id)
        internal_agent_id = _internal_profile_agent_id(profile_id)
        definition = definition.model_copy(update={"agent_id": internal_agent_id})
        settings = definition_to_agent_settings(
            definition,
            class_path=None,
            definition_ref=BASIC_REACT_DEFINITION_REF,
            enabled=True,
        )
        effective_settings = apply_profile_defaults_to_settings(
            definition=definition,
            settings=settings,
        )
        return effective_settings, self._build_v2_session_agent(
            user=user,
            runtime_context=runtime_context,
            definition=definition,
            effective_settings=effective_settings,
        )

    def _build_v2_session_agent(
        self,
        *,
        user: KeycloakUser,
        runtime_context: RuntimeContext,
        definition: AgentDefinition,
        effective_settings: AgentSettings,
    ) -> V2SessionAgent:
        binding = build_bound_runtime_context(
            user=user,
            runtime_context=runtime_context,
            agent_id=effective_settings.id,
            agent_name=effective_settings.name,
            team_id=effective_settings.team_id,
        )
        chat_model_factory = self._resolve_chat_model_factory(definition)
        base_tool_invoker = FredKnowledgeSearchToolInvoker(
            binding=binding,
            settings=effective_settings,
        )
        tool_provider = FredMcpToolProvider(
            binding=binding,
            settings=effective_settings,
        )
        artifact_publisher = FredArtifactPublisher(
            binding=binding,
            settings=effective_settings,
        )
        resource_reader = FredResourceReader(
            binding=binding,
            settings=effective_settings,
        )
        checkpointer = (
            self._get_v2_checkpointer()
            if self._configuration.ai.enable_v2_sql_checkpointer
            else None
        )
        services = RuntimeServices(
            tracer=build_langfuse_tracer(),
            chat_model_factory=chat_model_factory,
            tool_invoker=self._build_v2_tool_invoker(
                definition=definition,
                binding=binding,
                effective_settings=effective_settings,
                base_tool_invoker=base_tool_invoker,
                ports=ToolsetRuntimePorts(
                    chat_model_factory=chat_model_factory,
                    artifact_publisher=artifact_publisher,
                    resource_reader=resource_reader,
                    fallback_tool_invoker=base_tool_invoker,
                ),
            ),
            tool_provider=tool_provider,
            artifact_publisher=artifact_publisher,
            resource_reader=resource_reader,
            kpi=get_kpi_writer(),
            checkpointer=checkpointer,
        )
        if isinstance(definition, ReActAgentDefinition):
            runtime = ReActRuntime(
                definition=definition,
                services=services,
            )
        elif isinstance(definition, GraphAgentDefinition):
            runtime = GraphRuntime(
                definition=definition,
                services=services,
            )
        else:
            raise NotImplementedError(
                f"V2 execution category '{definition.execution_category.value}' is not wired yet."
            )
        runtime.bind(binding)
        return V2SessionAgent(runtime=runtime)

    def _resolve_chat_model_factory(
        self, definition: AgentDefinition
    ) -> ChatModelFactoryPort:
        """
        Why this function exists:
        - choose one chat-model factory for the runtime being built
        - keep routing on/off decision in one place

        Who calls it:
        - `_build_v2_session_agent(...)`

        When it is called:
        - once for each fresh v2 runtime construction
        - not called on every model invocation

        Expected inputs / invariants:
        - `definition` is the typed v2 definition resolved from `AgentSettings`
        - `self._routed_chat_model_factory` was already prepared at startup/refresh

        Return / side effects:
        - returns one `ChatModelFactoryPort`
        - no side effects (no I/O, no model client build)

        Fallback / errors:
        - fallback is always `DefaultFredChatModelFactory()` when routed factory
          is unavailable or definition type is not v2 ReAct/Graph
        - this function does not raise by design

        Observability signals to look at:
        - this function does not log directly
        - routing activation is observable in `_build_routed_chat_model_factory()`
          logs with prefix `[V2][MODEL_ROUTING]`
        """
        if self._routed_chat_model_factory is not None and isinstance(
            definition, (ReActAgentDefinition, GraphAgentDefinition)
        ):
            return self._routed_chat_model_factory
        return DefaultFredChatModelFactory()

    def _build_routed_chat_model_factory(self) -> RoutedChatModelFactory | None:
        """
        Why this function exists:
        - build one routed-factory snapshot for this `AgentFactory` instance
        - keep startup/refresh routing bootstrap out of runtime hot path

        Who calls it:
        - `AgentFactory.__init__` (service startup)
        - `refresh_model_routing()` (after catalog/UI changes)

        When it is called:
        - at startup and explicit refresh events
        - not called during each message turn

        Expected inputs / invariants:
        - bootstrap provider returns a valid `ModelRoutingBootstrapConfig`
          (`catalog_path`, `catalog_exists`, `presets_enabled`)
        - policy loaded from catalog/presets is compatible with resolver contracts

        Return / side effects:
        - returns `RoutedChatModelFactory` when routing is enabled
        - returns `None` when routing is disabled (default model factory path)
        - logs bootstrap decisions (`catalog` or `presets`) via logger

        Fallback / errors:
        - catalog exists but invalid -> fail fast (raises)
        - no catalog and presets disabled -> `None`
        - no catalog and presets enabled but bootstrap fails -> logs exception and
          returns `None`

        Observability signals to look at:
        - `[V2][MODEL_ROUTING] Enabled catalog routing ...`
        - `[V2][MODEL_ROUTING] Enabled preset routing ...`
        - `[V2][MODEL_ROUTING] Invalid catalog file ...`
        - fallback path: absence of the two "Enabled ..." logs and default-model
          behavior downstream
        """
        bootstrap = self._model_routing_bootstrap_provider()
        catalog_path = bootstrap.catalog_path
        catalog_exists = bootstrap.catalog_exists
        try:
            if catalog_exists:
                policy = load_model_routing_policy_from_catalog(catalog_path)
                logger.info(
                    "[V2][MODEL_ROUTING] Enabled catalog routing from %s "
                    "(main AI default model settings are ignored for routing).",
                    catalog_path,
                )
            else:
                if not bootstrap.presets_enabled:
                    return None
                policy = build_default_policy_with_basic_react_presets(
                    ai_config=self._configuration.ai,
                )
                logger.info(
                    "[V2][MODEL_ROUTING] Enabled preset routing via %s=1.",
                    MODEL_ROUTING_PRESETS_ENABLED_ENV,
                )
            resolver = ModelRoutingResolver(policy)
            return RoutedChatModelFactory(
                resolver=resolver,
                default_purpose="chat",
            )
        except Exception:
            if catalog_exists:
                logger.exception(
                    "[V2][MODEL_ROUTING] Invalid catalog file at %s. "
                    "Fix the catalog or remove it before startup.",
                    catalog_path,
                )
                raise
            logger.exception(
                "[V2][MODEL_ROUTING] Failed to initialize routed chat model factory. Falling back to default chat model."
            )
            return None

    def _build_v2_tool_invoker(
        self,
        *,
        definition: AgentDefinition,
        binding: BoundRuntimeContext,
        effective_settings: AgentSettings,
        base_tool_invoker: ToolInvokerPort,
        ports: ToolsetRuntimePorts,
    ):
        toolset_key = getattr(definition, "toolset_key", None)
        handlers = build_registered_tool_handlers(
            definition=definition,
            toolset_key=toolset_key,
            binding=binding,
            settings=effective_settings,
            ports=ports,
        )
        if not handlers:
            return base_tool_invoker
        return CompositeToolInvoker(
            handlers=handlers,
            fallback=base_tool_invoker,
        )

    def _get_v2_checkpointer(self) -> FredSqlCheckpointer:
        """
        Reuse one durable checkpointer across v2 runtimes.

        Why this matters:
        - checkpoints should survive executor rebuilds and process boundaries
        - the runtime contract should not silently depend on per-agent memory
        - Fred already owns a shared SQL engine lifecycle for durable stores
        """

        if self._v2_checkpointer is None:
            self._v2_checkpointer = FredSqlCheckpointer(
                get_pg_async_engine(),
                kpi=get_kpi_writer(),
            )
        return self._v2_checkpointer

    async def _initialize_agent(
        self,
        user: KeycloakUser,
        agent: AgentFlow,
        settings_obj: object,
        runtime_context: RuntimeContext,
    ) -> None:
        """
        Why: unify init for simple agents and leaders.
        - Simple AgentFlow: await agent.initialize_runtime(runtime_context=...)
        """
        logger.info("[AGENTS] agent='%s' initialize_runtime invoked.", agent.get_id())
        await agent.initialize_runtime(runtime_context=runtime_context)

    async def teardown_session_agents(self, session_id: str) -> None:
        """
        Asynchronously closes and removes all cached agents associated with the given session_id.
        This must be called from an async context (e.g., a FastAPI endpoint).

        Why this ? If a user leaves a conversation, we want to free up resources by closing any active agents.
        We also want to ensure that we properly await the asynchronous cleanup logic (e.g., Tessa's aclose) to prevent resource leaks.
        By iterating sequentially and awaiting each agent's aclose, we ensure a clean shutdown without overwhelming the event loop.
        """
        keys_to_clean = [
            key for key in self._agent_cache.keys() if key[0] == session_id
        ]

        # 🚨 FIX: Iterate and await SEQUENTIALLY, do NOT use asyncio.gather
        for key in keys_to_clean:
            # 1. Pop agent from cache
            agent = self._agent_cache.delete(key)

            if agent:
                # 2. Await cleanup directly in this current task
                await self._execute_aclose(agent, key)

    async def _execute_aclose(
        self, agent: RuntimeAgentInstance, key: Tuple[str, str]
    ) -> None:
        """Helper to safely execute aclose and log the result."""
        session_id, agent_id = key
        try:
            # Calls Tessa.aclose() -> MCPRuntime.aclose() -> AsyncExitStack.aclose()
            await agent.aclose()
            logger.debug(f"[AGENTS] Agent '{agent_id}' closed successfully.")
        except Exception:
            # Log the failure but ensure the task completes
            logger.error(
                f"[AGENTS] Failed to close agent '{agent_id}' for session '{session_id}'.",
                exc_info=True,
            )

    # ---------- Observability ----------
    def list_active_keys(self) -> list[tuple[str, str]]:
        try:
            return list(self._agent_cache.keys())
        except Exception:
            return []

    def release_agent(self, session_id: str, agent_id: str) -> None:
        self._agent_cache.release((session_id, agent_id))

    def get_cache_stats(self) -> Optional[AgentCacheStats]:
        return self._agent_cache.stats()
