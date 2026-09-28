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

"""FredHitlMiddleware — filesystem arg rewrite + human tool-approval gate (#1972/#1973, RFC §5.4)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Collection, Mapping, Sequence
from typing import Any

from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ToolApprovalPolicy
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse, hook_config
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from fred_runtime.runtime_support.tool_approval import (
    CapabilityHitlBinding,
    GatedToolCall,
    ToolApproval,
    build_tool_approval_request,
    is_tool_approval_granted,
)
from fred_runtime.support.filesystem_context import rewrite_filesystem_tool_arguments

from .shared import state_messages


class FredHitlMiddleware(AgentMiddleware):
    """
    Filesystem argument rewrite + the human tool-approval gate (legacy
    `gate_tools`, RFC §5.4).

    Why this exists:
    - risky tool calls must pause for human approval with Fred's localized
      `HumanInputRequest` payload — the wire format and resume flow are frozen
      contracts. All gated calls from one model turn share a SINGLE combined
      `interrupt()` (#2177 batching): proceed/cancel already applies to the
      whole batch atomically (see below), so a folder-wide "summarize every
      document" no longer means one confirmation click per document
    - filesystem tool calls are deterministically re-anchored against the
      current browsing state before execution (and before the approval preview,
      so the human reviews the real arguments)
    - exactly ONE HITL middleware exists per agent; capability `HitlSpec`
      declarations (#1973) merge into this gate through `capability_hitl`
      bindings rather than adding more interrupt middleware

    Behavior notes (vs the legacy 4-node graph):
    - tool-call argument rewrites are applied IN PLACE on the checkpointed
      AIMessage, exactly like the legacy gate, so the updates stream carries no
      extra message events for the transcoder
    - cancel skips the entire batch and supplies a refusal result for each
      call, so the model can replan with the user's decision in its context.
    - the legacy `notes` free-text injection was dead code in the ReAct wiring
      (the approval callback never returned notes) and is not carried over

    How to use:
    - always part of the frame (the filesystem rewrite applies even when
      approval is disabled); gating is controlled by `approval_policy`
    """

    def __init__(
        self,
        *,
        binding: BoundRuntimeContext,
        approval_policy: ToolApprovalPolicy,
        available_tool_names: Collection[str],
        capability_hitl: Mapping[str, CapabilityHitlBinding] | None = None,
    ) -> None:
        super().__init__()
        self._binding = binding
        self._available_tool_names = frozenset(available_tool_names)
        self._approval = ToolApproval(
            approval_policy=approval_policy, capability_hitl=capability_hitl
        )

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        messages = state_messages(state)
        last = messages[-1] if messages else None
        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return None

        # Pass 1: filesystem rewrite (every call, gated or not) + collect
        # every call the gate decides needs approval. Rewriting must still
        # happen for ungated calls too — unchanged from before batching.
        gated: list[GatedToolCall] = []
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else None
            raw_args = tc.get("args") if isinstance(tc, dict) else {}
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            call_id = tc.get("id") if isinstance(tc, dict) else None
            if not name:
                continue
            rewritten = rewrite_filesystem_tool_arguments(
                name,
                dict(args),
                messages=messages,
                available_tool_names=self._available_tool_names,
            )
            if rewritten != args:
                args = rewritten
                tc["args"] = args
            needs_approval, question = self._approval.decision(name, tc)
            if needs_approval:
                gated.append(
                    GatedToolCall(
                        tool_call_id=call_id,
                        tool_name=name,
                        tool_args=args,
                        question=question,
                    )
                )

        # Pass 2: exactly one combined interrupt for every call that needs
        # approval — proceed/cancel already applies to the whole batch
        # atomically (a cancel skips ALL of it, gated or not — see below),
        # so a partial per-call answer was never meaningful even before this.
        if not gated:
            return None
        return self._resolve_approval(gated, tool_calls=tool_calls)

    def _resolve_approval(
        self,
        gated: Sequence[GatedToolCall],
        *,
        tool_calls: Sequence[dict[str, Any]],
    ) -> dict[str, Any] | None:
        request = build_tool_approval_request(binding=self._binding, calls=gated)
        decision = interrupt(request.model_dump(mode="json"))
        if not is_tool_approval_granted(decision):
            # Pair every skipped call so hygiene preserves the refusal for replan.
            return {
                "jump_to": "model",
                "messages": [
                    ToolMessage(
                        content=(
                            "The user rejected this tool batch. This tool was not executed. "
                            "Do not request these actions again unless the user explicitly "
                            "asks. Acknowledge the refusal and use existing information "
                            "or offer an alternative."
                        ),
                        tool_call_id=tc["id"],
                        name=tc["name"],
                        status="error",
                        additional_kwargs={"fred_tool_approval_rejected": True},
                    )
                    for tc in tool_calls
                    if tc.get("id")
                ],
            }
        return None


class DeepChildHitlMiddleware(FredHitlMiddleware):
    """Native children reuse the gate but cannot open a human approval wait."""

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        def visible(tool: BaseTool | dict[str, Any]) -> bool:
            if isinstance(tool, BaseTool):
                name = tool.name
            else:
                function = tool.get("function")
                name = (
                    function.get("name")
                    if isinstance(function, dict)
                    else tool.get("name")
                )
            if not name:
                return True
            bound = self._approval.capability_hitl.get(name)
            return not (
                self._approval.requires_human_approval(name)
                or (bound is not None and bound.spec.require)
            )

        kept = [tool for tool in request.tools if visible(tool)]
        if len(kept) != len(request.tools):
            request = request.override(tools=kept)
        return await handler(request)

    def _resolve_approval(
        self,
        gated: Sequence[GatedToolCall],
        *,
        tool_calls: Sequence[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        # A result prevents execution of that call while allowing ungated calls
        # in the same batch. Without a call ID, fail closed on the whole batch.
        if not all(call.tool_call_id for call in gated):
            return {"jump_to": "model"}
        return {
            "messages": [
                ToolMessage(
                    content=(
                        "This tool requires human approval, which is unavailable in a "
                        "delegated task. Ask the parent agent to run it directly."
                    ),
                    tool_call_id=call.tool_call_id or "",
                    name=call.tool_name,
                    status="error",
                )
                for call in gated
            ]
        }
