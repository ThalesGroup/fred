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

"""Shared tool-pacing policy for this deployment's ReAct agents.

Precondition 1 of `MODEL-REASONING-ENABLEMENT-RFC.md` §9: activate the runaway
guardrail BEFORE levels 3-4 let an agent author and an end user turn reasoning
on per question.

`ToolCallLimitMiddleware` has been wired in the ReAct frame all along
(`react/middleware/frame.py`) but inert, because `max_tool_calls_per_turn`
defaults to `None` and no agent in this deployment set it
(`AGENT-THINKING-API-RFC.md` §C.8 measured exactly that: "Implemented … but
active? No"). One shared constant here rather than a literal in five
`policy()` methods, so the deployment has one number to reason about.
"""

from __future__ import annotations

from fred_sdk.contracts.models import ToolSelectionPolicy

#: Tool calls one assistant turn may make before the runtime stops issuing more.
#:
#: Sized to be invisible in normal use and to bite only a genuine runaway.
#: An ordinary turn uses 1-4 calls, but a `run_subagent` fan-out is one turn
#: too: a handful of discovery calls plus a dozen delegations is legitimate,
#: and under the old ceiling of 12 the surplus calls were dropped silently.
#: The measured reasoning defect (`AGENT-THINKING-API-RFC.md` §C.4) produced
#: 28 duplicate calls across 10 turns, 41 in the worst prompt condition (§C.7);
#: 30 still caps that while leaving a wide fan-out room to complete.
#:
#: `exit_behavior="continue"` in the frame means hitting the cap does not error
#: the turn — but it does not warn either: an over-limit call comes back as a
#: successful tool result reading "Tool call limit exceeded", so an orchestrator
#: cannot tell that a delegation never ran. Raise this before widening fan-out.
MAX_TOOL_CALLS_PER_TURN = 200

#: Drop-in `ReActPolicy.tool_selection` value for every tool-using ReAct agent
#: in this deployment. Applies to EVERY turn, not only reasoning ones — the RFC
#: calls this "configuration, not code" and a runaway loop is worth capping
#: whatever caused it.
REASONING_SAFE_TOOL_SELECTION = ToolSelectionPolicy(
    max_tool_calls_per_turn=MAX_TOOL_CALLS_PER_TURN,
)
