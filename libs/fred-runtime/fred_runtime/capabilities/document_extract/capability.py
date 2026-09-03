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
`DocumentExtractCapability` (DOCREAD-01) — exhaustively extract information from a
document, nothing omitted.

Phase 2 (2026-08-07): the tool no longer pages the document into the agent's own
context (which made the agent burst many token-heavy model calls and trip the
provider's rate limit). It now makes ONE call to the `document_extraction` port,
which runs the exhaustive map-reduce server-side in Knowledge Flow — mapping over
EVERY chunk with bounded concurrency and 429 backoff, then de-duplicating without
compressing — and returns the consolidated list. `document_verbatim`'s
positional read stays on the paginated `document_markdown` port; only exhaustive
extraction moved server-side.

Admin-gated (class default), registered via the `document_extract`
`fred.capabilities` entry point.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    HitlGateRequest,
    HitlSpec,
)
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import DocumentScopeRefusedError
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from fred_runtime.capabilities.document_read_common import (
    document_scope_refusal,
    document_tool_failure,
)


class DocumentExtractConfig(BaseModel):
    """Agent-creation / stored config of the document-extract capability.

    `require_confirmation` gates each `extract_from_document` call behind a human
    proceed/cancel (default on): extraction is token-heavy, so the confirmation
    is shown BEFORE any LLM work is spent. An admin who trusts this agent's usage
    can turn it off per instance. Same mechanism/field name as
    `document_summarize` (RFC §5.4)."""

    require_confirmation: bool = True


class DocumentExtractCapability(
    AgentCapability[DocumentExtractConfig, DocumentExtractConfig, EmptyModel]
):
    """Exhaustive, server-side document extraction. Single tool, no chat
    controls, no turn options; HITL-gated by default (token-heavy), configurable
    per instance via `require_confirmation`."""

    manifest = CapabilityManifest(
        id="document_extract",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped.
        version="0.1.0",
        name="capability.document_extract.name",
        description="capability.document_extract.description",
        icon="find_in_page",
        config_fields=[
            FieldSpec(
                key="require_confirmation",
                type="boolean",
                title="capability.document_extract.fields.require_confirmation.title",
                description="capability.document_extract.fields.require_confirmation.description",
                default=True,
                ui=UIHints(group="safety"),
            ),
        ],
        # team_scope left at the class default (ADMIN_GATED).
    )
    ConfigModel = DocumentExtractConfig

    def tools(
        self,
        ctx: CapabilityContext[DocumentExtractConfig, EmptyModel],
    ) -> Sequence[BaseTool]:
        services = ctx.services

        @tool("extract_from_document", response_format="content_and_artifact")
        async def extract_from_document(
            document_uid: str,
            what_to_extract: str,
        ) -> tuple[str, ToolInvocationResult]:
            """Exhaustively extract information from a document — nothing omitted.

            Use this when the user wants a COMPLETE, nothing-missed answer over a
            whole document — e.g. "list ALL the requirements in this spec",
            "every deadline", "each obligation and its owner". One call reads the
            ENTIRE document (server-side) and returns a consolidated,
            de-duplicated list of every matching item — you do NOT page through
            the document yourself.

            When to use a different tool instead:
            - do NOT use summarize_document for this — a summary silently drops
              items and gives a half-complete answer;
            - to read one specific spot verbatim (e.g. "the first paragraph") →
              read_document.

            `what_to_extract` describes precisely what to enumerate (e.g.
            "functional requirements", "dates and their surrounding context").
            `document_uid` MUST be the document's opaque uid, not its name — get
            it from a search hit's 'uid', the document tree, or the
            conversation's attached-files list. NEVER repeat the uid in your
            answer; refer to the document by its display name.

            The returned list is already complete: present it to the user, do not
            call this tool again for the same request.
            """

            port = services.document_extraction
            if port is None:
                raise RuntimeError(
                    "extract_from_document: RuntimeServices.document_extraction "
                    "is not available on this execution path."
                )

            started = time.monotonic()
            try:
                result = await port.extract(document_uid, instruction=what_to_extract)
            except DocumentScopeRefusedError as exc:
                return document_scope_refusal(
                    tool_ref="extract_from_document",
                    action="extract from the document",
                    exc=exc,
                )
            except Exception as exc:
                message, artifact = document_tool_failure(
                    tool_ref="extract_from_document",
                    action="extract from the document",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                    document_uid=document_uid,
                )
                return message, artifact

            if result.item_count == 0:
                content = (
                    f"No items matching “{what_to_extract}” were found in the document."
                )
            else:
                content = result.extraction
                if result.truncated:
                    content += (
                        "\n\n[Note: the document exceeded the processing cap and "
                        "was read head+tail; some middle content may be omitted.]"
                    )

            artifact = ToolInvocationResult(
                tool_ref="extract_from_document",
                blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=content),),
            )
            return content, artifact

        return [extract_from_document]

    def hitl_specs(self) -> Sequence[HitlSpec]:
        """Gate `extract_from_document` behind a human proceed/cancel, on by
        default and per-instance configurable via `require_confirmation`
        (RFC §5.4), the same mechanism as `document_summarize`. `require=False`
        defers to the `when` predicate, which reads the resolved instance config
        fresh at gate time (`request.context.config`) — so it always reflects the
        CURRENT `require_confirmation`, not whatever was set at assembly time.
        The gate runs BEFORE the tool, so a cancel spends no extraction tokens."""

        return [
            HitlSpec(
                tool="extract_from_document",
                require=False,
                when=_confirmation_required,
            )
        ]


def _confirmation_required(request: HitlGateRequest) -> bool:
    """Whether this agent instance still wants a human's proceed/cancel before
    `extract_from_document` runs — the resolved `require_confirmation` config
    value (default `True`, see `DocumentExtractConfig`)."""

    return bool(request.context.config.require_confirmation)
