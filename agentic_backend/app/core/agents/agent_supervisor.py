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
from collections.abc import Mapping
import logging
from inspect import iscoroutinefunction
from typing import Awaitable, Callable, Iterable

# ❌ remove anyio.abc TaskGroup import; we won't accept a TG anymore
# import anyio
# from anyio.abc import TaskGroup

from app.core.agents.flow import AgentFlow
from app.agents.leader.leader import Leader

logger = logging.getLogger(__name__)


class AgentSupervisor:
    """
    Owns long-lived agent work and cleanup.

    Responsibilities:
    - Close agents via `aclose()` from the SAME task on shutdown.
    - Run a retry loop (provided a retry coroutine).
    - Inject experts into leaders after (re)loads.
    """

    def __init__(self) -> None:
        # ❌ These fields were never set/used; remove them
        # self._retry_scope: anyio.CancelScope | None = None
        # self._retry_task: asyncio.Task | None = None
        pass

    async def close_agents(self, agents: Iterable[AgentFlow]) -> None:
        for agent in agents:
            close = getattr(agent, "aclose", None)
            if iscoroutinefunction(close):
                try:
                    await close()
                except Exception:
                    logger.debug(
                        "Agent %s aclose() failed (ignored).",
                        getattr(agent, "name", "<unnamed>"),
                    )

    # ------------
    # Retry engine
    # ------------

    # ✅ Drop the TaskGroup parameter; the caller just schedules this as an asyncio task.
    async def run_retry_loop(self, retry_fn: Callable[[], Awaitable[None]]):
        """
        Long-lived retry loop. Caller is responsible for task lifecycle
        (start with asyncio.create_task; cancel on shutdown).
        """
        try:
            while True:
                await asyncio.sleep(10)
                try:
                    await retry_fn()
                except asyncio.CancelledError:
                    # graceful shutdown
                    raise
                except Exception:
                    logger.exception("Retry loop threw; continuing.")
        except asyncio.CancelledError:
            logger.info("Retry loop cancelled; exiting cleanly.")

    def stop_retry_loop(self) -> None:
        """
        No-op in the current design: the AgentManager cancels the task that runs
        `run_retry_loop`. Kept for API compatibility.
        """
        return

    # --------------------------
    # Leader–expert integration
    # --------------------------

    def inject_experts_into_leaders(
        self,
        *,
        agents_by_name: Mapping[str, AgentFlow],
        settings_by_name: Mapping[str, object],
        classes_by_name: Mapping[str, type],
    ) -> None:
        for leader_name, leader_settings in settings_by_name.items():
            if getattr(leader_settings, "type", None) != "leader":
                continue

            leader_instance = agents_by_name.get(leader_name)
            if not isinstance(leader_instance, Leader):
                continue

            for expert_name, expert_cls in classes_by_name.items():
                if expert_name == leader_name:
                    continue
                if not issubclass(expert_cls, AgentFlow):
                    continue

                expert_instance = agents_by_name.get(expert_name)
                if not isinstance(expert_instance, AgentFlow):
                    continue

                compiled = expert_instance.get_compiled_graph()
                leader_instance.add_expert(expert_name, expert_instance, compiled)
                logger.info(
                    "👥 Added expert '%s' to leader '%s'", expert_name, leader_name
                )
