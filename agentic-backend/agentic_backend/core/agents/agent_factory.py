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
from typing import Optional, Tuple, cast

from fred_core import KeycloakUser

from agentic_backend.application_context import get_kpi_writer, get_pg_async_engine
from agentic_backend.common.structures import AgentSettings, Configuration
from agentic_backend.agents.v2 import BasicReActV2Definition
from agentic_backend.core.agents.agent_cache import ActiveAgentCache, AgentCacheStats
from agentic_backend.core.agents.agent_class_resolver import (
    AgentImplementationKind,
    resolve_agent_class,
)
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.agent_service import AgentService
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.agents.v2.adapters import (
    DefaultFredChatModelFactory,
    FredArtifactPublisher,
    FredKnowledgeSearchToolInvoker,
    FredMcpToolProvider,
    FredResourceReader,
)
from agentic_backend.core.agents.v2.catalog import (
    apply_react_profile_to_definition,
    apply_profile_defaults_to_settings,
    build_bound_runtime_context,
    build_definition_from_settings,
    definition_to_agent_settings,
    instantiate_definition_class,
)
from agentic_backend.core.agents.v2.graph_runtime import GraphRuntime
from agentic_backend.core.agents.v2.models import (
    AgentDefinition,
    GraphAgentDefinition,
    ReActAgentDefinition,
)
from agentic_backend.core.agents.v2.react_runtime import ReActRuntime
from agentic_backend.core.agents.v2.runtime import RuntimeServices
from agentic_backend.core.agents.v2.session_agent import V2SessionAgent
from agentic_backend.core.agents.v2.sql_checkpointer import FredSqlCheckpointer

logger = logging.getLogger(__name__)

RuntimeAgentInstance = AgentFlow | V2SessionAgent


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
    ) -> Tuple[RuntimeAgentInstance, bool]:
        raise NotImplementedError("NoOpAgentFactory cannot create agents.")

    async def create_and_init_internal_profile(
        self,
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
    Factory that returns a **warm, per-(session, agent)** instance.
    Why Fred caches: we persist tool working state across messages (e.g., Tessa’s selected DB).
    """

    def __init__(
        self, configuration: Configuration, manager: AgentManager, loader: AgentLoader
    ):
        self._agent_cache: ActiveAgentCache[Tuple[str, str], RuntimeAgentInstance] = (
            ActiveAgentCache(max_size=configuration.ai.max_concurrent_agents)
        )
        self.service = AgentService(agent_manager=manager)
        self.loader = loader
        self._main_event_loop = asyncio.get_event_loop()
        self._v2_checkpointer: FredSqlCheckpointer | None = None

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
                cached.rebind(
                    build_bound_runtime_context(
                        user=user,
                        runtime_context=runtime_context,
                        agent_id=agent_id,
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
                cached.rebind(
                    build_bound_runtime_context(
                        user=user,
                        runtime_context=runtime_context,
                        agent_id=internal_agent_id,
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
        if not settings.class_path:
            raise ValueError(f"Agent '{agent_id}' has no class_path defined.")
        resolved = resolve_agent_class(settings.class_path)
        if resolved.implementation_kind == AgentImplementationKind.FLOW:
            agent_cls = self.loader._import_agent_class(settings.class_path)
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
        base_definition = instantiate_definition_class(BasicReActV2Definition)
        definition = apply_react_profile_to_definition(base_definition, profile_id)
        internal_agent_id = _internal_profile_agent_id(profile_id)
        definition = definition.model_copy(update={"agent_id": internal_agent_id})
        settings = definition_to_agent_settings(
            definition,
            class_path="agentic_backend.agents.v2.basic_react.BasicReActV2Definition",
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
        )
        services = RuntimeServices(
            chat_model_factory=DefaultFredChatModelFactory(),
            tool_invoker=FredKnowledgeSearchToolInvoker(
                binding=binding,
                settings=effective_settings,
            ),
            tool_provider=FredMcpToolProvider(
                binding=binding,
                settings=effective_settings,
            ),
            artifact_publisher=FredArtifactPublisher(
                binding=binding,
                settings=effective_settings,
            ),
            resource_reader=FredResourceReader(
                binding=binding,
                settings=effective_settings,
            ),
            checkpointer=self._get_v2_checkpointer(),
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
