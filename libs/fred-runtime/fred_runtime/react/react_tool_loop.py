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
  the fixed platform middleware frame (`middleware/`): message hygiene,
  model routing, dynamic prompting, tracing/KPI, human tool approval, and the
  optional per-turn tool-call limit

History note (#1972):
- this module used to wire the hand-rolled 4-node StateGraph
  (`support/tool_loop.py build_tool_loop`); the loop is now stock
  `create_agent` and all custom node logic lives in the middleware frame.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence

from fred_core.kpi import BaseKPIWriter
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import ChatModelFactoryPort, TracerPort
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer

from .middleware import CapabilityHitlBinding, build_react_platform_middleware_frame

logger = logging.getLogger(__name__)

# Bounded history window for V2 ReAct — matches V1 Rico's rag.history_max_messages=6
# and prevents unbounded LangGraph checkpointer growth from contaminating queries.
_V2_MAX_HISTORY_MESSAGES = 500

# Size-based companion to the message-count window above (#2350, TURN-04).
#
# Why this exists: a handful of large tool outputs (a generated document, a
# big RAG hit) can push the model input tokens far past a provider's context
# window while the session stays well under _V2_MAX_HISTORY_MESSAGES. Field
# incident (2026-08-12, mistral-small-2603): a session stayed at ~25 turns
# / well under the message cap while a 115k-character tool result followed
# a few turns later by a 22k-character generated document pushed one call's
# input to 178,670 tokens (still accepted); the very next turn then failed
# outright (finish_reason="error", 0 output tokens). Message count alone
# cannot catch that.
#
# Character count, not tokens: no exact tokenizer covers every provider this
# deployment can point at (Mistral, Azure, OpenAI, ...), so this is a
# deliberately provider-agnostic proxy — same reasoning as `max_chat_input_chars`
# (#2253) for a single message. The naive "~4 chars/token" rule of thumb (used
# in an earlier revision of this constant) does NOT hold for this deployment's
# actual traffic: replaying the same field incident's persisted turn history
# against its own reported token usage gives ~1.35 characters per token for
# this French/HTML-heavy content mix (240,395 visible characters of prior
# turns fed the call that reported 178,670 input tokens) — a plain 4x
# assumption would have UNDER-protected by roughly 3x and never trimmed
# before this exact failure. 200,000 characters is calibrated off that
# measured ratio (~148k tokens equivalent): comfortably below the 178,670
# tokens that already nearly failed, while still covering routine
# single-document/single-tool-result payloads (both well under 150k
# characters here) without trimming them on their own. This is one
# deployment's measured ratio, not a universal constant — re-derive it (or at
# least sanity-check it) if the configured models or typical content mix
# change materially, and tune the raw number per deployment either way.
_V2_MAX_HISTORY_CHARS = 200_000


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
    capability_middleware: Sequence[AgentMiddleware] = (),
    capability_hitl: Mapping[str, CapabilityHitlBinding] | None = None,
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
    - `capability_middleware`/`capability_hitl` come from one
      `fred_runtime.capabilities.assembly.CapabilityAgentBlock` (#1973):
      the id-sorted capability stacks for the frame's reserved slot, and the
      `HitlSpec` bindings for the single approval gate; capability tools ride
      on their middleware (`AgentMiddleware.tools`), so `tools` stays the
      platform-resolved set

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
        max_history_chars=_V2_MAX_HISTORY_CHARS,
        max_tool_calls_per_turn=max_tool_calls_per_turn,
        capability_middleware=capability_middleware,
        capability_hitl=capability_hitl,
    )
    # Names, per middleware, exactly what tools reach `create_agent` — the
    # boundary past which tool binding is LangChain's own responsibility, not
    # ours. Pairs with `[V2][CAPABILITY]` (agent_app.py) to localize a missing
    # tool to either side of that boundary from logs alone.
    logger.debug(
        "[V2][TOOL_LOOP] agent=%s static_tools=%s middleware=%s",
        definition.agent_id,
        [t.name for t in tools],
        [
            (type(m).__name__, [t.name for t in getattr(m, "tools", [])])
            for m in middleware
        ],
    )
    return create_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=middleware,
        checkpointer=checkpointer,
    )
