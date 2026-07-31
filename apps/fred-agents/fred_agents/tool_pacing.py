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
#: Real turns in this deployment use 1-4 calls (orient with the tree, search,
#: summarize a hit or two). The measured reasoning defect
#: (`AGENT-THINKING-API-RFC.md` §C.4) produced 28 duplicate calls across 10
#: turns — roughly 3 extra per turn on top of the legitimate ones, and 41
#: duplicates in the worst prompt condition (§C.7). 12 leaves ample headroom
#: for a legitimately multi-step turn while capping the pathological case.
#:
#: `exit_behavior="continue"` in the frame means hitting the cap does not error
#: the turn: the model stops getting tool calls executed and answers from what
#: it has. A user sees a normal (possibly less complete) answer, never a crash.
MAX_TOOL_CALLS_PER_TURN = 12

#: Drop-in `ReActPolicy.tool_selection` value for every tool-using ReAct agent
#: in this deployment. Applies to EVERY turn, not only reasoning ones — the RFC
#: calls this "configuration, not code" and a runaway loop is worth capping
#: whatever caused it.
REASONING_SAFE_TOOL_SELECTION = ToolSelectionPolicy(
    max_tool_calls_per_turn=MAX_TOOL_CALLS_PER_TURN,
)
