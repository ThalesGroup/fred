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
Shared helper for the ReAct platform middleware frame (#1972).

Why this module exists:
- several middleware in the frame read the raw checkpointed message history the
  same way; keeping that single reader here avoids duplicating the logic per
  middleware module.
"""

from __future__ import annotations

from typing import Any, Optional

from fred_sdk.contracts.context import BoundRuntimeContext


def identity_kpi_dims(binding: BoundRuntimeContext) -> dict[str, Optional[str]]:
    """
    Identity/correlation dims for a KPI or audit event tied to one bound turn.

    Why this exists:
    - mirrors `ToolObservabilityMiddleware._base_dims`'s identity block
      (only identifiers, never content — session/user/team/correlation, never
      message text); factored out here so a second KPI call site
      (`CheckpointHygieneMiddleware`, #2350) doesn't hand-roll a diverging copy
    - only identifiers, on purpose: `PROMETHEUS_ALLOWED_LABELS`
      (`prometheus_kpi_store.py`) strips user/session/team identity before a
      metric reaches Prometheus, but the full set still carries through to the
      KPI store's other consumers (e.g. audit-adjacent product analytics) —
      see `docs/swift/platform/OBSERVABILITY-AND-AUDIT.md` §3
    """
    portable = binding.portable_context
    dims: dict[str, Optional[str]] = {}
    if portable.session_id:
        dims["session_id"] = portable.session_id
    if portable.user_id:
        dims["user_id"] = portable.user_id
    if portable.team_id:
        dims["team_id"] = portable.team_id
    agent_instance_id = portable.baggage.get("agent_instance_id")
    if agent_instance_id:
        dims["agent_instance_id"] = agent_instance_id
    template_agent_id = portable.baggage.get("template_agent_id")
    if template_agent_id:
        dims["template_agent_id"] = template_agent_id
    if portable.correlation_id:
        dims["correlation_id"] = portable.correlation_id
    if portable.trace_id:
        dims["trace_id"] = portable.trace_id
    return dims


def state_messages(state_like: object) -> list[Any]:
    """
    Read the raw (unsanitized) message history from one agent state mapping.

    Why this exists:
    - routing, prompt, tracing, and HITL decisions are all made against the RAW
      checkpointed history, exactly as the legacy `reasoner`/`gate_tools` nodes
      did; only the model input goes through hygiene

    How to use:
    - pass `request.state` or the `after_model` state argument
    """

    messages = state_like.get("messages", []) if isinstance(state_like, dict) else []
    return messages if isinstance(messages, list) else []
