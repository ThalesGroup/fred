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
`DocumentExtractCapability` (DOCREAD-01) — exhaustively extract information from
a document, nothing omitted, through the `document_markdown` port.

Half of the document-reading pair (see `document_read_common`). This capability
answers "give me EVERY X in this document" questions (all requirements, every
deadline…) where a summary would silently drop items — the exact "half answer"
failure mode `document_summarize` has. The tool streams the document's full text
in pages and instructs the model, in-band, to keep paging to the end before
concluding, so completeness is structurally signalled rather than hoped for.

Phase 1 relies on the agent paging to completion (guided by the per-page
continuation footer). If that proves unreliable on very large documents, the
robust follow-up is a server-side map-reduce extraction endpoint (mirroring the
summarize map-reduce but accumulating instead of compressing) — deliberately not
built yet.

Installing fred-runtime registers it via the `fred.capabilities` entry point
(`document_extract`); it is `ADMIN_GATED` (class default).
"""

from __future__ import annotations

from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.models import FieldSpec, UIHints
from langchain_core.tools import BaseTool, tool

from fred_runtime.capabilities.document_read_common import (
    DocumentReadConfig,
    read_document_page,
    resolve_page_max_chars,
)


class DocumentExtractCapability(
    AgentCapability[DocumentReadConfig, DocumentReadConfig, EmptyModel]
):
    """Exhaustive, paginated document extraction. Single tool, no chat controls,
    no turn options, no HITL (read-only)."""

    manifest = CapabilityManifest(
        id="document_extract",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped.
        version="0.1.0",
        name="capability.document_extract.name",
        description="capability.document_extract.description",
        icon="find_in_page",
        config_fields=[
            FieldSpec(
                key="page_max_chars",
                type="integer",
                title="capability.document_extract.fields.page_max_chars.title",
                description="capability.document_extract.fields.page_max_chars.description",
                min=200,
                max=50_000,
                ui=UIHints(group="retrieval", advanced=True),
            ),
        ],
        # team_scope left at the class default (ADMIN_GATED).
    )
    ConfigModel = DocumentReadConfig

    def tools(
        self,
        ctx: CapabilityContext[DocumentReadConfig, EmptyModel],
    ) -> Sequence[BaseTool]:
        config = ctx.config
        services = ctx.services
        page_cap = config.page_max_chars

        @tool("extract_from_document", response_format="content_and_artifact")
        async def extract_from_document(
            document_uid: str,
            what_to_extract: str,
            offset: int = 0,
            max_chars: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Exhaustively extract information from a document — nothing omitted.

            Use this when the user wants a COMPLETE, nothing-missed answer over a
            whole document — e.g. "list ALL the requirements in this spec",
            "every deadline", "each obligation and its owner". It streams the
            document's full text in pages so you can gather every matching item.

            When to use a different tool instead:
            - do NOT use summarize_document for this — a summary silently drops
              items and gives a half-complete answer;
            - to read one specific spot verbatim (e.g. "the first paragraph") →
              read_document.

            `what_to_extract` describes precisely what to enumerate (e.g.
            "functional requirements", "dates and their surrounding context").

            COMPLETENESS — read the document to the END: start at `offset` 0;
            each result tells you whether more text remains and the next offset.
            Keep calling with that next offset, accumulating matches, until the
            result says the end has been reached. NEVER give your final list
            while more text remains.

            `document_uid` MUST be the document's opaque uid, not its name — get
            it from a search hit's 'uid', the document tree, or the
            conversation's attached-files list. NEVER repeat the uid in your
            answer; refer to the document by its display name. `max_chars` bounds
            each page (leave unset for the agent's default).
            """

            # `what_to_extract` steers the model's own reading; the tool returns
            # the raw page text plus the continuation signal (Phase 1 — no
            # server-side extraction pass), so it is intentionally not forwarded
            # to the port.
            _ = what_to_extract
            effective = resolve_page_max_chars(page_cap, max_chars)
            return await read_document_page(
                port=services.document_markdown,
                tool_ref="extract_from_document",
                document_uid=document_uid,
                offset=offset,
                max_chars=effective,
                exhaustive=True,
            )

        return [extract_from_document]
