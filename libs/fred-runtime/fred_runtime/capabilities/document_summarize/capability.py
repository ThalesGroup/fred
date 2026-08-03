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
`DocumentSummarizeCapability` (RFC §3, §10) — on-demand document summarization.

Why this module exists:
- `summarize_document` used to be bundled inside `document_access`, but its
  invocation is decided purely by the LLM from the tool docstring — there is
  no query-shaped config condition (unlike `list_document_tree`'s
  `attachments_only`) that tells the runtime when the tool should even exist
  for an agent. This capability is its own admin-gated, per-agent opt-in (an
  agent selecting `document_access` does NOT get this tool for free) — the
  admission control that governs it today.
- commonly paired with `document_access` (its `list_document_tree` /
  `search_documents_using_vectorization` hits are the usual source of the
  `document_uid` this tool's caller needs), but there is no runtime coupling:
  the uid can equally come from the conversation's attached-files list.

Deliberately NOT declaring `hitl_specs()` (RFC §5.4) yet, even though a
per-call HITL gate was the original design (admission + approval, defense in
depth): ReAct V2's HITL resume is currently broken end to end for EVERY
gated tool, not specific to this one (#2179 — `_validate_session_checkpoint_access`
only understands the legacy Graph runtime's hand-rolled checkpoint
convention; ReAct V2's native LangGraph checkpoint never matches it).
Shipping with `require=True` today would mean every approval attempt dead-
ends in a 409 — strictly worse than no gate at all. Re-add
`hitl_specs() -> [HitlSpec(tool="summarize_document", require=True)]` once
#2179 is fixed; admission control (`ADMIN_GATED` below) is the sole
governance layer until then.

Doctrine (RFC §3.5, §3.8, §10) — same as `document_access`:
- the capability reaches the platform ONLY through the typed
  `RuntimeServices.document_summarize` port; the per-turn binding and the raw
  access token NEVER enter `CapabilityContext`
- the tool signature exposes ONLY LLM arguments; scope and identity reach the
  tool through the middleware closure, never the tool schema

Identifier hygiene (hard rule, shared with `document_access`): the
`document_uid` argument is an internal working identifier for the agent's own
tool calls. The docstring instructs the model to NEVER repeat it to the end
user — answers refer to documents by display name only.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    HitlSpec,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import DocumentSummaryResult
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

_KF_SERVICE = "Knowledge Flow"

# Built-in default summary length when neither the caller (the LLM) nor the
# capability config specifies one.
DEFAULT_SUMMARIZE_MAX_CHARS = 5000
# Wire bounds of the Knowledge Flow endpoint's `max_chars` validation — clamp
# client-side so an out-of-range LLM value degrades gracefully instead of 422ing.
_SUMMARIZE_MAX_CHARS_BOUNDS = (200, 20_000)


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(value, high))


def resolve_summarize_max_chars(cap: int | None, requested: int | None) -> int:
    """
    Resolve the effective summary length from the configured cap and the
    caller's request.

    The per-agent cap (`summarize_max_chars` config) is both the default (when
    the caller asks for nothing) and a hard upper bound on whatever the caller
    requests; without one, the built-in default applies and the caller's
    request is honored verbatim (within wire bounds).
    """

    default = cap if cap is not None else DEFAULT_SUMMARIZE_MAX_CHARS
    effective = requested if requested is not None else default
    if cap is not None:
        effective = min(effective, cap)
    return _clamp(effective, _SUMMARIZE_MAX_CHARS_BOUNDS)


def _document_tool_failure(
    *,
    tool_ref: str,
    action: str,
    exc: Exception,
    elapsed_s: float,
    document_uid: str | None = None,
) -> tuple[str, ToolInvocationResult]:
    """Turn any document tool-call failure into a non-empty, actionable error
    message plus an ``is_error=True`` artifact.

    The v2 ReAct runtime surfaces ``ToolInvocationResult.is_error`` directly to
    the user (and suppresses LLM hallucination), so a failing tool MUST return
    such a result instead of raising — a raised exception is re-raised by the
    default ``ToolNode`` handler, which leaves the tool call pending in the
    trace and yields an empty error detail to the UI.

    Transport detail (timeout, HTTP status) arrives via the SDK-typed
    `DocumentPortCallError` attributes the adapters stamp — this module never
    imports the adapter's HTTP stack.
    """

    err_type = type(exc).__name__
    raw = str(exc).strip()
    timed_out = bool(getattr(exc, "timed_out", False))
    status_code = getattr(exc, "status_code", None)

    if timed_out:
        cause = f"the {_KF_SERVICE} service timed out after {elapsed_s:.0f}s"
    elif status_code is not None:
        cause = f"the {_KF_SERVICE} service returned HTTP {status_code}"
    else:
        cause = f"the {_KF_SERVICE} service call failed after {elapsed_s:.0f}s"

    target = f" (document_uid={document_uid})" if document_uid else ""
    detail = f": {raw}" if raw else ""
    message = f"Could not {action}{target}: {cause} [{err_type}{detail}]."
    return message, ToolInvocationResult(
        tool_ref=tool_ref,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


class DocumentSummarizeConfig(BaseModel):
    """
    Agent-creation / stored config of the document-summarize capability
    (RFC §3.2). The single field mirrors what `document_access` used to carry
    for this tool.
    """

    # Per-agent default AND hard cap for summarize_document's summary length
    # (chars). None = built-in default, caller's request honored verbatim.
    summarize_max_chars: int | None = Field(default=None, ge=200, le=20_000)


class DocumentSummarizeCapability(
    AgentCapability[DocumentSummarizeConfig, DocumentSummarizeConfig, EmptyModel]
):
    """
    On-demand document summarization, wired through the `document_summarize`
    port. Single tool, no chat controls, no turn options — see the module
    docstring for the admission/execution split with `document_access`.
    """

    manifest = CapabilityManifest(
        id="document_summarize",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped —
        # config-surface changes land without bumps.
        version="0.1.0",
        name="capability.document_summarize.name",
        description="capability.document_summarize.description",
        icon="summarize",
        config_fields=[
            FieldSpec(
                key="summarize_max_chars",
                type="integer",
                title="capability.document_summarize.fields.summarize_max_chars.title",
                description="capability.document_summarize.fields.summarize_max_chars.description",
                min=200,
                max=20_000,
                ui=UIHints(group="retrieval", advanced=True),
            ),
        ],
        # No new chat part / side panel / router / owned table.
        # team_scope intentionally left at the class default (ADMIN_GATED,
        # RFC §7, §8.3): unlike document_access's baseline search/tree, this
        # tool has no config-shaped trigger a user can reason about — a team
        # admin must explicitly enable it before any agent in that team can
        # even select it.
    )
    ConfigModel = DocumentSummarizeConfig

    def tools(
        self,
        ctx: CapabilityContext[DocumentSummarizeConfig, EmptyModel],
    ) -> Sequence[BaseTool]:
        """
        Build the single summarize tool, bound to the turn's typed context
        (RFC §3.2, §5). `AgentCapability.middleware()`'s default wraps this
        for `create_agent()`; no ReAct-loop-specific hook is needed.

        Return-convention note (Phase 1, NOTES-GRAPH-CAPABILITY-BRIDGE.md):
        kept as `@tool(..., response_format="content_and_artifact")` returning
        a `(content, ToolInvocationResult)` tuple — see `document_access`'s
        `tools()` docstring for the full rationale; identical constraint here.
        """

        config = ctx.config
        services = ctx.services
        summarize_cap = config.summarize_max_chars

        @tool("summarize_document", response_format="content_and_artifact")
        async def summarize_document(
            document_uid: str,
            instruction: str | None = None,
            max_chars: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Generate a fresh, on-demand summary of one document by its uid.

            Use this when you need to understand a document's content in depth —
            e.g. to decide whether it's relevant, or to extract specific
            information — without pulling its full text into your own context. A
            fresh model reads the whole document (using map-reduce for large
            documents) and returns just the summary.

            `document_uid` MUST be the document's opaque uid, not its name or
            title. Get it from a prior search_documents_using_vectorization
            hit's 'uid' field, from list_document_tree (the value shown in
            '[...]' after each document name), or from the conversation's
            attached-files list (the bracketed value after the file name). If
            you only know a document's name, resolve its uid with one of those
            first — never pass the name here. The uid is an internal working
            identifier for YOUR tool calls only: NEVER repeat it in your answer
            to the user — always refer to the document by its display name.

            Pass `instruction` to steer the summary: focus area, what to look
            for, audience, tone, desired length — e.g. "focus on financial risks
            and list every action item". Without it, you get a generic abstract.

            `max_chars` bounds the returned summary length; raise it for a more
            detailed summary, lower it for a terse one. Leave it unset to use
            the agent's configured default. The agent may also impose a hard
            maximum, in which case a larger request is clamped down to it.
            """

            port = services.document_summarize
            if port is None:
                raise RuntimeError(
                    "document_summarize: RuntimeServices.document_summarize is "
                    "not available on this execution path."
                )

            effective_max_chars = resolve_summarize_max_chars(summarize_cap, max_chars)
            started = time.monotonic()
            try:
                result: DocumentSummaryResult = await port.summarize(
                    document_uid,
                    instruction=instruction,
                    max_chars=effective_max_chars,
                )
            except Exception as exc:
                message, artifact = _document_tool_failure(
                    tool_ref="summarize_document",
                    action="summarize the document",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                    document_uid=document_uid,
                )
                # 403/404 almost always means the model passed a file NAME (or
                # a stale/foreign uid) — the backend fails closed on unknown
                # resources. Tell the model how to recover instead of letting
                # it give up and echo the error.
                if getattr(exc, "status_code", None) in (403, 404):
                    message += (
                        " If you passed a file name, that is the likely cause: "
                        "document_uid must be the opaque uid. Find it in the "
                        "conversation's attached-files list (the bracketed "
                        "value after the file name), in a search hit's 'uid' "
                        "field, or via list_document_tree — then call "
                        "summarize_document again with that uid. Do not "
                        "repeat the uid to the user."
                    )
                    # CAPAB-02: `_document_tool_failure` already baked the
                    # (shorter) pre-hint message into `artifact.blocks`; the
                    # recovery hint appended above must reach `blocks` too, or
                    # a Graph agent — which keeps only the artifact half of
                    # this return — loses exactly the guidance a model needs
                    # to self-correct and retry.
                    artifact = artifact.model_copy(
                        update={
                            "blocks": (
                                ToolContentBlock(
                                    kind=ToolContentKind.TEXT, text=message
                                ),
                            )
                        }
                    )
                return message, artifact
            # `blocks` carries the same summary text as `content` (CAPAB-02):
            # a Graph agent's plain-dict invocation keeps only the artifact
            # half of a `content_and_artifact` return.
            artifact = ToolInvocationResult(
                tool_ref="summarize_document",
                blocks=(
                    ToolContentBlock(kind=ToolContentKind.TEXT, text=result.summary),
                ),
            )
            return result.summary, artifact

        return [summarize_document]

    def hitl_specs(self) -> Sequence[HitlSpec]:
        # TEMPORARY, for manual verification of the #2179 fix on this branch
        # only — revert before merge unless #2177 is deliberately picked up
        # in the same change. See the module docstring for the full context.
        return [HitlSpec(tool="summarize_document", require=True)]
