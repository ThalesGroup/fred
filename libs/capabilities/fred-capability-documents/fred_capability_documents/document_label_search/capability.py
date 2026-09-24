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
`DocumentLabelSearchCapability` — exhaustive, paginated business-label
resolution.

Why this is its own capability, not a second tool on `document_access`:
- `document_access` is `DEFAULT_ON` — every agent that ships with it gets its
  tool set for free. Adding a label-search tool there would mean every such
  agent picks up a second, semantically-adjacent tool the moment it ships: a
  harder tool-selection call for the model than the pre-existing
  search-vs-tree split (both would answer "documents with label X",
  differing only on the where/all-of-them axis), with a fail-quiet failure
  mode (an incomplete-but-plausible-looking answer) instead of a fail-loud
  one. Splitting into its own admin-gated capability means NO existing
  agent's tool set changes; a team admin opts a specific agent into label
  search deliberately, one team at a time.
- `list_document_tree` (`document_access`) does NOT filter by label at all,
  by design (see its own docstring) — it renders a folder tree, and a size-
  budgeted tree is the wrong response shape for "give me every document
  labeled X". This capability's `list_documents_by_label` is the only
  label-search surface: exhaustive, deterministic, paginated.

Doctrine (RFC §3.5, §3.8, §10) — same as `document_access`/
`document_summarize`:
- reaches the platform ONLY through the typed `RuntimeServices.document_tree`
  port's `list_by_label` method (shared plumbing with `document_access`'s
  `tree()` — one port, two capabilities, not two ports); the per-turn
  binding and the raw access token NEVER enter `CapabilityContext`
- the tool signature exposes ONLY LLM arguments; scope and identity reach it
  through the middleware closure, never the tool schema

Identifier hygiene (hard rule, shared with `document_access`): `document_uid`
is an internal working identifier for the agent's own tool calls (e.g.
chaining into `document_summarize`). The docstring instructs the model to
NEVER repeat it to the end user — answers refer to documents by display name
only.

KNOWN GAP (documented on `DocumentTreePort.list_by_label` itself): unlike
`document_access`'s `tree()`, this tool does not respect a `library_tag_ids`
binding — Knowledge Flow's label resolution narrows only by document-level
READ permission, never by folder/library scope. An agent bound to a specific
library set still sees every readable document carrying a label, corpus-
wide. Not silently papered over; narrowing this is follow-up work.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import DocumentLabelPageResult
from langchain_core.tools import BaseTool, tool

_KF_SERVICE = "Knowledge Flow"

# Wire bounds of the Knowledge Flow endpoint's `limit` validation — clamp
# client-side so an out-of-range LLM value degrades gracefully instead of
# 422ing.
_LABEL_PAGE_LIMIT_BOUNDS = (1, 500)


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(value, high))


def _document_tool_failure(
    *,
    tool_ref: str,
    action: str,
    exc: Exception,
    elapsed_s: float,
) -> tuple[str, ToolInvocationResult]:
    """Turn any label-search failure into a non-empty, actionable error
    message plus an ``is_error=True`` artifact — same convention as
    `document_access`/`document_summarize`'s `_document_tool_failure`
    (duplicated, not imported: these capabilities are independently
    installable/removable and must not import each other's internals)."""

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

    detail = f": {raw}" if raw else ""
    message = f"Could not {action}: {cause} [{err_type}{detail}]."
    return message, ToolInvocationResult(
        tool_ref=tool_ref,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )


class DocumentLabelSearchCapability(
    AgentCapability[EmptyModel, EmptyModel, EmptyModel]
):
    """
    Exhaustive, paginated business-label resolution — a single tool, no
    config, no chat controls, no turn options. See the module docstring for
    why this is its own admin-gated capability rather than living inside
    `document_access`.
    """

    manifest = CapabilityManifest(
        id="document_label_search",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped —
        # config-surface changes land without bumps.
        version="0.1.0",
        name="capability.document_label_search.name",
        description="capability.document_label_search.description",
        icon="label",
        # No new chat part / side panel / router / owned table.
        # team_scope intentionally left at the class default (ADMIN_GATED,
        # RFC §7, §8.3), same reasoning as `document_summarize`: this tool
        # has no config-shaped trigger a user can reason about — a team
        # admin must explicitly enable it before any agent in that team can
        # even select it. That is the whole point of the split (see module
        # docstring): zero blast radius on `document_access`'s existing,
        # already-shipped baseline tool set.
    )
    ConfigModel = EmptyModel

    def tools(
        self,
        ctx: CapabilityContext[EmptyModel, EmptyModel],
    ) -> Sequence[BaseTool]:
        """
        Build the single label-search tool, bound to the turn's typed
        context (RFC §3.2, §5). `AgentCapability.middleware()`'s default
        wraps this for `create_agent()`; no ReAct-loop-specific hook is
        needed.

        Return-convention note (Phase 1, NOTES-GRAPH-CAPABILITY-BRIDGE.md):
        kept as `@tool(..., response_format="content_and_artifact")`
        returning a `(content, ToolInvocationResult)` tuple — see
        `document_access`'s `tools()` docstring for the full rationale;
        identical constraint here.
        """

        services = ctx.services

        @tool("list_documents_by_label", response_format="content_and_artifact")
        async def list_documents_by_label(
            label: str,
            offset: int = 0,
            limit: int = 50,
        ) -> tuple[str, ToolInvocationResult]:
            """List EVERY document carrying a business label, exhaustively and page by page.

            Call this when the user wants a complete answer about a label —
            "list every DAT document", "how many MEX documents are there",
            "find all documents tagged DAT". This tool is exhaustive and
            deterministic: it is the only label-search surface available to
            you, there is no folder-tree filter by label anywhere else.

            Each call returns ONE page: matching documents as "name [uid]",
            plus `total` (the full match count across all pages) and
            `has_more`. When `has_more` is true, call again with
            `offset=<next_offset from this response>` to continue. NEVER
            report a count or a "complete" list to the user after a single
            call without checking `has_more` — a label can match far more
            documents than one page holds.

            The bracketed uid is an internal working id for chaining into
            other tools (e.g. summarize_document) only: NEVER repeat it in
            your answer to the user — refer to documents by display name.
            """

            port = services.document_tree
            if port is None:
                raise RuntimeError(
                    "document_label_search: RuntimeServices.document_tree is "
                    "not available on this execution path."
                )

            effective_limit = _clamp(limit, _LABEL_PAGE_LIMIT_BOUNDS)
            effective_offset = max(offset, 0)
            started = time.monotonic()
            try:
                result: DocumentLabelPageResult = await port.list_by_label(
                    label=label,
                    offset=effective_offset,
                    limit=effective_limit,
                )
            except Exception as exc:
                return _document_tool_failure(
                    tool_ref="list_documents_by_label",
                    action="list documents by label",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                )

            if not result.documents:
                text = f'No documents found with label "{result.label}".'
            else:
                lines = [
                    f'label="{result.label}" total={result.total} offset={result.offset} limit={result.limit}'
                ]
                lines.extend(
                    f"{doc.document_name} [{doc.document_uid}]"
                    for doc in result.documents
                )
                if result.has_more and result.next_offset is not None:
                    lines.append(
                        f"... {result.total - result.next_offset} more — call again with offset={result.next_offset} to continue."
                    )
                text = "\n".join(lines)

            artifact = ToolInvocationResult(
                tool_ref="list_documents_by_label",
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=text),),
            )
            return text, artifact

        return [list_documents_by_label]
