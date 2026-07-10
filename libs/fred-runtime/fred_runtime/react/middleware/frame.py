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
The fixed platform middleware frame for the ReAct `create_agent` loop (#1972).

The numbered frame order and the `create_agent` hook-order cheat sheet live in
the package docstring (`fred_runtime.react.middleware.__init__`). This module
just assembles that order.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import cast

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import ChatModelFactoryPort, TracerPort
from fred_core.kpi import BaseKPIWriter
from langchain.agents.middleware import AgentMiddleware, ToolCallLimitMiddleware

from .checkpoint_hygiene import CheckpointHygieneMiddleware
from .dynamic_prompt import DynamicPromptMiddleware
from .hitl import CapabilityHitlBinding, FredHitlMiddleware
from .model_routing import ModelRoutingMiddleware
from .tracing_kpi import TracingKpiMiddleware


def build_react_platform_middleware_frame(
    *,
    binding: BoundRuntimeContext,
    definition: ReActAgentDefinition,
    approval_policy: ToolApprovalPolicy,
    chat_model_factory: ChatModelFactoryPort | None,
    infer_operation_from_messages: Callable[[Sequence[object]], str],
    default_operation: str,
    available_tool_names: set[str] | frozenset[str],
    tracer: TracerPort | None,
    kpi: BaseKPIWriter | None,
    max_history_messages: int | None,
    max_tool_calls_per_turn: int | None = None,
    capability_middleware: Sequence[AgentMiddleware] = (),
    capability_hitl: Mapping[str, CapabilityHitlBinding] | None = None,
) -> list[AgentMiddleware]:
    """
    Assemble the fixed platform middleware frame for one ReAct agent.

    Why this exists:
    - middleware list order is semantic in `create_agent`; the platform owns
      one fixed frame so capability authors can never get the ordering wrong
      (RFC §5.3) — see the package docstring for the full order rationale

    How to use:
    - `capability_middleware` is the RESERVED capability-block slot (#1973):
      pass the concatenated capability stacks already sorted by capability id
      (`fred_runtime.capabilities.assembly` produces that order); they are
      inserted between DynamicPromptMiddleware and TracingKpiMiddleware
    - `capability_hitl` carries the capability `HitlSpec` bindings merged into
      the single FredHitlMiddleware gate (RFC §5.4) — never a second gate

    Example:
    - `build_react_platform_middleware_frame(..., capability_middleware=block.middleware, capability_hitl=block.hitl)`
    """

    frame: list[AgentMiddleware] = [
        CheckpointHygieneMiddleware(max_history_messages=max_history_messages),
        ModelRoutingMiddleware(
            chat_model_factory=chat_model_factory,
            definition=definition,
            binding=binding,
            infer_operation_from_messages=infer_operation_from_messages,
            default_operation=default_operation,
        ),
        DynamicPromptMiddleware(available_tool_names=available_tool_names),
        # --- CAPABILITY BLOCK INSERTION SLOT (#1973, RFC §5.3) ---
        *capability_middleware,
        TracingKpiMiddleware(
            tracer=tracer,
            kpi=kpi,
            binding=binding,
            infer_operation_from_messages=infer_operation_from_messages,
            default_operation=default_operation,
        ),
        FredHitlMiddleware(
            binding=binding,
            approval_policy=approval_policy,
            available_tool_names=available_tool_names,
            capability_hitl=capability_hitl,
        ),
    ]
    if max_tool_calls_per_turn is not None:
        # Listed after FredHitl on purpose: after_model hooks run in reverse
        # list order, so the limit blocks over-limit calls before the human
        # gate ever asks about them. `run_limit` == one Fred turn.
        frame.append(
            cast(
                AgentMiddleware,
                ToolCallLimitMiddleware(
                    run_limit=max_tool_calls_per_turn,
                    exit_behavior="continue",
                ),
            )
        )
    return frame
