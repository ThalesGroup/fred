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
from collections.abc import Awaitable, Callable, Mapping, Sequence
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
    PendingToolCall,
)
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse, hook_config
from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from fred_runtime.support.filesystem_context import rewrite_filesystem_tool_arguments

from .shared import state_messages

logger = logging.getLogger(__name__)

# Tool result a gated call gets instead of an interrupt when no human can be
# reached (invocation depth ≥ 1). A sub-agent runs inside its parent's tool
# call, with no checkpointer to persist an interrupt and no UI channel to
# raise it on — asking would hang the parent, so the call is refused.
SUBAGENT_APPROVAL_UNAVAILABLE = (
    "Error: this tool requires human approval, which is unavailable in a "
    "sub-agent. Do not call it again — continue with the tools you have, or "
    "report in your answer what could not be done without it."
)


def _tool_schema_name(tool: object) -> str | None:
    """Name of one entry of `ModelRequest.tools`, which holds `BaseTool`
    objects and raw provider schemas (flat or OpenAI `function`-wrapped)."""

    if isinstance(tool, Mapping):
        name = tool.get("name")
        if isinstance(name, str):
            return name
        function = tool.get("function")
        if isinstance(function, Mapping):
            nested = function.get("name")
            return nested if isinstance(nested, str) else None
        return None
    name = getattr(tool, "name", None)
    return name if isinstance(name, str) else None


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


@dataclass(frozen=True)
class GatedToolCall:
    """One tool call the gate decided needs human approval, collected before
    the single combined interrupt is raised (#2177 batching, see
    `PendingToolCall`)."""

    tool_call_id: str | None
    tool_name: str
    tool_args: dict[str, object]
    # The capability `HitlSpec.question` override (#1973), if any. Used
    # verbatim only in the single-call case — see `build_tool_approval_request`.
    question: str | None


def _humanize_tool_name(name: str) -> str:
    """
    Display form of a raw tool name for a human-facing approval prompt:
    "Summarize Document", not the bare `summarize_document` identifier — a
    snake_case function name is an internal detail, not something to show the
    person deciding whether to approve it. Deliberately a plain title-case
    (no verb/provider-aware humanization like the frontend's
    `humanizeToolName()` in traceUtils.ts): that richer logic lives client-side
    for the trace UI, and duplicating it here for a one-line approval prompt
    would outweigh the benefit. Tool names are inherently English identifiers,
    so — matching the trace UI's own convention — this stays in English even
    inside the French copy below.
    """

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
    """
    Human-readable, deduplicated tool listing for a batched approval prompt:
    "Summarize Document (×3)", not "summarize_document, summarize_document,
    summarize_document" — repeating the same raw identifier N times says
    nothing the trace's own step count doesn't already say, and reads as
    noise on top of exposing an internal name.
    """

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
    # Per-call `HitlSpec.question` overrides are deliberately not merged here:
    # no in-tree capability sets one today (only `require=True`), and there is
    # no sound way to combine N arbitrary override sentences into one — the
    # override still applies verbatim whenever it is the ONLY gated call.
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
    """
    Build the human approval prompt gating one or more pending tool calls.

    Why this exists:
    - the HITL gate needs one structured human question when approval is
      enabled; this payload is a frozen wire contract with the frontend
      (`AwaitingHumanRuntimeEvent.request`) — do not change its shape
    - `calls` may hold more than one entry (#2177 batching): the model can
      emit several calls to the same gated tool in one turn (e.g. summarizing
      every document in a folder), and proceed/cancel already applies to the
      whole set atomically — `aafter_model` raises exactly one combined
      interrupt for all of them instead of one prompt per call

    How to use:
    - call from the approval gate with every `GatedToolCall` needing approval
      in this turn (never empty — the caller only invokes this when at least
      one call needs approval)
    - each call's own `tool_call_id`/`tool_name`/args preview rides in
      `HumanInputRequest.pending_calls` so the frontend trace can correlate
      each gated `ToolCallRuntimeEvent` with this same prompt — the model
      node commits and streams those events before this gate ever runs
      (separate graph step), so without this the UI cannot tell "awaiting
      your confirmation" apart from "already executing"
    """

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
        # Deliberately False (P1): a free-text answer here has nowhere to go
        # — this gate only distinguishes cancel vs not-cancel
        # (_is_cancelled_human_decision), and the legacy free-text/"notes"
        # injection into the graph was already dead code before ReAct V2
        # (see this function's docstring). Showing the box anyway silently
        # discarded whatever the human typed and treated it as an implicit
        # "proceed" — confusing, not a real second input path. Revisit once
        # there is an actual consumer for free-text tool-approval answers.
        free_text=False,
        pending_calls=pending_calls,
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
    - cancel jumps back to the model WITHOUT executing any tool of the batch;
      the dangling assistant tool-call message is then dropped from the model
      input by CheckpointHygieneMiddleware, so the model replans. The legacy
      graph *intended* this via a `skip_tools` state key, but LangGraph
      silently dropped that write (unknown channel on `MessagesState`), so
      cancelling never actually prevented execution — this middleware fixes
      that latent bug (#1972).
    - the legacy `notes` free-text injection was dead code in the ReAct wiring
      (the approval callback never returned notes) and is not carried over

    - a sub-agent (`invocation_depth` ≥ 1) can never wait for a human: it runs
      inside its parent's tool call, checkpointer-free, with no UI channel, so
      asking would hang the parent. Unconditionally gated tools are hidden from
      its model and anything that would still have interrupted is refused with
      an error tool result (SUBAGENT-CAPABILITY-RFC.md §5.6)

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
        invocation_depth: int = 0,
    ) -> None:
        super().__init__()
        self._binding = binding
        self._approval_policy = approval_policy
        self._available_tool_names = available_tool_names
        self._capability_hitl = dict(capability_hitl or {})
        self._invocation_depth = invocation_depth
        # Both sets are resolved once per compiled agent: `ToolApprovalPolicy`
        # is frozen and the bindings never change after assembly, while the
        # gate itself runs per model call and per tool call.
        self._operator_gated: frozenset[str] = (
            frozenset(approval_policy.always_require_tools)
            if approval_policy.enabled
            else frozenset()
        )
        self._hidden_tool_names = (
            self._unconditionally_gated_names() if invocation_depth > 0 else frozenset()
        )

    def _unconditionally_gated_names(self) -> frozenset[str]:
        """Tools whose approval does not depend on the call's arguments: a
        capability `HitlSpec` with `require`, or the operator's exact list. A
        `when` predicate is excluded — only the gate can answer it, per call."""

        return self._operator_gated | frozenset(
            name for name, bound in self._capability_hitl.items() if bound.spec.require
        )

    def _requires_human_approval(self, tool_name: str) -> bool:
        """
        Operator-policy approval decision for a tool NO capability declared
        (#1978, RFC §5.4). The legacy name-prefix heuristics were retired now
        that every gated tool either carries a capability `HitlSpec` or is
        listed by the operator: approval is required iff the operator toggle is
        enabled AND the tool is in the exact `always_require_tools` list.
        """

        return tool_name in self._operator_gated

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
        if not needs and tool_name in self._operator_gated:
            needs = True
        return needs, bound.spec.question

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """
        Hide the tools no one can approve from a sub-agent's model (RFC §5.6).

        Empty at depth 0, so the depth-0 request is handed on untouched. The
        `aafter_model` refusal below is the safety net for what stays visible
        (a `when` predicate can only be answered per call).
        """

        if self._hidden_tool_names:
            kept = [
                tool
                for tool in request.tools
                if _tool_schema_name(tool) not in self._hidden_tool_names
            ]
            if len(kept) != len(request.tools):
                request = request.override(tools=kept)
        return await handler(request)

    def _refuse_without_a_human(self, gated: Sequence[GatedToolCall]) -> dict[str, Any]:
        """
        Answer every gated call with an error result instead of interrupting.

        LangChain's model→tools edge only sends the calls that have no
        `ToolMessage` yet, so answering here both refuses these calls and lets
        the ungated ones in the same batch run; when the whole batch is
        refused it routes straight back to the model.
        """

        logger.info(
            "[HITL] invocation_depth=%d: refusing %d approval-gated call(s) "
            "(%s) — no human can be reached from a sub-agent.",
            self._invocation_depth,
            len(gated),
            ", ".join(sorted({call.tool_name for call in gated})),
        )
        if not all(call.tool_call_id for call in gated):
            # An id-less call cannot be answered, and an unanswered call still
            # executes: skip the whole batch instead (the cancel path).
            return {"jump_to": "model"}
        return {
            "messages": [
                ToolMessage(
                    content=SUBAGENT_APPROVAL_UNAVAILABLE,
                    tool_call_id=call.tool_call_id or "",
                    name=call.tool_name,
                    status="error",
                )
                for call in gated
            ]
        }

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
            needs_approval, question = self._gate_decision(name, tc)
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
        if self._invocation_depth > 0:
            return self._refuse_without_a_human(gated)
        request = build_tool_approval_request(binding=self._binding, calls=gated)
        decision = interrupt(request.model_dump(mode="json"))
        if _is_cancelled_human_decision(decision):
            # Skip the whole tool batch (gated and ungated calls alike) and
            # let the model replan.
            return {"jump_to": "model"}
        return None
