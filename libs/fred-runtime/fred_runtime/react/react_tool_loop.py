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
ReAct execution loop built on LangChain `create_agent` (#1972).

Why this module exists:
- keep `react_runtime.py` focused on Fred runtime orchestration
- isolate the one place where the stock `create_agent` loop is assembled with
  the fixed platform middleware frame (`react_middleware.py`): message hygiene,
  model routing, dynamic prompting, tracing/KPI, human tool approval, and the
  optional per-turn tool-call limit

History note (#1972):
- this module used to wire the hand-rolled 4-node StateGraph
  (`support/tool_loop.py build_tool_loop`); the loop is now stock
  `create_agent` and all custom node logic lives in the middleware frame.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import ChatModelFactoryPort, TracerPort
from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from .react_middleware import build_react_platform_middleware_frame

# Bounded history window for V2 ReAct — matches V1 Rico's rag.history_max_messages=6
# and prevents unbounded LangGraph checkpointer growth from contaminating queries.
_V2_MAX_HISTORY_MESSAGES = 10


def build_tool_loop_compiled_react_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    binding: BoundRuntimeContext,
    approval_policy: ToolApprovalPolicy,
    checkpointer: Checkpointer,
    chat_model_factory: ChatModelFactoryPort | None,
    definition: ReActAgentDefinition,
    infer_operation_from_messages: Callable[[Sequence[object]], str],
    default_operation: str,
    available_tool_names: set[str] | frozenset[str],
    tracer: TracerPort | None = None,
    kpi: BaseKPIWriter | None = None,
    max_tool_calls_per_turn: int | None = None,
) -> object:
    """
    Build the compiled ReAct agent: `create_agent` + the platform middleware frame.

    Why this exists:
    - plain ReAct and HITL share one execution model for message memory, tool
      execution, and deterministic filesystem continuation
    - approval is one middleware gate inside that loop, not a separate runtime

    How to use:
    - pass the already selected model, bound tools, and the composed runtime
      system prompt
    - include the current runtime tool names so filesystem follow-up context can
      be rebuilt and enforced per turn

    Example:
    - `build_tool_loop_compiled_react_agent(..., available_tool_names={"ls", "read_file"})`
    """

    middleware = build_react_platform_middleware_frame(
        binding=binding,
        definition=definition,
        approval_policy=approval_policy,
        chat_model_factory=chat_model_factory,
        infer_operation_from_messages=infer_operation_from_messages,
        default_operation=default_operation,
        available_tool_names=available_tool_names,
        tracer=tracer,
        kpi=kpi,
        max_history_messages=_V2_MAX_HISTORY_MESSAGES,
        max_tool_calls_per_turn=max_tool_calls_per_turn,
    )
    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
    )
