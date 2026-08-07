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
Graph steps for the routing probe agent (#2267).

`_make_phase_step` builds one node per typical agent phase (routing,
planning, execution). Each node calls `context.invoke_model` with that
phase's `operation` label — the same label a team-routing-policy override
row matches on — then records which model actually answered, read straight
off the LangChain response's `response_metadata` (no dependency on
fred-runtime internals: this is deliberately the same two keys any
provider-agnostic caller would read).

`finalize_step` assembles the three records into one markdown table so a
single chat turn shows the full routing decision for that turn at a glance.
"""

from __future__ import annotations

from fred_sdk import (
    GraphNodeContext,
    StepResult,
    typed_node,
)
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from .graph_state import PhaseRecord, RoutingProbeState

_NO_MODEL = "(no model configured for this pod)"


def _resolved_model_name(response: BaseMessage) -> str:
    metadata = getattr(response, "response_metadata", None) or {}
    if not isinstance(metadata, dict):
        return "(unknown)"
    name = metadata.get("model_name") or metadata.get("model")
    return name if isinstance(name, str) and name.strip() else "(unknown)"


def _make_phase_step(phase: str, operation: str):
    @typed_node(RoutingProbeState)
    async def _phase_step(
        state: RoutingProbeState,
        context: GraphNodeContext,
    ) -> StepResult:
        context.emit_status(operation, f"Running the '{phase}' phase.")

        if context.model is None:
            record = PhaseRecord(
                phase=phase,
                operation=operation,
                model_name=_NO_MODEL,
                reply="skipped — no chat model bound to this pod",
            )
            return StepResult(
                state_update={"phase_records": [*state.phase_records, record]}
            )

        response = await context.invoke_model(
            messages=[
                SystemMessage(
                    content=(
                        f"You are Fred's routing-probe agent, currently in the "
                        f"'{phase}' phase (operation label: '{operation}'). "
                        "Reply with exactly one short sentence confirming the "
                        "phase name — this reply is used to visually confirm "
                        "which model answered, nothing else."
                    )
                ),
                HumanMessage(content=state.latest_user_text),
            ],
            operation=operation,
        )
        reply = (
            response.content
            if isinstance(response.content, str)
            else str(response.content)
        )
        record = PhaseRecord(
            phase=phase,
            operation=operation,
            model_name=_resolved_model_name(response),
            reply=reply.strip(),
        )
        return StepResult(
            state_update={"phase_records": [*state.phase_records, record]}
        )

    return _phase_step


routing_step = _make_phase_step("Routing", "routing")
planning_step = _make_phase_step("Planning", "planning")
execution_step = _make_phase_step("Execution", "execution")


@typed_node(RoutingProbeState)
async def finalize_step(
    state: RoutingProbeState,
    context: GraphNodeContext,
) -> StepResult:
    """Assemble the three phase records into one summary table."""
    if state.node_error:
        return StepResult(
            state_update={
                "final_text": f"Routing probe encountered a node error: {state.node_error}",
                "done_reason": "node_error",
            }
        )
    if not state.phase_records:
        return StepResult(
            state_update={
                "final_text": "Routing probe: no phase ran.",
                "done_reason": "completed_without_summary",
            }
        )

    lines = [
        "**Routing probe — model resolved per phase:**",
        "",
        "| Phase | Operation | Model resolved | Reply |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {r.phase} | `{r.operation}` | `{r.model_name}` | {r.reply} |"
        for r in state.phase_records
    ]
    return StepResult(
        state_update={
            "final_text": "\n".join(lines),
            "done_reason": "routing_probe_complete",
        }
    )
