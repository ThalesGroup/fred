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

"""Shared capability approval decisions and localized human requests."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from fred_sdk.contracts.capability import CapabilityContext, HitlGateRequest, HitlSpec
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ToolApprovalPolicy
from fred_sdk.contracts.runtime import (
    HumanChoiceOption,
    HumanInputRequest,
    PendingToolCall,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CapabilityHitlBinding:
    spec: HitlSpec
    context: CapabilityContext[Any, Any]
    tool: Any | None = None


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


@dataclass(frozen=True)
class GatedToolCall:
    tool_call_id: str | None
    tool_name: str
    tool_args: dict[str, object]
    question: str | None


def _humanize_tool_name(name: str) -> str:

    return name.replace("_", " ").strip().title()


def _single_call_question(call: GatedToolCall, *, is_fr: bool) -> str:
    if call.question:
        return call.question
    display_name = _humanize_tool_name(call.tool_name)
    if is_fr:
        return (
            f"L'agent souhaite exécuter « {display_name} ». "
            "Cette action peut modifier un état, déclencher une action externe "
            "ou consommer beaucoup de tokens. "
            "Voulez-vous continuer ?"
        )
    return (
        f"The agent wants to execute {display_name}. "
        "This may modify state, trigger an external action, or consume a "
        "large number of tokens. "
        "Do you want to continue?"
    )


def _describe_batch(calls: Sequence[GatedToolCall]) -> str:

    order: list[str] = []
    counts: dict[str, int] = {}
    for c in calls:
        if c.tool_name not in counts:
            order.append(c.tool_name)
        counts[c.tool_name] = counts.get(c.tool_name, 0) + 1
    return ", ".join(
        _humanize_tool_name(name) + (f" (×{counts[name]})" if counts[name] > 1 else "")
        for name in order
    )


def _batch_question(calls: Sequence[GatedToolCall], *, is_fr: bool) -> str:
    names = _describe_batch(calls)
    if is_fr:
        return (
            f"L'agent souhaite exécuter {len(calls)} actions : {names}. "
            "Ces actions peuvent modifier un état, déclencher des actions externes "
            "ou consommer beaucoup de tokens. "
            "Voulez-vous continuer ?"
        )
    return (
        f"The agent wants to execute {len(calls)} actions: {names}. "
        "These may modify state, trigger external actions, or consume a "
        "large number of tokens. "
        "Do you want to continue?"
    )


def build_tool_approval_request(
    *,
    binding: BoundRuntimeContext,
    calls: Sequence[GatedToolCall],
) -> HumanInputRequest:

    if not calls:
        raise ValueError(
            "build_tool_approval_request() requires at least one GatedToolCall; "
            "the caller must only invoke this when the gate has decided at "
            "least one call needs approval."
        )

    is_fr = _is_french_language(binding.runtime_context.language)
    pending_calls = tuple(
        PendingToolCall(
            tool_call_id=call.tool_call_id or "",
            tool_name=call.tool_name,
            args_preview=_truncate_for_human_review(call.tool_args),
        )
        for call in calls
    )
    question = (
        _single_call_question(calls[0], is_fr=is_fr)
        if len(calls) == 1
        else _batch_question(calls, is_fr=is_fr)
    )

    if is_fr:
        title = (
            "Confirmer l'exécution de l'outil"
            if len(calls) == 1
            else f"Confirmer l'exécution de {len(calls)} outils"
        )
        choices = (
            HumanChoiceOption(
                id="proceed",
                label="Accepter",
                description="Exécuter cet outil maintenant."
                if len(calls) == 1
                else "Exécuter ces outils maintenant.",
                default=True,
            ),
            HumanChoiceOption(
                id="cancel",
                label="Refuser",
                description="Ne pas exécuter cet outil et laisser l'agent se replanifier."
                if len(calls) == 1
                else "Ne pas exécuter ces outils et laisser l'agent se replanifier.",
            ),
        )
    else:
        title = (
            "Confirm tool execution"
            if len(calls) == 1
            else f"Confirm {len(calls)} tool executions"
        )
        choices = (
            HumanChoiceOption(
                id="proceed",
                label="Accept",
                description="Run this tool now."
                if len(calls) == 1
                else "Run these tools now.",
                default=True,
            ),
            HumanChoiceOption(
                id="cancel",
                label="Reject",
                description="Do not run this tool; let the agent replan."
                if len(calls) == 1
                else "Do not run these tools; let the agent replan.",
            ),
        )

    return HumanInputRequest(
        stage="tool_approval",
        title=title,
        question=question,
        choices=choices,
        free_text=False,
        pending_calls=pending_calls,
    )


def is_tool_approval_granted(decision: object) -> bool:
    """Only an explicit proceed answer authorizes the pending operation."""
    if isinstance(decision, dict):
        decision = decision.get("choice_id") or decision.get("answer")
    return isinstance(decision, str) and decision.strip().lower() == "proceed"


class ToolApproval:
    """Capability declarations apply even when operator approval is disabled."""

    def __init__(
        self,
        *,
        approval_policy: ToolApprovalPolicy,
        capability_hitl: Mapping[str, CapabilityHitlBinding] | None = None,
    ) -> None:
        self._approval_policy = approval_policy
        self.capability_hitl = dict(capability_hitl or {})

    def requires_human_approval(self, tool_name: str) -> bool:
        return self._approval_policy.enabled and tool_name in set(
            self._approval_policy.always_require_tools
        )

    def decision(
        self, tool_name: str, tool_call: Mapping[str, Any]
    ) -> tuple[bool, str | None]:
        bound = self.capability_hitl.get(tool_name)
        if bound is None:
            return self.requires_human_approval(tool_name), None

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
