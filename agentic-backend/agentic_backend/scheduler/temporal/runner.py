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

from __future__ import annotations

import asyncio
import logging
from typing import cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig

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
from agentic_backend.core.agents.execution_state import build_messages_state
from agentic_backend.core.agents.runtime_context import RuntimeContext
from agentic_backend.scheduler.scheduler_structures import AgentTaskInput

logger = logging.getLogger(__name__)

_runner_lock = asyncio.Lock()
_runner: "AgentTaskRunner | None" = None


def _load_configuration() -> Configuration:
    return load_configuration()


def _ensure_app_context() -> Configuration:
    try:
        return get_app_context().configuration
    except RuntimeError:
        config = _load_configuration()
        ApplicationContext(config)
        return config


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
            if self._bootstrapped:
                return
            await self._agent_manager.bootstrap()
            self._bootstrapped = True

    async def run_task(self, task: AgentTaskInput) -> dict:
        await self._ensure_bootstrapped()
        session_id = task.session_id or f"task-{uuid4()}"
        runtime_context = RuntimeContext(**(task.context or {}))
        if not runtime_context.session_id:
            runtime_context.session_id = session_id
        if task.caller_actor and not runtime_context.user_id:
            runtime_context.user_id = task.caller_actor

        agent, _ = await self._agent_factory.create_and_init(
            agent_name=task.target_agent,
            runtime_context=runtime_context,
            session_id=session_id,
        )

        config: RunnableConfig = {
            "configurable": {
                "thread_id": session_id,
                "user_id": runtime_context.user_id,
                "access_token": runtime_context.access_token,
                "refresh_token": runtime_context.refresh_token,
            }
        }
        agent.run_config = cast(RunnableConfig, config)

        try:
            compiled = agent.get_compiled_graph()
            payload = task.payload or {}
            try:
                state = build_messages_state(
                    question=payload.get("question"), payload=payload
                )
            except ValueError as exc:
                raise RuntimeError(
                    "Temporal agent payload must include a 'question' or serialized 'messages'."
                ) from exc
            invocation_state = dict(payload)
            invocation_state.update(state)
            result = await compiled.ainvoke(invocation_state, config=config)
            if isinstance(result, dict):
                return result
            return {"result": result}
        finally:
            await self._agent_factory.teardown_session_agents(session_id)


async def get_runner() -> AgentTaskRunner:
    global _runner
    if _runner is not None:
        return _runner
    async with _runner_lock:
        if _runner is not None:
            return _runner
        configuration = _ensure_app_context()
        _runner = AgentTaskRunner(configuration)
        logger.info("Agent task runner initialized.")
        return _runner
