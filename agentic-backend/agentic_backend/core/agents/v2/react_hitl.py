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
HITL/approval-specific ReAct graph construction.

Why this module exists:
- keep `react_runtime.py` focused on baseline ReAct execution
- isolate the custom approval loop wiring in one place
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.types import Checkpointer, interrupt

from agentic_backend.core.tools.tool_loop import build_tool_loop

from .context import BoundRuntimeContext
from .model_routing import RoutedChatModelFactory
from .models import ReActAgentDefinition, ToolApprovalPolicy
from .runtime import HumanChoiceOption, HumanInputRequest
from .tool_approval import requires_tool_approval


def _truncate_for_human_review(value: object, *, max_chars: int = 1200) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except Exception:
        rendered = str(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."


def _is_french_language(language: str | None) -> bool:
    if language is None:
        return False
    return language.strip().lower().replace("_", "-").startswith("fr")


def _build_tool_approval_request(
    *,
    binding: BoundRuntimeContext,
    tool_name: str,
    tool_args: dict[str, object],
) -> HumanInputRequest:
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
    if isinstance(decision, dict):
        raw_choice = decision.get("choice_id") or decision.get("answer")
        if isinstance(raw_choice, str):
            return raw_choice.strip().lower() == "cancel"
        return False
    if isinstance(decision, str):
        return decision.strip().lower() == "cancel"
    return False


def build_hitl_compiled_react_agent(
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
) -> object:
    """
    Build the custom ReAct graph used when tool approval is enabled.

    The graph is intentionally separate from LangChain `create_agent()` path:
    it inserts an explicit approval gate before sensitive tool executions.
    """
    bound_models_by_operation: dict[str, object] = {}

    def _system_builder(_: object) -> str:
        return system_prompt

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
            approval_enabled=True,
            exact_required_tools=set(approval_policy.always_require_tools),
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
        requires_hitl=_requires_human_approval,
        hitl_callback=_hitl_callback,
    )
    return graph.compile(checkpointer=checkpointer)
