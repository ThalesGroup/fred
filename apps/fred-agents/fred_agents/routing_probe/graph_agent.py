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
Graph definition for the routing probe agent (#2267).

Purpose:
- Let a team admin validate team-level model-routing overrides — both
  operation-wide rules (`operation="planning"`, agent left to "Any") and
  per-agent rules (`operation="planning"`, agent scoped to one of the two
  instances below) — by chatting with a real agent instead of reading code.
- Every turn runs three phases (`routing`, `planning`, `execution`), one
  `invoke_model` call each with that phase's operation label, and replies
  with a table of which model actually answered each phase.

Two distinct `agent_id`s (not two instances of one class) are needed because
the team-routing agent selector (`TeamSettingsRouting.tsx`) is fed by
`source_agent_id`, deduplicated per class — an agent-scoped override targets
a class, not one enrolled instance. Enroll both `routing_probe_alpha` and
`routing_probe_beta` in the same team to compare an operation-wide rule
(applies to both) against an agent-scoped rule (applies to only one).

No MCP server or declared tool is needed — only `invoke_model`. When no chat
model is bound to the pod, each phase reports "no model configured" instead
of failing, so the agent still loads and runs end to end.
"""

from __future__ import annotations

from fred_sdk import GraphAgent, GraphWorkflow

from .graph_state import RoutingProbeInput, RoutingProbeState
from .graph_steps import (
    execution_step,
    finalize_step,
    planning_step,
    routing_step,
)

_ROUTING_PROBE_DESCRIPTION = (
    "Graph agent that runs one model call per typical agent phase (routing, "
    "planning, execution) and reports which model answered each — a live "
    "probe for team-level model-routing overrides (operation-wide and "
    "per-agent). Send any message to run all three phases."
)

_ROUTING_PROBE_WORKFLOW = GraphWorkflow(
    entry="routing",
    nodes={
        "routing": routing_step,
        "planning": planning_step,
        "execution": execution_step,
        "finalize": finalize_step,
    },
    edges={
        "routing": "planning",
        "planning": "execution",
        "execution": "finalize",
    },
    error_routes={
        "routing": "finalize",
        "planning": "finalize",
        "execution": "finalize",
    },
)


class RoutingProbeGraphAgent(GraphAgent):
    """
    Model-routing test probe (#2267). See module docstring for why two
    `agent_id`s exist — instantiate this class once per probe identity
    rather than subclassing; only `agent_id`/`role`/`description` differ.
    """

    agent_id: str = "fred.github.routing_probe"
    role: str = "Routing Probe"
    description: str = _ROUTING_PROBE_DESCRIPTION
    tags: tuple[str, ...] = ("test", "graph", "routing", "dev")

    input_schema = RoutingProbeInput
    state_schema = RoutingProbeState
    input_to_state = {"message": "latest_user_text"}
    output_state_field = "final_text"

    workflow = _ROUTING_PROBE_WORKFLOW


ROUTING_PROBE_ALPHA_AGENT = RoutingProbeGraphAgent(
    agent_id="fred.github.routing_probe_alpha",
    role="Routing Probe — Alpha",
    description=_ROUTING_PROBE_DESCRIPTION
    + " (Alpha — pair with Beta to compare an operation-wide override "
    "against one scoped to a single agent.)",
)

ROUTING_PROBE_BETA_AGENT = RoutingProbeGraphAgent(
    agent_id="fred.github.routing_probe_beta",
    role="Routing Probe — Beta",
    description=_ROUTING_PROBE_DESCRIPTION
    + " (Beta — pair with Alpha to compare an operation-wide override "
    "against one scoped to a single agent.)",
)
