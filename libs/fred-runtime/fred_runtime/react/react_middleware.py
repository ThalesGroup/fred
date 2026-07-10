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
Platform middleware frame for the ReAct `create_agent` execution loop (#1972).

Why this module exists:
- the hand-rolled 4-node ReAct StateGraph (`reasoner`/`tools`/`gate_tools`/
  `tool_exec`) is replaced by stock LangChain `create_agent`; the custom node
  logic is re-homed here as five platform middleware (RFC
  docs/swift/rfc/AGENT-CAPABILITY-RFC.md §5.2–§5.4)
- the platform owns a FIXED composition frame; capability middleware (#1973)
  is inserted as a block at one reserved slot inside that frame, so capability
  authors never position themselves relative to core middleware

The frame, in `create_agent` middleware list order:

    1. CheckpointHygieneMiddleware   — request-scoped message hygiene (outermost
       `wrap_model_call`): dangling-tool-call sanitize + history trim +
       reasoning-strip, applied to the MODEL INPUT ONLY — never persisted to the
       checkpoint — plus legacy tool-output metadata attach on the response.
    2. ModelRoutingMiddleware        — per-operation model selection. Sits
       inside hygiene and outside tracing so spans/KPI record the ROUTED model.
    3. DynamicPromptMiddleware       — per-turn system-prompt suffix
       (filesystem browsing continuation context).
    4. >>> CAPABILITY BLOCK INSERTION SLOT (#1973) <<<
       Capability middleware stacks are inserted here, sorted by capability id
       (RFC §5.3). Their `wrap_model_call` nests inside the platform prompt and
       outside tracing, so observability always records the final request.
    5. TracingKpiMiddleware          — innermost `wrap_model_call`: the
       `v2.react.model` span, `llm.call_latency_ms` KPI timer, and the
       `[LLM][CALL]`/`[LLM][RESPONSE]` logs measure/describe the bare model
       call, exactly as the legacy `reasoner` node did.
    6. FredHitlMiddleware            — `after_model`: filesystem tool-argument
       rewrite + the human tool-approval gate (RFC §5.4). Sequential per-call
       `interrupt()`s with the legacy `HumanInputRequest` payload; cancel jumps
       back to the model without executing tools.
    7. ToolCallLimitMiddleware       — LangChain prebuilt, appended only when
       `max_tool_calls_per_turn` is set. Listed AFTER FredHitl on purpose:
       `after_model` hooks run in REVERSE list order, so the limit blocks
       over-limit calls BEFORE a human is asked to approve them.

Hook-order cheat sheet (`create_agent` semantics):
- `wrap_model_call`: first in list = outermost.
- `before_model`: list order. `after_model`: reverse list order.

How to use:
- call `build_react_platform_middleware_frame(...)` from the ReAct executor
  builder; pass future capability middleware through `capability_middleware`.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from contextlib import nullcontext
from typing import Any, cast

from fred_core.kpi import BaseKPIWriter, KPIActor
from fred_sdk.contracts.context import BoundRuntimeContext
from fred_sdk.contracts.models import ReActAgentDefinition, ToolApprovalPolicy
from fred_sdk.contracts.runtime import (
    ChatModelFactoryPort,
    HumanChoiceOption,
    HumanInputRequest,
    TracerPort,
)
from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ToolCallLimitMiddleware,
)
from langchain.agents.middleware.types import (
    ModelRequest,
    ModelResponse,
    hook_config,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from fred_runtime.support.filesystem_context import (
    render_filesystem_browsing_context,
    rewrite_filesystem_tool_arguments,
)
from fred_runtime.support.thinking import strip_reasoning_from_history
from fred_runtime.support.tool_approval import requires_tool_approval
from fred_runtime.support.tool_loop import (
    collect_tool_outputs,
    sanitize_dangling_tool_calls,
    trim_to_human_boundary,
)

from .react_model_adapter import (
    TRACE_MODEL_SPAN_NAME,
    extract_model_name_from_model_response,
    extract_model_name_from_object,
)

logger = logging.getLogger(__name__)


def _state_messages(state_like: object) -> list[Any]:
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


# ---------------------------------------------------------------------------
# 1. CheckpointHygieneMiddleware
# ---------------------------------------------------------------------------


class CheckpointHygieneMiddleware(AgentMiddleware):
    """
    Request-scoped message hygiene for every model call (legacy `reasoner` prep).

    Why this exists:
    - poisoned checkpoints (dangling tool calls from crashed turns) make OpenAI
      reject the payload with HTTP 400; replayed reasoning blocks make Mistral
      reject with HTTP 422; unbounded history contaminates queries
    - the legacy loop applied sanitize → trim → reasoning-strip to the MODEL
      INPUT only, never to the persisted checkpoint — so this must be a
      `wrap_model_call` request override, NOT a `before_model` state update
      (state updates would rewrite the checkpoint and destroy history)

    How to use:
    - first middleware of the platform frame; nothing may see an unsanitized
      model request
    """

    def __init__(self, *, max_history_messages: int | None) -> None:
        super().__init__()
        self._max_history_messages = max_history_messages

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        messages = sanitize_dangling_tool_calls(list(request.messages))
        if self._max_history_messages is not None:
            trimmed = trim_to_human_boundary(messages, self._max_history_messages)
            logger.debug(
                "[TOOL LOOP] history trimmed: %d → %d messages (max_history_messages=%d)",
                len(messages),
                len(trimmed),
                self._max_history_messages,
            )
            messages = trimmed
        # Strip provider-native reasoning from replayed assistant messages
        # (RUNTIME-05 Layer 2c): reasoning-capable models (Mistral via the
        # OpenAI-compatible client, Claude extended thinking) leave reasoning
        # blocks in the checkpointed AIMessage. Replaying them makes Mistral
        # reject the request (HTTP 422) and pollutes context. The reasoning was
        # already surfaced to the UI as THOUGHT_* events.
        messages = strip_reasoning_from_history(messages)
        response = await handler(
            request.override(messages=cast("list[AnyMessage]", messages))
        )
        self._attach_tool_outputs(response, request)
        return response

    @staticmethod
    def _attach_tool_outputs(response: ModelResponse, request: ModelRequest) -> None:
        """
        Attach the latest tool outputs to the response metadata (legacy behavior).

        Why this exists:
        - the legacy `reasoner` node recorded the latest ToolMessage payload per
          tool name under `response_metadata["tools"]`; re-homed unchanged
        """

        ai_message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)),
            None,
        )
        if ai_message is None:
            return
        tool_payloads = collect_tool_outputs(_state_messages(request.state))
        md = getattr(ai_message, "response_metadata", {}) or {}
        tools_md = md.get("tools", {}) or {}
        tools_md.update(tool_payloads)
        md["tools"] = tools_md
        ai_message.response_metadata = md


# ---------------------------------------------------------------------------
# 2. ModelRoutingMiddleware
# ---------------------------------------------------------------------------


class ModelRoutingMiddleware(AgentMiddleware):
    """
    Per-operation model selection (legacy `_model_for_state`).

    Why this exists:
    - routed model factories may choose different model configs for `routing`
      (fresh user turn) vs `planning` (tool-driven follow-up) inside one turn
    - the operation is inferred from the RAW state history, and resolved models
      are cached per operation for the lifetime of the compiled agent — both
      exactly as the legacy closure did

    How to use:
    - placed before TracingKpiMiddleware so spans/KPI record the routed model
    """

    def __init__(
        self,
        *,
        chat_model_factory: ChatModelFactoryPort | None,
        definition: ReActAgentDefinition,
        binding: BoundRuntimeContext,
        infer_operation_from_messages: Callable[[Sequence[object]], str],
        default_operation: str,
    ) -> None:
        super().__init__()
        self._chat_model_factory = chat_model_factory
        self._definition = definition
        self._binding = binding
        self._infer_operation_from_messages = infer_operation_from_messages
        self._default_operation = default_operation
        self._models_by_operation: dict[str, BaseChatModel] = {}

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        resolved = self._resolve_model(request)
        if resolved is not None:
            request = request.override(model=resolved)
        return await handler(request)

    def _resolve_model(self, request: ModelRequest) -> BaseChatModel | None:
        messages = _state_messages(request.state)
        operation = (
            self._infer_operation_from_messages(messages)
            if messages
            else self._default_operation
        )
        cached = self._models_by_operation.get(operation)
        if cached is not None:
            return cached
        if self._chat_model_factory is None:
            return None
        resolved = self._chat_model_factory.build_for_operation(
            definition=self._definition,
            binding=self._binding,
            purpose="chat",
            operation=operation,
        )
        if resolved is None:
            return None
        model = cast(BaseChatModel, resolved)
        self._models_by_operation[operation] = model
        return model


# ---------------------------------------------------------------------------
# 3. DynamicPromptMiddleware
# ---------------------------------------------------------------------------


class DynamicPromptMiddleware(AgentMiddleware):
    """
    Per-turn dynamic system-prompt suffix (legacy `_system_builder`).

    Why this exists:
    - the model should not have to remember filesystem browsing continuation
      (current dir, prior `ls` results) across turns; the legacy loop rebuilt
      that suffix from the message state on every model call

    How to use:
    - the static composed system prompt is passed to `create_agent`; this
      middleware appends the per-turn suffix on top of it
    """

    def __init__(self, *, available_tool_names: set[str] | frozenset[str]) -> None:
        super().__init__()
        self._available_tool_names = available_tool_names

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        suffix = render_filesystem_browsing_context(
            _state_messages(request.state),
            available_tool_names=self._available_tool_names,
        )
        if suffix:
            base = request.system_prompt or ""
            request = request.override(
                system_message=SystemMessage(content=f"{base}{suffix}")
            )
        return await handler(request)


# ---------------------------------------------------------------------------
# 5. TracingKpiMiddleware
# ---------------------------------------------------------------------------


class TracingKpiMiddleware(AgentMiddleware):
    """
    Model-call span, latency KPI, and call/response logs (legacy `_wrap`).

    Why this exists:
    - Fred tracing tags each model call with a `v2.react.model` span (operation
      + model name) nested under the active agent span; KPI records
      `llm.call_latency_ms`; `[LLM][CALL]`/`[LLM][RESPONSE]` logs describe the
      exact request/response
    - this middleware is the INNERMOST `wrap_model_call` of the platform frame
      so span/KPI/log measure the bare model call, exactly as the legacy
      `reasoner` node wrapped only `model.ainvoke(...)`

    How to use:
    - always part of the frame; span/KPI are no-ops when tracer/kpi are None,
      the logs are emitted unconditionally (legacy behavior)
    """

    def __init__(
        self,
        *,
        tracer: TracerPort | None,
        kpi: BaseKPIWriter | None,
        binding: BoundRuntimeContext,
        infer_operation_from_messages: Callable[[Sequence[object]], str],
        default_operation: str,
    ) -> None:
        super().__init__()
        self._tracer = tracer
        self._kpi = kpi
        self._binding = binding
        self._infer_operation_from_messages = infer_operation_from_messages
        self._default_operation = default_operation

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        messages = _state_messages(request.state)
        operation = (
            self._infer_operation_from_messages(messages)
            if messages
            else self._default_operation
        )
        model_name = extract_model_name_from_object(request.model)
        self._log_model_call(request)

        span = None
        if self._tracer is not None:
            attributes: dict[str, object] = {"operation": operation}
            if model_name is not None:
                attributes["model_name"] = model_name
            from .react_tracing import active_agent_span

            span = self._tracer.start_span(
                name=TRACE_MODEL_SPAN_NAME,
                context=self._binding.portable_context,
                attributes=cast(dict[str, str | int | float | bool | None], attributes),
                parent=active_agent_span.get(),
            )

        kpi_dims: dict[str, str | None] = {
            "agent_id": self._binding.portable_context.agent_name
            or self._binding.portable_context.agent_id,
            "operation": operation,
        }
        if model_name is not None:
            kpi_dims["model_name"] = model_name

        kpi_ctx = (
            self._kpi.timer(
                "llm.call_latency_ms", dims=kpi_dims, actor=KPIActor(type="system")
            )
            if self._kpi is not None
            else None
        )
        # Use the timer as a sync context manager (allowed inside async
        # functions). _TimerImpl.__exit__ receives exc_type so
        # status=error/cancelled is set automatically on failure.
        with kpi_ctx if kpi_ctx is not None else nullcontext():
            try:
                response = await handler(request)
                if span is not None:
                    span.set_attribute("status", "ok")
                    response_model_name = extract_model_name_from_model_response(
                        response
                    )
                    if response_model_name is not None:
                        span.set_attribute("model_name", response_model_name)
                self._log_model_response(response)
                return response
            except Exception:
                if span is not None:
                    span.set_attribute("status", "error")
                raise
            finally:
                if span is not None:
                    span.end()

    @staticmethod
    def _log_model_call(request: ModelRequest) -> None:
        messages = list(request.messages)
        sys_text = request.system_prompt or ""
        tail = ", ".join(
            f"{type(m).__name__[0]}:{len(str(m.content))}c" for m in messages[-6:]
        )
        last_human = next(
            (
                (
                    m.content[:120]
                    if isinstance(m.content, str)
                    else str(m.content)[:120]
                )
                for m in reversed(messages)
                if isinstance(m, HumanMessage)
            ),
            "—",
        )
        logger.info(
            "[LLM][CALL] sys=%dc total_msgs=%d hist_tail=[%s] question=%r",
            len(sys_text),
            len(messages) + (1 if request.system_message is not None else 0),
            tail,
            last_human,
        )

    @staticmethod
    def _log_model_response(response: ModelResponse) -> None:
        ai_message = next(
            (m for m in reversed(response.result) if isinstance(m, AIMessage)),
            None,
        )
        if ai_message is None:
            return
        tool_calls = getattr(ai_message, "tool_calls", None) or []
        if tool_calls:
            logger.info(
                "[LLM][RESPONSE] tool_calls=%s",
                [
                    {
                        "name": tc.get("name")
                        if isinstance(tc, dict)
                        else getattr(tc, "name", "?"),
                        "args": {
                            k: (str(v)[:60] if isinstance(v, str) else v)
                            for k, v in (
                                (tc.get("args") or {}) if isinstance(tc, dict) else {}
                            ).items()
                        },
                    }
                    for tc in tool_calls
                ],
            )
        else:
            text = (
                ai_message.content
                if isinstance(ai_message.content, str)
                else str(ai_message.content)
            )
            logger.info(
                "[LLM][RESPONSE] final answer=%dc: %r",
                len(text),
                text[:150] + ("…" if len(text) > 150 else ""),
            )


# ---------------------------------------------------------------------------
# 6. FredHitlMiddleware
# ---------------------------------------------------------------------------


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
) -> HumanInputRequest:
    """
    Build the human approval prompt for one pending tool execution.

    Why this exists:
    - the HITL gate needs one structured human question when approval is
      enabled; this payload is a frozen wire contract with the frontend
      (`AwaitingHumanRuntimeEvent.request`) — do not change its shape

    How to use:
    - call from the approval gate with the current tool name and args
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
      declarations (#1973) will merge into this gate rather than adding more

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
    ) -> None:
        super().__init__()
        self._binding = binding
        self._approval_policy = approval_policy
        self._available_tool_names = available_tool_names

    def _requires_human_approval(self, tool_name: str) -> bool:
        """Merge the operator policy with the legacy name-prefix heuristics."""

        return requires_tool_approval(
            tool_name,
            approval_enabled=self._approval_policy.enabled,
            exact_required_tools=set(self._approval_policy.always_require_tools),
        )

    @hook_config(can_jump_to=["model"])
    async def aafter_model(
        self, state: AgentState[Any], runtime: Runtime[Any]
    ) -> dict[str, Any] | None:
        messages = _state_messages(state)
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
            if name and self._requires_human_approval(name):
                request = build_tool_approval_request(
                    binding=self._binding,
                    tool_name=name,
                    tool_args=args,
                )
                decision = interrupt(request.model_dump(mode="json"))
                if _is_cancelled_human_decision(decision):
                    # Skip the whole tool batch and let the model replan.
                    return {"jump_to": "model"}
        return None


# ---------------------------------------------------------------------------
# The fixed platform frame
# ---------------------------------------------------------------------------


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
) -> list[AgentMiddleware]:
    """
    Assemble the fixed platform middleware frame for one ReAct agent.

    Why this exists:
    - middleware list order is semantic in `create_agent`; the platform owns
      one fixed frame so capability authors can never get the ordering wrong
      (RFC §5.3) — see the module docstring for the full order rationale

    How to use:
    - `capability_middleware` is the RESERVED capability-block slot (#1973):
      pass the concatenated capability stacks already sorted by capability id;
      they are inserted between DynamicPromptMiddleware and
      TracingKpiMiddleware

    Example:
    - `build_react_platform_middleware_frame(..., capability_middleware=stacks)`
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
