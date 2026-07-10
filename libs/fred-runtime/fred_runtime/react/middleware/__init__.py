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
Platform middleware frame for the ReAct `create_agent` execution loop (#1972).

Why this package exists:
- the hand-rolled 4-node ReAct StateGraph (`reasoner`/`tools`/`gate_tools`/
  `tool_exec`) is replaced by stock LangChain `create_agent`; the custom node
  logic is re-homed here as five platform middleware (RFC
  docs/swift/rfc/AGENT-CAPABILITY-RFC.md §5.2–§5.4)
- the platform owns a FIXED composition frame; capability middleware (#1973)
  is inserted as a block at one reserved slot inside that frame, so capability
  authors never position themselves relative to core middleware

The frame, in `create_agent` middleware list order:

    1. CheckpointHygieneMiddleware   — request-scoped message hygiene (outermost
       `wrap_model_call`): dangling-tool-call sanitize + history trim +
       reasoning-strip, applied to the MODEL INPUT ONLY — never persisted to the
       checkpoint — plus legacy tool-output metadata attach on the response.
    2. ModelRoutingMiddleware        — per-operation model selection. Sits
       inside hygiene and outside tracing so spans/KPI record the ROUTED model.
    3. DynamicPromptMiddleware       — per-turn system-prompt suffix
       (filesystem browsing continuation context).
    4. >>> CAPABILITY BLOCK INSERTION SLOT (#1973) <<<
       Capability middleware stacks are inserted here, sorted by capability id
       (RFC §5.3). Their `wrap_model_call` nests inside the platform prompt and
       outside tracing, so observability always records the final request.
    5. TracingKpiMiddleware          — innermost `wrap_model_call`: the
       `v2.react.model` span, `llm.call_latency_ms` KPI timer, and the
       `[LLM][CALL]`/`[LLM][RESPONSE]` logs measure/describe the bare model
       call, exactly as the legacy `reasoner` node did.
    6. FredHitlMiddleware            — `after_model`: filesystem tool-argument
       rewrite + the human tool-approval gate (RFC §5.4). Sequential per-call
       `interrupt()`s with the legacy `HumanInputRequest` payload; cancel jumps
       back to the model without executing tools.
    7. ToolCallLimitMiddleware       — LangChain prebuilt, appended only when
       `max_tool_calls_per_turn` is set. Listed AFTER FredHitl on purpose:
       `after_model` hooks run in REVERSE list order, so the limit blocks
       over-limit calls BEFORE a human is asked to approve them.

Hook-order cheat sheet (`create_agent` semantics):
- `wrap_model_call`: first in list = outermost.
- `before_model`: list order. `after_model`: reverse list order.

How to use:
- call `build_react_platform_middleware_frame(...)` from the ReAct executor
  builder; pass future capability middleware through `capability_middleware`.
- import the middleware and the frame builder from this package
  (`fred_runtime.react.middleware`) — it is the canonical import point.
"""

from __future__ import annotations

from .checkpoint_hygiene import CheckpointHygieneMiddleware
from .dynamic_prompt import DynamicPromptMiddleware
from .frame import build_react_platform_middleware_frame
from .hitl import (
    FredHitlMiddleware,
    build_tool_approval_request,
)
from .model_routing import ModelRoutingMiddleware
from .tracing_kpi import TracingKpiMiddleware

__all__ = [
    "CheckpointHygieneMiddleware",
    "DynamicPromptMiddleware",
    "FredHitlMiddleware",
    "ModelRoutingMiddleware",
    "TracingKpiMiddleware",
    "build_react_platform_middleware_frame",
    "build_tool_approval_request",
]
