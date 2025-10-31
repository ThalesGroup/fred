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
from collections import defaultdict
from inspect import iscoroutinefunction
from typing import Tuple, cast

from fred_core import ThreadSafeLRUCache

from agentic_backend.common.structures import Leader
from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import (
    AgentManager,  # Import the new version
)
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.core.leader.leader_flow import LeaderFlow

logger = logging.getLogger(__name__)

# Why: Agents are recreated per request. We keep one warm AgentFlow per (session, agent)
# so tool working state (e.g., Tessa's selected DB + loaded tables) survives the next call.
_AGENT_CACHE: ThreadSafeLRUCache[Tuple[str, str], AgentFlow] = ThreadSafeLRUCache(
    max_size=128
)

# Optional but recommended: per-key lock to avoid double-builds when two requests arrive together
_AGENT_LOCKS: dict[Tuple[str, str], asyncio.Lock] = defaultdict(asyncio.Lock)


def _agent_cache_get(session_id: str, agent_name: str) -> AgentFlow | None:
    return _AGENT_CACHE.get((session_id, agent_name))


def _agent_cache_set(session_id: str, agent_name: str, agent: AgentFlow) -> None:
    _AGENT_CACHE.set((session_id, agent_name), agent)


def _agent_cache_delete(session_id: str, agent_name: str) -> None:
    # If you add a .close() on AgentFlow later, call it here before delete.
    _AGENT_CACHE.delete((session_id, agent_name))


class AgentFactory:
    """
    Factory responsible for creating a **transient, per-request** AgentFlow instance.

    This service ensures:
    1. The agent is always initialized with the latest persisted settings.
    2. The agent's MCP client is connected using the **current user's tokens (from cfg)**.
    3. The agent is disposable and must be closed after use.
    """

    def __init__(self, manager: AgentManager, loader: AgentLoader):
        self.manager = manager
        self.loader = loader
        self.cached_agent: AgentFlow | None = None

    def _import_agent_class(self, class_path: str):
        return self.loader._import_agent_class(class_path)

    async def create_and_init(
        self, agent_name: str, runtime_context: RuntimeContext, session_id: str
    ) -> AgentFlow:
        """
        Creates a new AgentFlow instance, applies the latest settings,
        and runs its full async initialization (including MCP connection).
        """
        cache_key = (session_id or "anon-session", agent_name)
        lock = _AGENT_LOCKS[cache_key]
        async with lock:
            cached = _agent_cache_get(*cache_key)
            if cached is not None:
                # Make sure fresh tokens/context are visible to the reused instance.
                try:
                    cached.set_runtime_context(runtime_context)
                except Exception:
                    setattr(cached, "runtime_context", runtime_context)
                logger.info(
                    "[AGENTS] Reusing cached agent '%s' for session '%s'",
                    agent_name,
                    session_id,
                )
                return cached

            # self.manager.log_current_settings()
            # 1. Get the latest authoritative settings from the Manager's catalog.
            settings = self.manager.get_agent_settings(agent_name)

            if not settings:
                raise ValueError(f"Agent '{agent_name}' not found in catalog.")

            # 2. Get the agent class (Manager's internal loader is the source of truth)
            if not settings.class_path:
                raise ValueError(f"Agent '{agent_name}' has no class_path defined.")

            agent_cls = self.loader._import_agent_class(settings.class_path)

            # 3. Instantiate the agent. CRITICAL: Pass the user's cfg/context.
            #    The cfg is injected as self.cfg and contains 'access_token', 'refresh_token'.
            instance = agent_cls(agent_settings=settings)

            # 4. Apply merged settings and set runtime context.
            #    Note: settings are merged on the class by the manager.
            instance.apply_settings(settings)
            if runtime_context:
                instance.set_runtime_context(runtime_context)

            # Check if the instance is of type LeaderFlow. If so we must create its crew agents
            if isinstance(instance, LeaderFlow):
                leader_settings = cast(Leader, settings)
                expert_agents = {}
                for expert_name in leader_settings.crew:
                    expert_settings = self.manager.get_agent_settings(expert_name)
                    if not expert_settings:
                        raise ValueError(
                            f"Expert agent '{expert_name}' not found in catalog."
                        )
                    if not expert_settings.class_path:
                        raise ValueError(
                            f"Expert agent '{expert_name}' has no class_path defined."
                        )
                    expert_cls = self.loader._import_agent_class(
                        expert_settings.class_path
                    )
                    expert_instance = expert_cls(agent_settings=expert_settings)
                    expert_instance.apply_settings(expert_settings)
                    expert_instance.set_runtime_context(runtime_context)
                    if iscoroutinefunction(
                        getattr(expert_instance, "async_init", None)
                    ):
                        logger.info(
                            "[AGENTS] agent='%s' async_init invoked.",
                            expert_name,
                        )
                        await expert_instance.async_init(
                            runtime_context=runtime_context
                        )
                    expert_agents[expert_name] = expert_instance
                # TODO call the LeaderFlow instance async_init with the runtime_context AND the list of AgentFlow experts
                await instance.async_init(runtime_context, expert_agents)
            elif isinstance(instance, AgentFlow):
                # 5. Run async initialization (This is where the token is used for MCP connection)
                logger.info(
                    "[AGENTS] agent='%s' async_init invoked.",
                    agent_name,
                )
                if iscoroutinefunction(getattr(instance, "async_init", None)):
                    await instance.async_init(runtime_context=runtime_context)

            logger.debug("[AGENTS] agent='%s' fully initialized.", agent_name)
            _agent_cache_set(*cache_key, instance)
            logger.info(
                "[AGENTS] Cached agent '%s' for session '%s'", agent_name, session_id
            )
            return instance
