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

"""Graph steps for the self-test RAG agent — real retrieval, no LLM.

The runtime applies the per-turn library scope (``selected_document_libraries_ids``)
to the knowledge-search tool, so this agent simply asks the question and echoes
what came back. The answer is deterministic by construction: it is the retrieved
chunk text, which lets a caller assert a marker phrase is present (or absent).
"""

from __future__ import annotations

import asyncio

import httpx
from fred_core.store import VectorSearchHit
from fred_sdk import (
    TOOL_REF_KNOWLEDGE_SEARCH,
    GraphNodeContext,
    GraphNodeResult,
    StepResult,
    TuningValue,
    typed_node,
)
from fred_sdk import (
    finalize_step as _finalize_step,
)

from .graph_state import SelfTestState

_DEFAULT_TOP_K = 5
_DEFAULT_HOLD_SECONDS = 0
MAX_HOLD_SECONDS = 900
_HOLD_SLICE_SECONDS = 10

CREDENTIAL_EXPIRED = "credential expired during protected call"
PROTECTED_CALL_REFUSED = "protected call refused"
PROTECTED_CALL_FAILED = "protected call failed"

# Indirected so a test can substitute the wait instead of spending it.
_sleep = asyncio.sleep


def _top_k(context: GraphNodeContext) -> int:
    value: TuningValue | None = context.tuning_values.get("settings.top_k")
    return int(value) if isinstance(value, (int, float)) else _DEFAULT_TOP_K


def _hold_seconds(context: GraphNodeContext) -> int:
    value: TuningValue | None = context.tuning_values.get("settings.hold_seconds")
    seconds = int(value) if isinstance(value, (int, float)) else _DEFAULT_HOLD_SECONDS
    return max(0, min(seconds, MAX_HOLD_SECONDS))


def _delivery_footer(context: GraphNodeContext) -> str:
    """Echo the prompts this turn was given, so the harness can assert *delivery*.

    Two independent delivery paths converge here, both proven by echoing a marker
    (no LLM, so the check is deterministic — it asserts the text arrived, not that
    a model obeyed it):

    - ``prompts.system`` — the per-instance system prompt set by the admin at
      enrollment (tuning). Reaches the agent via ``context.tuning_values``.
    - ``context_prompt_text`` — a marketplace/library prompt selected *for the
      conversation*: created in the prompt library, attached to the session, then
      resolved control-plane-side at prepare-execution. Reaches the agent via
      ``binding.runtime_context.context_prompt_text``. This agent is its first
      consumer — nothing else reads the field yet.
    """
    system_value = context.tuning_values.get("prompts.system")
    system_prompt = system_value.strip() if isinstance(system_value, str) else ""

    binding = getattr(context, "binding", None)
    runtime_context = getattr(binding, "runtime_context", None)
    context_value = getattr(runtime_context, "context_prompt_text", None)
    context_prompt = context_value.strip() if isinstance(context_value, str) else ""

    return (
        "\n\n---\nSELF-TEST DELIVERY\n"
        f"system_prompt: {system_prompt or '(none)'}\n"
        f"context_prompt: {context_prompt or '(none)'}"
    )


def _collect_hits(result: object) -> list[VectorSearchHit]:
    """Pull hits from a tool result: the typed ``sources`` plus any json blocks."""
    hits: list[VectorSearchHit] = list(getattr(result, "sources", ()) or ())
    for block in getattr(result, "blocks", ()) or ():
        if getattr(block.kind, "value", block.kind) != "json":
            continue
        raw_hits = block.data.get("hits") if isinstance(block.data, dict) else None
        for raw in raw_hits or []:
            if isinstance(raw, dict):
                try:
                    hits.append(VectorSearchHit.model_validate(raw))
                except (TypeError, ValueError):
                    continue
    return hits


@typed_node(SelfTestState)
async def baseline_step(state: SelfTestState, context: GraphNodeContext) -> StepResult:
    """Prove the credential is accepted before any waiting.

    Its own node on purpose: a node's statuses are flushed when it ends, so this
    one reaches the stream before the hold begins rather than after it.
    """
    if context.tuning_values.get("settings.check_access") is True:
        await _check_access(context)
        context.emit_status("credential_baseline")
    return StepResult()


@typed_node(SelfTestState)
async def hold_step(state: SelfTestState, context: GraphNodeContext) -> StepResult:
    """Wait before retrieving, so a turn can be made to outlive its bearer."""
    total = _hold_seconds(context)
    if total == 0:
        return StepResult()

    # Heartbeats are thoughts because only those reach the stream while the node
    # is still running; the one status is buffered with the node's events, so it
    # is flushed last and marks the moment retrieval begins.
    elapsed = 0
    while elapsed < total:
        await _sleep(min(_HOLD_SLICE_SECONDS, total - elapsed))
        elapsed = min(elapsed + _HOLD_SLICE_SECONDS, total)
        context.emit_thought(
            "tool_use", f"holding {elapsed}/{total} s before retrieval"
        )
    context.emit_status("hold", f"{total}/{total} s before retrieval")
    return StepResult()


def _protected_call_error(error: httpx.HTTPError) -> RuntimeError:
    """Classify a call made as the person.

    The harness reads the verdict off this message, so it stays fixed and never
    carries upstream response text.
    """
    if isinstance(error, httpx.HTTPStatusError):
        challenge = error.response.headers.get("WWW-Authenticate", "").lower()
        if error.response.status_code == 401 and "token expired" in challenge:
            return RuntimeError(CREDENTIAL_EXPIRED)
        return RuntimeError(PROTECTED_CALL_REFUSED)
    return RuntimeError(PROTECTED_CALL_FAILED)


async def _check_access(context: GraphNodeContext) -> None:
    folders = context.services.document_folders
    if folders is None:
        raise RuntimeError("authenticated metadata check unavailable")
    try:
        # Resolution always lists authenticated metadata; no matching folder is required.
        await folders.resolve_folder("credential-check")
    except httpx.HTTPError as error:
        raise _protected_call_error(error) from None


@typed_node(SelfTestState)
async def retrieve_step(state: SelfTestState, context: GraphNodeContext) -> StepResult:
    """Retrieve from the selected libraries and echo the chunks verbatim."""
    if context.tuning_values.get("settings.check_access") is True:
        runtime_context = context.binding.runtime_context
        original = getattr(runtime_context, "access_token", None)
        await _check_access(context)
        current = getattr(runtime_context, "access_token", None)
        if original and current and original != current:
            context.emit_status("credential_renewed")
        context.emit_status("protected_call_succeeded")
        return StepResult(
            state_update={
                "final_text": "Authenticated metadata check completed.",
                "sources_data": [],
                "hit_count": 0,
                "done_reason": "self_test_access_ok",
            }
        )
    context.emit_status(
        "retrieve", f"Searching selected libraries for: {state.latest_user_text}"
    )

    runtime_context = context.binding.runtime_context
    original = getattr(runtime_context, "access_token", None)
    try:
        result = await context.invoke_tool(
            TOOL_REF_KNOWLEDGE_SEARCH,
            {"query": state.latest_user_text, "top_k": _top_k(context)},
        )
    except httpx.HTTPError as error:
        raise _protected_call_error(error) from None
    current = getattr(runtime_context, "access_token", None)
    if _hold_seconds(context) and original and current and original != current:
        # Only the observation crosses the stream; credential values stay local.
        context.emit_status("credential_renewed")
    hits = _collect_hits(result)
    footer = _delivery_footer(context)

    if not hits:
        return StepResult(
            state_update={
                "final_text": "SELF-TEST: no chunks retrieved from the selected scope."
                + footer,
                "hit_count": 0,
                "done_reason": "self_test_empty",
            }
        )

    body = "\n\n".join(
        f"[{i + 1}] {hit.title or hit.uid}\n{hit.content}" for i, hit in enumerate(hits)
    )
    return StepResult(
        state_update={
            "final_text": f"SELF-TEST retrieved {len(hits)} chunk(s):\n\n{body}"
            + footer,
            "sources_data": [hit.model_dump(mode="json") for hit in hits],
            "hit_count": len(hits),
            "done_reason": "self_test_ok",
        }
    )


@typed_node(SelfTestState)
async def finalize_step(
    state: SelfTestState, context: GraphNodeContext
) -> GraphNodeResult:
    """Terminal step — emit the echoed retrieval."""
    return _finalize_step(
        final_text=state.final_text,
        fallback_text="SELF-TEST: nothing to report.",
        done_reason=state.done_reason,
    )
