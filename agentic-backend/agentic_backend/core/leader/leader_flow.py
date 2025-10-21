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

# app/core/agents/leader_flow.py

from __future__ import annotations

from abc import abstractmethod
from contextlib import contextmanager
from typing import Iterator, cast

from langchain_core.runnables import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from agentic_backend.common.structures import AgentSettings
from agentic_backend.core.agents.agent_flow import AgentFlow


class LeaderFlow(AgentFlow):
    """
    Why LeaderFlow exists in Fred:
    - Leaders *delegate*. Every delegated call must carry the same run context
      (user/session/trace IDs, security, sampling, etc.) so downstream agents
      behave as if called directly by the end-user.
    - We centralize that rule here to avoid hand-crafting dict copies in every leader.

    Contract:
    - Subclasses manage a crew of AgentFlow experts and route work to them.
    """

    def __init__(self, agent_settings: AgentSettings):
        super().__init__(agent_settings)

    # -------------------------------
    # Delegation utilities (core idea)
    # -------------------------------

    def _clone_runnable_config(self) -> RunnableConfig:
        """
        Make a safe, shallow clone of the current run_config.

        Rationale:
        - Some LangChain/LangGraph nodes mutate `configurable`; we isolate children.
        - Always return a RunnableConfig for strict typing in leaders & experts.
        """
        base = self.run_config or {}
        if isinstance(base, dict):
            # clone and normalize the `configurable` sub-dict
            cfg = dict(base)
            conf = cfg.get("configurable")
            cfg["configurable"] = dict(conf) if isinstance(conf, dict) else {}
            return cast(RunnableConfig, cfg)
        # Non-dict configs are assumed already RunnableConfig-shaped
        return cast(RunnableConfig, base)

    def apply_run_context(self, child: AgentFlow) -> RunnableConfig:
        """
        One-liner used by leaders when delegating to an expert.

        Why:
        - Ensures children keep the same user/session/config knobs (auditing, tenancy,
          temperature, tools limits, etc.) without each leader re-implementing it.
        """
        child.run_config = self._clone_runnable_config()
        return child.run_config

    @contextmanager
    def delegated(self, child: AgentFlow) -> Iterator[RunnableConfig]:
        """
        Use as: `with self.delegated(expert) as cfg: ...`

        Why a context manager?
        - Reads clean at call sites.
        - Future-proof: if we later add per-delegation tracing spans or cleanup,
          all leaders benefit automatically.
        """
        cfg = self.apply_run_context(child)
        yield cfg

    # -------------------------------
    # Crew management (abstract API)
    # -------------------------------

    @abstractmethod
    def add_expert(
        self, name: str, instance: AgentFlow, compiled_graph: CompiledStateGraph
    ) -> None:
        """Register a compiled expert graph under a stable name."""
        ...

    @abstractmethod
    def reset_crew(self) -> None:
        """Clear all experts from this leader."""
        ...
