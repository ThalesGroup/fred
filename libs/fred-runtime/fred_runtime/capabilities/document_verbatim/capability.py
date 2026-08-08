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
`DocumentVerbatimCapability` (DOCREAD-01) — read a document's exact text
verbatim, one bounded page at a time, through the `document_markdown` port.

Half of the document-reading pair (see `document_read_common`). This capability
answers positional/literal questions ("what does the first paragraph say?",
"read section 3") — distinct from `document_extract` (exhaustive enumeration by
criterion) and `document_summarize` (a lossy overview). All three can coexist on
one agent; each tool's docstring draws the boundary so the model picks the right
one.

Installing fred-runtime registers it via the `fred.capabilities` entry point
(`document_verbatim`); it is `ADMIN_GATED` (class default), a per-agent opt-in a
team admin must enable.
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


class DocumentVerbatimCapability(
    AgentCapability[DocumentReadConfig, DocumentReadConfig, EmptyModel]
):
    """Verbatim, paginated document read. Single tool, no chat controls, no turn
    options, no HITL (read-only)."""

    manifest = CapabilityManifest(
        id="document_verbatim",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped.
        version="0.1.0",
        name="capability.document_verbatim.name",
        description="capability.document_verbatim.description",
        icon="description",
        config_fields=[
            FieldSpec(
                key="page_max_chars",
                type="integer",
                title="capability.document_verbatim.fields.page_max_chars.title",
                description="capability.document_verbatim.fields.page_max_chars.description",
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

        @tool("read_document", response_format="content_and_artifact")
        async def read_document(
            document_uid: str,
            offset: int = 0,
            max_chars: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Read a document's exact text VERBATIM, one page at a time.

            Use this to see what a document literally says at a given position —
            e.g. "what does the first paragraph say?", "read the introduction",
            "show me section 3" — or to read a whole short document. Returns the
            document's text unchanged, NOT a summary.

            When to use a different tool instead:
            - for a short, lossy overview of the whole document → summarize_document;
            - to enumerate EVERY item matching a criterion across the whole
              document ("all the requirements") → extract_from_document.

            `document_uid` MUST be the document's opaque uid, not its name — get
            it from a search hit's 'uid', the document tree, or the
            conversation's attached-files list. The uid is an internal working
            identifier for YOUR tool calls only: NEVER repeat it in your answer;
            always refer to the document by its display name.

            `offset` is the character position to start from (0 = the very
            beginning). `max_chars` bounds this page (leave unset for the agent's
            default). If the returned result says more text remains, call again
            with the next offset it gives you to keep reading.
            """

            effective = resolve_page_max_chars(page_cap, max_chars)
            return await read_document_page(
                port=services.document_markdown,
                tool_ref="read_document",
                document_uid=document_uid,
                offset=offset,
                max_chars=effective,
                exhaustive=False,
            )

        return [read_document]
