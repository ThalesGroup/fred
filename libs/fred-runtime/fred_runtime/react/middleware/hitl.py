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

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fred_sdk.contracts.capability import (
    CapabilityContext,
    HitlGateRequest,
    HitlSpec,
)
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
)
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import hook_config
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from fred_runtime.support.filesystem_context import rewrite_filesystem_tool_arguments

from .shared import state_messages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapabilityHitlBinding:
    """
    One capability tool's approval declaration, bound for the gate (#1973,
    RFC §5.4).

    Why this exists:
    - exactly ONE HITL middleware exists per agent; capability `HitlSpec`s
      merge into that gate instead of shipping interrupt middleware of their
      own — assembly (`fred_runtime.capabilities.assembly`) builds one
      binding per declared tool so `when` predicates see the capability's
      typed `CapabilityContext` and the real tool object
    """

    spec: HitlSpec
    context: CapabilityContext[Any, Any]
    tool: Any | None = None


def _truncate_for_human_review(value: object, *, max_chars: int = 1200) -> str:
    """
    Render one tool-argument preview for approval UIs.

    Why this exists:
    - approval requests should show the human a bounded preview of the pending
      tool call
    - one helper keeps the preview formatting stable across all approval prompts
    """

    try:
        rendered = json.dumps(value, ensure_ascii=False)
    except Exception:
        rendered = str(value)
    if len(rendered) <= max_chars:
        return rendered
    return rendered[: max_chars - 3] + "..."


def _is_french_language(language: str | None) -> bool:
    """Tell whether the runtime language should use the French approval copy."""

    if language is None:
        return False
    return language.strip().lower().replace("_", "-").startswith("fr")


def build_tool_approval_request(
    *,
    binding: BoundRuntimeContext,
    tool_name: str,
    tool_args: dict[str, object],
    question: str | None = None,
) -> HumanInputRequest:
    """
    Build the human approval prompt for one pending tool execution.

    Why this exists:
    - the HITL gate needs one structured human question when approval is
      enabled; this payload is a frozen wire contract with the frontend
      (`AwaitingHumanRuntimeEvent.request`) — do not change its shape

    How to use:
    - call from the approval gate with the current tool name and args
    - `question` is the capability `HitlSpec.question` override (#1973):
      used verbatim in place of the default copy (the capability owns its
      i18n); title, choices, and wire shape stay unchanged
    """

    if _is_french_language(binding.runtime_context.language):
        return HumanInputRequest(
            stage="tool_approval",
            title="Confirmer l'exécution de l'outil",
            question=question
            or (
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
        question=question
        or (
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
    Tell whether one approval response means "cancel this tool call".

    Why this exists:
    - interrupt resume payloads can come back as a dict or a plain string
    - the gate only needs one small normalized cancel check
    """

    if isinstance(decision, dict):
        raw_choice = decision.get("choice_id") or decision.get("answer")
        if isinstance(raw_choice, str):
            return raw_choice.strip().lower() == "cancel"
        return False
    if isinstance(decision, str):
        return decision.strip().lower() == "cancel"
    return False


class FredHitlMiddleware(AgentMiddleware):
    """
    Filesystem argument rewrite + the human tool-approval gate (legacy
    `gate_tools`, RFC §5.4).

    Why this exists:
    - risky tool calls must pause for human approval with Fred's localized
      `HumanInputRequest` payload, one `interrupt()` per gated call,
      sequentially — the wire format and resume flow are frozen contracts
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
    - cancel jumps back to the model WITHOUT executing any tool of the batch;
      the dangling assistant tool-call message is then dropped from the model
      input by CheckpointHygieneMiddleware, so the model replans. The legacy
      graph *intended* this via a `skip_tools` state key, but LangGraph
      silently dropped that write (unknown channel on `MessagesState`), so
      cancelling never actually prevented execution — this middleware fixes
      that latent bug (#1972).
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
        available_tool_names: set[str] | frozenset[str],
        capability_hitl: Mapping[str, CapabilityHitlBinding] | None = None,
    ) -> None:
        super().__init__()
        self._binding = binding
        self._approval_policy = approval_policy
        self._available_tool_names = available_tool_names
        self._capability_hitl = dict(capability_hitl or {})

    def _requires_human_approval(self, tool_name: str) -> bool:
        """
        Operator-policy approval decision for a tool NO capability declared
        (#1978, RFC §5.4). The legacy name-prefix heuristics were retired now
        that every gated tool either carries a capability `HitlSpec` or is
        listed by the operator: approval is required iff the operator toggle is
        enabled AND the tool is in the exact `always_require_tools` list.
        """

        return self._approval_policy.enabled and tool_name in set(
            self._approval_policy.always_require_tools
        )

    def _gate_decision(
        self, tool_name: str, tool_call: Mapping[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Merge the two approval sources into one decision (RFC §5.4): capability
        `HitlSpec`s and operator policy. The legacy name-prefix heuristics were
        retired at Tier 1 (#1978) — a tool no capability declared is gated only
        by the operator `always_require_tools` list.

        Returns `(requires_approval, question_override)`.

        Semantics for capability-declared tools (#1973):
        - a raising `when` predicate counts as "interrupt" (fail-closed)
        - the spec applies regardless of `approval_policy.enabled` — the
          operator toggle controls PLATFORM gating; it does not silence a
          capability author's own safety declaration
        - the operator `always_require_tools` exact list (admin override)
          still forces approval when the policy is enabled
        """

        bound = self._capability_hitl.get(tool_name)
        if bound is None:
            return self._requires_human_approval(tool_name), None

        needs = bound.spec.require
        if not needs and bound.spec.when is not None:
            request = HitlGateRequest(
                tool_call=tool_call, tool=bound.tool, context=bound.context
            )
            try:
                needs = bool(bound.spec.when(request))
            except Exception:
                logger.exception(
                    "[HITL] capability 'when' predicate for tool '%s' raised; "
                    "failing closed (interrupt).",
                    tool_name,
                )
                needs = True
        if (
            not needs
            and self._approval_policy.enabled
            and tool_name in set(self._approval_policy.always_require_tools)
        ):
            needs = True
        return needs, bound.spec.question

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        messages = state_messages(state)
        last = messages[-1] if messages else None
        tool_calls = getattr(last, "tool_calls", None) or []
        if not tool_calls:
            return None
        for tc in tool_calls:
            name = tc.get("name") if isinstance(tc, dict) else None
            raw_args = tc.get("args") if isinstance(tc, dict) else {}
            args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            if name:
                rewritten = rewrite_filesystem_tool_arguments(
                    name,
                    dict(args),
                    messages=messages,
                    available_tool_names=self._available_tool_names,
                )
                if rewritten != args:
                    args = rewritten
                    tc["args"] = args
            if not name:
                continue
            needs_approval, question = self._gate_decision(name, tc)
            if needs_approval:
                request = build_tool_approval_request(
                    binding=self._binding,
                    tool_name=name,
                    tool_args=args,
                    question=question,
                )
                decision = interrupt(request.model_dump(mode="json"))
                if _is_cancelled_human_decision(decision):
                    # Skip the whole tool batch and let the model replan.
                    return {"jump_to": "model"}
        return None
