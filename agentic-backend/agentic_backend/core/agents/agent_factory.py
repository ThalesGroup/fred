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
from typing import Dict, Optional, Tuple, cast

from pyparsing import abstractmethod

from agentic_backend.common.structures import AgentSettings, Configuration, Leader
from agentic_backend.core.agents.agent_cache import ActiveAgentCache, AgentCacheStats
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.leader.leader_flow import LeaderFlow

logger = logging.getLogger(__name__)


class BaseAgentFactory:
    @abstractmethod
    async def create_and_init(
        self,
        agent_name: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[AgentFlow, bool]:
        pass

    @abstractmethod
    async def teardown_session_agents(self, session_id: str) -> None:
        pass

    @abstractmethod
    def release_agent(self, session_id: str, agent_name: str) -> None:
        pass

    # Lightweight observability hook
    def list_active_keys(self) -> list[tuple[str, str]]:
        """List cached (session_id, agent_name) keys if implemented; empty by default."""
        return []

    def get_cache_stats(self) -> Optional[AgentCacheStats]:
        return None


class NoOpAgentFactory(BaseAgentFactory):
    async def create_and_init(
        self,
    ) -> Tuple[AgentFlow, bool]:
        raise NotImplementedError("NoOpAgentFactory cannot create agents.")

    async def teardown_session_agents(self, session_id: str) -> None:
        pass

    def release_agent(self, session_id: str, agent_name: str) -> None:
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
        self._agent_cache: ActiveAgentCache[Tuple[str, str], AgentFlow] = (
            ActiveAgentCache(max_size=configuration.ai.max_concurrent_agents)
        )
        self.manager = manager
        self.loader = loader
        self._main_event_loop = asyncio.get_event_loop()

    # ---------- Public entry point ----------
    async def create_and_init(
        self,
        agent_name: str,
        runtime_context: RuntimeContext,
        session_id: str,
    ) -> Tuple[AgentFlow, bool]:
        """
        Returns a warm agent. Reuses cache when possible; otherwise:
          1) instantiate from authoritative settings,
          2) set runtime context,
          3) run async init (with crew when Leader).
        """
        cache_key = (session_id, agent_name)
        cached = self._agent_cache.get(cache_key)
        if cached is not None:
            self._agent_cache.acquire(cache_key)
            # Why: tokens/context may change between requests; always refresh on reuse.
            try:
                cached.set_runtime_context(runtime_context)
            except Exception:
                setattr(cached, "runtime_context", runtime_context)
            logger.info(
                "[AGENTS] Reusing cached agent '%s' for session '%s'",
                agent_name,
                session_id,
            )
            return cached, True

        # Build fresh
        settings, agent = self._instantiate_from_settings(agent_name)

        # Always apply merged settings and context before init
        agent.apply_settings(settings)
        if runtime_context:
            agent.set_runtime_context(runtime_context)

        # Initialize (Leader vs simple Agent handled here)
        await self._initialize_agent(agent, settings, runtime_context)

        # Cache and return
        self._agent_cache.set(cache_key, agent)
        self._agent_cache.acquire(cache_key)
        logger.info(
            "[AGENTS] Created and cached agent '%s' for session '%s'",
            agent_name,
            session_id,
        )
        return agent, False

    # ---------- Helpers (why-focused, no duplication) ----------

    def _instantiate_from_settings(
        self, agent_name: str
    ) -> Tuple[AgentSettings, AgentFlow]:
        """
        Why: the Manager is the single source of truth for settings/class_path.
        Keeps class loading + validation in one place.
        """
        settings = self.manager.get_agent_settings(agent_name)
        if not settings:
            raise ValueError(f"Agent '{agent_name}' not found in catalog.")
        if not settings.class_path:
            raise ValueError(f"Agent '{agent_name}' has no class_path defined.")
        agent_cls = self.loader._import_agent_class(settings.class_path)
        agent = cast(AgentFlow, agent_cls(agent_settings=settings))
        return settings, agent

    async def _initialize_agent(
        self,
        agent: AgentFlow,
        settings_obj: object,
        runtime_context: RuntimeContext,
    ) -> None:
        """
        Why: unify init for simple agents and leaders.
        - Simple AgentFlow: await agent.async_init(runtime_context=...)
        - LeaderFlow: build crew once, then await leader.async_init(runtime_context, crew)
        """
        if isinstance(agent, LeaderFlow):
            crew = await self._build_leader_crew(
                cast(Leader, settings_obj), runtime_context
            )
            logger.info(
                "[AGENTS] leader='%s' async_init invoked (crew size=%d).",
                agent.get_name(),
                len(crew),
            )
            await agent.async_init(runtime_context, crew)
            return

        # Simple agent
        if hasattr(agent, "async_init"):
            logger.info("[AGENTS] agent='%s' async_init invoked.", agent.get_name())
            await agent.async_init(runtime_context=runtime_context)

    async def _build_leader_crew(
        self,
        leader_settings: Leader,
        runtime_context: RuntimeContext,
    ) -> Dict[str, AgentFlow]:
        """
        Why: leaders orchestrate expert agents. We build each expert exactly like a simple agent:
        instantiate → apply settings → set context → async_init — then hand to the Leader.
        """
        crew: Dict[str, AgentFlow] = {}
        for expert_name in leader_settings.crew:
            expert_settings, expert = self._instantiate_from_settings(expert_name)
            expert.apply_settings(expert_settings)
            expert.set_runtime_context(runtime_context)
            if hasattr(expert, "async_init"):
                logger.info(
                    "[AGENTS] expert='%s' async_init invoked.", expert.get_name()
                )
                await expert.async_init(runtime_context=runtime_context)
            crew[expert_name] = expert
        return crew

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

    async def _execute_aclose(self, agent: AgentFlow, key: Tuple[str, str]) -> None:
        """Helper to safely execute aclose and log the result."""
        session_id, agent_name = key
        try:
            # Calls Tessa.aclose() -> MCPRuntime.aclose() -> AsyncExitStack.aclose()
            await agent.aclose()
            logger.debug(f"[AGENTS] Agent '{agent_name}' closed successfully.")
        except Exception:
            # Log the failure but ensure the task completes
            logger.error(
                f"[AGENTS] Failed to close agent '{agent_name}' for session '{session_id}'.",
                exc_info=True,
            )

    # ---------- Observability ----------
    def list_active_keys(self) -> list[tuple[str, str]]:
        try:
            return list(self._agent_cache.keys())
        except Exception:
            return []

    def release_agent(self, session_id: str, agent_name: str) -> None:
        self._agent_cache.release((session_id, agent_name))

    def get_cache_stats(self) -> Optional[AgentCacheStats]:
        return self._agent_cache.stats()
