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

import logging
from inspect import iscoroutinefunction

from agentic_backend.core.agents.agent_flow import AgentFlow
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import (
    AgentManager,  # Import the new version
)
from agentic_backend.core.agents.runtime_context import RuntimeContext

logger = logging.getLogger(__name__)


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

    def _import_agent_class(self, class_path: str):
        return self.loader._import_agent_class(class_path)

    async def create_and_init(
        self,
        agent_name: str,
        runtime_context: RuntimeContext,
    ) -> AgentFlow:
        """
        Creates a new AgentFlow instance, applies the latest settings,
        and runs its full async initialization (including MCP connection).
        """
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

        # 5. Run async initialization (This is where the token is used for MCP connection)
        if iscoroutinefunction(getattr(instance, "async_init", None)):
            logger.info(
                "[AGENTS] agent='%s' async_init invoked.",
                agent_name,
            )
            await instance.async_init(runtime_context=runtime_context)

        logger.debug("[AGENTS] agent='%s' fully initialized.", agent_name)
        return instance
