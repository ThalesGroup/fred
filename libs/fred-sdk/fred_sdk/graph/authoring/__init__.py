# Copyright Thales 2026
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

"""
Authoring helpers for Fred workflow-shaped graph agents.

Why this package exists:
- keep reusable graph authoring helpers close to the graph runtime family
- provide a narrow layer that reduces ceremony without replacing LangGraph

How to use it:
- import only the helpers that remove real duplication in your graph definition
- use ``TeamAgent`` and ``AgentSpec`` when composing multiple specialists into
  a coordinated team without writing explicit nodes and state schemas

SDK extraction note:
- this entire package is part of the public authoring surface
- it does not import Fred platform internals and is safe to publish as a
  standalone SDK package without modification

Example (single graph agent):
- ``from fred_sdk.graph.authoring import typed_node``

Example (multi-agent team):
- ``from fred_sdk.graph.authoring import TeamAgent, AgentSpec``
"""

from ..runtime import AgentInvocationResult
from .api import (
    GraphAgent,
    GraphWorkflow,
    StepResult,
    WorkflowNode,
    choice_step,
    finalize_step,
    intent_router_step,
    model_text_step,
    structured_model_step,
    typed_node,
)
from .team_api import (
    AgentSpec,
    TeamAgent,
    TeamInput,
    TeamMemberResult,
    TeamState,
)

__all__ = [
    # Single-agent graph authoring
    "GraphAgent",
    "GraphWorkflow",
    "StepResult",
    "WorkflowNode",
    "choice_step",
    "finalize_step",
    "intent_router_step",
    "model_text_step",
    "structured_model_step",
    "typed_node",
    # Agent invocation result — the typed output of invoke_agent()
    "AgentInvocationResult",
    # Multi-agent team authoring
    "AgentSpec",
    "TeamAgent",
    "TeamInput",
    "TeamMemberResult",
    "TeamState",
]
