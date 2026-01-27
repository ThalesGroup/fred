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
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from agentic_backend.application_context import (
    ApplicationContext,
    get_agent_store,
    get_app_context,
)
from agentic_backend.common.config_loader import load_configuration
from agentic_backend.common.structures import Configuration
from agentic_backend.core.agents.agent_factory import AgentFactory
from agentic_backend.core.agents.agent_loader import AgentLoader
from agentic_backend.core.agents.agent_manager import AgentManager
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.scheduler.agent_contracts import (
    AgentInputV1,
    AgentResultStatus,
    AgentResultV1,
)
from agentic_backend.scheduler.temporal.temporal_bridge import TemporalHeartbeatCallback

logger = logging.getLogger(__name__)


class AgentTaskRunner:
    def __init__(self, configuration: Configuration) -> None:
        self._configuration = configuration
        self._agent_loader = AgentLoader(configuration, get_agent_store())
        self._agent_manager = AgentManager(
            configuration, self._agent_loader, get_agent_store()
        )
        self._agent_factory = AgentFactory(
            configuration, self._agent_manager, self._agent_loader
        )
        self._bootstrapped = False
        self._bootstrap_lock = asyncio.Lock()

    async def _ensure_bootstrapped(self) -> None:
        if self._bootstrapped:
            return
        async with self._bootstrap_lock:
            if not self._bootstrapped:
                await self._agent_manager.bootstrap()
                self._bootstrapped = True

    async def run_temporal_task(self, task_input: AgentInputV1) -> AgentResultV1:
        """
        Main orchestration bridge.
        Supports:
        1. Fresh Start: No human_input provided.
        2. Resume: human_input provided, resuming from LangGraph checkpoint.
        """
        await self._ensure_bootstrapped()

        # 1. Setup Identity
        runtime_context = RuntimeContext(user_id=task_input.user_id)
        session_id = task_input.task_id  # Thread ID for LangGraph persistence

        # 2. Agent Initialization
        agent, _ = await self._agent_factory.create_and_init(
            agent_name=task_input.target_agent,
            runtime_context=runtime_context,
            session_id=session_id,
        )

        # 3. Middleware & Callbacks
        bridge = TemporalHeartbeatCallback(task_id=session_id)
        config: RunnableConfig = {
            "callbacks": [bridge],
            "configurable": {
                "thread_id": session_id,
                "user_id": task_input.user_id,
            },
        }
        agent.run_config = cast(RunnableConfig, config)

        try:
            compiled = agent.get_compiled_graph()

            # --- 4. EXECUTION LOGIC (Start vs Resume) ---
            if task_input.human_input:
                # RESUME CASE: We are being called back after a BLOCKED status.
                # We use Command(resume=...) to pass the human data directly
                # into the node that called interrupt().
                logger.info(f"Resuming agent {session_id} with human input.")
                result = await compiled.ainvoke(
                    Command(resume=task_input.human_input), config=config
                )
            else:
                # START CASE: Fresh task. Hydrate the state from the input.
                initial_state = agent.hydrate_state(task_input)
                logger.info(f"Starting agent {session_id} fresh.")
                result = await compiled.ainvoke(initial_state, config=config)

            # --- 5. POST-EXECUTION INSPECTION (HITL Check) ---
            # Check if the graph stopped because of an 'interrupt'
            state_snapshot = await compiled.aget_state(config)

            # If there are pending tasks with interrupts, the graph is 'waiting'
            if state_snapshot.tasks and any(
                task.interrupts for task in state_snapshot.tasks
            ):
                logger.info(f"Agent {session_id} hit a breakpoint. Returning BLOCKED.")
                return AgentResultV1(
                    status=AgentResultStatus.BLOCKED,
                    final_summary="Agent is waiting for human input/approval.",
                    checkpoint_ref=session_id,  # Temporal uses this to identify the thread
                    # Optional: pass the prompt from the interrupt if captured
                )

            # --- 6. COMPLETION ---
            messages = result.get("messages", [])
            final_summary = (
                messages[-1].content if messages else "Agent finished with no message."
            )

            return AgentResultV1(
                status=AgentResultStatus.COMPLETED,
                final_summary=str(final_summary),
                artifacts=result.get("artifacts", []),
                checkpoint_ref=session_id,
            )

        except Exception as e:
            logger.exception(f"Failure in LangGraph execution for task {session_id}")
            return AgentResultV1(
                status=AgentResultStatus.FAILED, final_summary=f"Error: {str(e)}"
            )
        finally:
            await self._agent_factory.teardown_session_agents(session_id)


# Singleton pattern
_runner_lock = asyncio.Lock()
_runner: AgentTaskRunner | None = None


async def get_runner() -> AgentTaskRunner:
    global _runner
    if _runner:
        return _runner
    async with _runner_lock:
        if not _runner:
            try:
                config = get_app_context().configuration
            except RuntimeError:
                config = load_configuration()
                ApplicationContext(config)
            _runner = AgentTaskRunner(config)
    return _runner
