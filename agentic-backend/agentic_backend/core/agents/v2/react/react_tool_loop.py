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
Shared LangChain/LangGraph ReAct tool loop.

Why this module exists:
- keep `react_runtime.py` focused on Fred runtime orchestration
- isolate the LangChain/LangGraph execution loop plus the small Fred additions
  that legitimately belong around it: approval gating, model routing, and
  deterministic filesystem continuation
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.graph import MessagesState
from langgraph.types import Checkpointer, interrupt

from agentic_backend.core.tools.tool_loop import build_tool_loop

from ..contracts.context import BoundRuntimeContext
from ..contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from ..contracts.runtime import HumanChoiceOption, HumanInputRequest
from ..model_routing import RoutedChatModelFactory
from ..support.filesystem_context import (
    render_filesystem_browsing_context,
    rewrite_filesystem_tool_arguments,
)
from ..support.tool_approval import requires_tool_approval

# Bounded history window for V2 ReAct — matches V1 Rico's rag.history_max_messages=6
# and prevents unbounded LangGraph checkpointer growth from contaminating queries.
_V2_MAX_HISTORY_MESSAGES = 10


def _truncate_for_human_review(value: object, *, max_chars: int = 1200) -> str:
    """
    Render one tool-argument preview for approval UIs.

    Why this exists:
    - approval requests should show the human a bounded preview of the pending tool call
    - one helper keeps the preview formatting stable across all approval prompts

    How to use:
    - pass any tool-argument object before storing it in `HumanInputRequest.metadata`

    Example:
    - `_truncate_for_human_review({"path": "/corpus/CIR"})`
    """

    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except Exception:
        rendered = str(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."


def _is_french_language(language: str | None) -> bool:
    """
    Tell whether the runtime language should use the French approval copy.

    Why this exists:
    - approval questions have a small localized French variant
    - one helper keeps the language switch simple and explicit

    How to use:
    - pass the runtime language hint from the bound context

    Example:
    - `_is_french_language("fr-FR")`
    """

    if language is None:
        return False
    return language.strip().lower().replace("_", "-").startswith("fr")


def _build_tool_approval_request(
    *,
    binding: BoundRuntimeContext,
    tool_name: str,
    tool_args: dict[str, object],
) -> HumanInputRequest:
    """
    Build the human approval prompt for one pending tool execution.

    Why this exists:
    - the shared ReAct tool loop needs one structured human question when approval
      is enabled
    - keeping the prompt construction here isolates approval UX from runtime orchestration

    How to use:
    - call from the approval callback with the current tool name and args

    Example:
    - `_build_tool_approval_request(binding=binding, tool_name="update_ticket", tool_args={"ticket_id": "INC-42"})`
    """

    if _is_french_language(binding.runtime_context.language):
        return HumanInputRequest(
            stage="tool_approval",
            title="Confirmer l'exécution de l'outil",
            question=(
                f"L'agent souhaite exécuter `{tool_name}`. "
                "Cette action peut modifier un état ou déclencher une action externe. "
                "Veux-tu continuer ?"
            ),
            choices=(
                HumanChoiceOption(
                    id="proceed",
                    label="Continuer",
                    description="Exécuter cet outil maintenant.",
                    default=True,
                ),
                HumanChoiceOption(
                    id="cancel",
                    label="Annuler",
                    description="Ne pas exécuter cet outil et laisser l'agent se replanifier.",
                ),
            ),
            free_text=True,
            metadata={
                "tool_name": tool_name,
                "tool_args_preview": _truncate_for_human_review(tool_args),
            },
        )

    return HumanInputRequest(
        stage="tool_approval",
        title="Confirm tool execution",
        question=(
            f"The agent wants to execute `{tool_name}`. "
            "This may modify state or trigger an external action. "
            "Do you want to continue?"
        ),
        choices=(
            HumanChoiceOption(
                id="proceed",
                label="Proceed",
                description="Run this tool now.",
                default=True,
            ),
            HumanChoiceOption(
                id="cancel",
                label="Cancel",
                description="Do not run this tool; let the agent replan.",
            ),
        ),
        free_text=True,
        metadata={
            "tool_name": tool_name,
            "tool_args_preview": _truncate_for_human_review(tool_args),
        },
    )


def _is_cancelled_human_decision(decision: object) -> bool:
    """
    Tell whether one approval response means “cancel this tool call”.

    Why this exists:
    - interrupt payloads can come back as a dict or a plain string
    - the loop only needs one small normalized cancel check

    How to use:
    - pass the interrupt resume payload received from LangGraph

    Example:
    - `_is_cancelled_human_decision({"choice_id": "cancel"})`
    """

    if isinstance(decision, dict):
        raw_choice = decision.get("choice_id") or decision.get("answer")
        if isinstance(raw_choice, str):
            return raw_choice.strip().lower() == "cancel"
        return False
    if isinstance(decision, str):
        return decision.strip().lower() == "cancel"
    return False


def build_tool_loop_compiled_react_agent(
    *,
    model: BaseChatModel,
    tools: Sequence[BaseTool],
    system_prompt: str,
    binding: BoundRuntimeContext,
    approval_policy: ToolApprovalPolicy,
    checkpointer: Checkpointer,
    chat_model_factory: object | None,
    definition: ReActAgentDefinition,
    infer_operation_from_messages: Callable[[Sequence[object]], str],
    default_operation: str,
    available_tool_names: set[str] | frozenset[str],
    model_call_wrapper: Callable[
        [MessagesState, object, Callable[[], Awaitable[object]]],
        Awaitable[object],
    ]
    | None = None,
) -> object:
    """
    Build the shared ReAct tool loop used with or without HITL approval.

    Why this exists:
    - plain ReAct and HITL should share one execution model for message memory,
      tool execution, and filesystem continuation
    - approval should be one optional gate inside that loop, not a separate runtime

    How to use:
    - pass the already selected model, bound tools, and the runtime system prompt
    - include the current runtime tool names so filesystem follow-up context can be
      rebuilt and enforced per turn

    Example:
    - `build_tool_loop_compiled_react_agent(..., available_tool_names={"ls", "read_file"})`
    """
    bound_models_by_operation: dict[str, object] = {}

    def _system_builder(state: object) -> str:
        state_messages = state.get("messages", []) if isinstance(state, dict) else []
        if not isinstance(state_messages, list):
            state_messages = []
        return (
            f"{system_prompt}"
            f"{render_filesystem_browsing_context(state_messages, available_tool_names=available_tool_names)}"
        )

    def _model_for_state(state: object) -> object:
        if not isinstance(chat_model_factory, RoutedChatModelFactory):
            return model.bind_tools(tools)
        messages = state.get("messages", []) if isinstance(state, dict) else []
        operation = (
            infer_operation_from_messages(messages)
            if isinstance(messages, list)
            else default_operation
        )
        cached = bound_models_by_operation.get(operation)
        if cached is not None:
            return cached
        resolved_model, _ = chat_model_factory.build_for_chat(
            definition=definition,
            binding=binding,
            purpose="chat",
            operation=operation,
        )
        bound = resolved_model.bind_tools(tools)
        bound_models_by_operation[operation] = bound
        return bound

    def _requires_human_approval(tool_name: str) -> bool:
        return requires_tool_approval(
            tool_name,
            approval_enabled=approval_policy.enabled,
            exact_required_tools=set(approval_policy.always_require_tools),
        )

    def _rewrite_tool_call(
        tool_name: str,
        args: dict[str, Any],
        state: MessagesState,
    ) -> dict[str, Any]:
        """
        Rewrite one filesystem tool call against the current tool-backed browsing state.

        Why this exists:
        - the model should not have to remember relative filesystem continuation perfectly
        - one shared rewrite step keeps plain ReAct and HITL aligned

        How to use:
        - call from the shared tool loop before tool execution

        Example:
        - after listing `/corpus`, `ls(path=\"/\")` can become `ls(path=\"/corpus/CIR\")`
        """

        state_messages = state.get("messages", []) if isinstance(state, dict) else []
        messages = state_messages if isinstance(state_messages, list) else []
        return rewrite_filesystem_tool_arguments(
            tool_name,
            args,
            messages=messages,
            available_tool_names=available_tool_names,
        )

    async def _hitl_callback(
        tool_name: str, args: dict[str, object]
    ) -> dict[str, object]:
        request = _build_tool_approval_request(
            binding=binding,
            tool_name=tool_name,
            tool_args=args,
        )
        decision = interrupt(request.model_dump(mode="json"))
        if _is_cancelled_human_decision(decision):
            return {"cancel": True}
        return {}

    graph = build_tool_loop(
        model=model.bind_tools(tools),
        tools=list(tools),
        system_builder=_system_builder,
        model_resolver=_model_for_state,
        model_call_wrapper=model_call_wrapper,
        requires_hitl=_requires_human_approval,
        hitl_callback=_hitl_callback,
        rewrite_tool_call=_rewrite_tool_call,
        max_history_messages=_V2_MAX_HISTORY_MESSAGES,
    )
    return graph.compile(checkpointer=checkpointer)
