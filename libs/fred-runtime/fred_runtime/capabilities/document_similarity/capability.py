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
`DocumentSimilarityCapability` — find the passages most similar to an anchor
passage, inside documents named on the call.

Why it is its own capability and not a second tool on `document_access`:
- the two answer different questions. `document_access` searches to ANSWER
  ("what does the corpus say about X?"), scope fixed once per conversation.
  This one COMPARES ("for this passage, what is the closest passage in that
  document?"), re-aimed per call. Same distinction the RFC drew when
  `document_summarize` was split out - separately selectable, so a comparison
  agent can take the comparison primitive without the corpus Q&A tool.
- it sits on its own port (`RuntimeServices.document_similarity`), because its
  targeting comes from the model rather than from the conversation, and that
  changes what the adapter has to enforce.

Doctrine (RFC AGENT-CAPABILITY §3.5, §3.8, §10), same as its siblings:
- the platform is reached ONLY through the typed port; the per-turn binding and
  the raw access token NEVER enter `CapabilityContext`;
- the tool signature exposes ONLY LLM arguments; config reaches the tool through
  the closure, never the schema;
- document uids are internal working identifiers - the tool docstring tells the
  model never to repeat them to the end user.

Read-only, so no HITL gate. `ADMIN_GATED` by the class default.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence

from fred_core.store.vector_search import select_citable_sources
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
from fred_sdk.contracts.models import FieldSpec, UIHints
from fred_sdk.contracts.runtime import (
    DocumentScopeRefusedError,
    DocumentSearchResult,
)
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from fred_runtime.capabilities.document_read_common import document_tool_failure

DOCUMENT_SIMILARITY_TOOL_REF = "document_similarity"

# Same LLM-visible slice the sibling document tools use: citation and reasoning
# fields only, never URLs or operational paths the model could echo back. `uid`
# stays - it is the working identifier for chaining into the reading tools.
_LLM_FIELDS = frozenset(
    {"uid", "title", "content", "file_name", "page", "section", "score"}
)

# Wire bounds, clamped capability-side so an out-of-range model value degrades
# instead of failing the call downstream.
_TOP_K_BOUNDS = (1, 50)

logger = logging.getLogger(__name__)


class DocumentSimilarityConfig(BaseModel):
    """Per-agent-instance tuning. Targeting is deliberately absent: the whole
    point of this mode is that the model names its targets per call, and the
    adapter bounds them by the session binding."""

    default_top_k: int = Field(default=10, ge=1, le=50)
    rerank: bool = Field(default=True)
    min_score: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentSimilarityCapability(
    AgentCapability[DocumentSimilarityConfig, DocumentSimilarityConfig, EmptyModel]
):
    """Targeted comparison search. Single tool, no chat controls, no turn
    options, no HITL (read-only)."""

    manifest = CapabilityManifest(
        id="document_similarity",
        # Pre-GA: version stays 0.1.0 while the platform has not shipped.
        version="0.1.0",
        name="capability.document_similarity.name",
        description="capability.document_similarity.description",
        icon="sync_alt",
        config_fields=[
            FieldSpec(
                key="default_top_k",
                type="integer",
                title="capability.document_similarity.fields.default_top_k.title",
                description="capability.document_similarity.fields.default_top_k.description",
                min=1,
                max=50,
                ui=UIHints(group="retrieval"),
            ),
            FieldSpec(
                key="rerank",
                type="boolean",
                title="capability.document_similarity.fields.rerank.title",
                description="capability.document_similarity.fields.rerank.description",
                ui=UIHints(group="retrieval", advanced=True),
            ),
            FieldSpec(
                key="min_score",
                type="number",
                title="capability.document_similarity.fields.min_score.title",
                description="capability.document_similarity.fields.min_score.description",
                min=0.0,
                max=1.0,
                ui=UIHints(group="retrieval", advanced=True),
            ),
        ],
        # team_scope left at the class default (ADMIN_GATED).
    )
    ConfigModel = DocumentSimilarityConfig

    def tools(
        self,
        ctx: CapabilityContext[DocumentSimilarityConfig, EmptyModel],
    ) -> Sequence[BaseTool]:
        config = ctx.config
        services = ctx.services
        default_top_k = config.default_top_k
        rerank = config.rerank
        min_score = config.min_score

        @tool("find_similar_passages", response_format="content_and_artifact")
        async def find_similar_passages(
            anchor: str,
            document_uids: list[str],
            top_k: int | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Find the passages most similar to an anchor passage, inside specific documents.

            This is a COMPARISON tool, not a question-answering one. `anchor` is
            a passage of text to match against - a sentence, a paragraph, a
            requirement - NOT a question. Use it to compare one document against
            another: "does the operations manual cover what the architecture
            document requires here?", "what in document B corresponds to this
            section of document A?", "is this requirement contradicted anywhere
            in that spec?".

            To compare two documents end to end, call this once per passage of
            the first document with `document_uids` set to the second - each call
            is aimed independently, which is what this tool is for.

            When to use a different tool instead:
            - to answer a question from the corpus at large -> use the vector
              search tool, which is not restricted to named documents;
            - to read a document's own text in order -> use the verbatim read
              tool.

            `document_uids` is REQUIRED and must name at least one document: the
            search runs ONLY inside those documents. They must be opaque
            document uids, not file names - take them from a search hit's 'uid'
            or from the document tree. This tool searches the document corpus
            only: a file attached to this conversation is NOT searchable here,
            so its uid would return nothing. Those uids are internal working
            identifiers for YOUR tool calls: NEVER repeat one in your answer,
            always refer to a document by its display name.

            `top_k` bounds how many matches come back, best-first (leave unset
            for the agent's default). An empty result means nothing in those
            documents resembles the anchor - report that, do not invent a match.
            """

            port = services.document_similarity
            if port is None:
                # No platform port injected (e.g. a bare test harness). Fail
                # LOUD rather than silently returning nothing.
                raise RuntimeError(
                    "document_similarity: RuntimeServices.document_similarity is "
                    "not available on this execution path."
                )

            if not isinstance(anchor, str) or not anchor.strip():
                return _bad_call(
                    "`anchor` must be a non-empty passage of text to match "
                    "against (not a question, and not empty)."
                )
            if not isinstance(document_uids, list) or not document_uids:
                return _bad_call(
                    "`document_uids` must name at least one document to search "
                    "inside - this tool never searches the whole corpus. Resolve "
                    "a document's uid from a search hit, the document tree, or "
                    "the conversation's attached files, then retry."
                )

            uids = [str(uid) for uid in document_uids]
            effective_top_k = (
                _clamp(top_k, _TOP_K_BOUNDS)
                if isinstance(top_k, int) and not isinstance(top_k, bool) and top_k > 0
                else default_top_k
            )

            started = time.monotonic()
            try:
                result: DocumentSearchResult = await port.find_similar(
                    anchor,
                    document_uids=uids,
                    top_k=effective_top_k,
                    rerank=rerank,
                    min_score=min_score,
                )
            except DocumentScopeRefusedError as exc:
                # Nothing was searched, so this must never reach the model as an
                # empty result - it would report "nothing matches" about a
                # document it never looked at.
                return _bad_call(
                    "Cannot search "
                    f"{', '.join(exc.requested_uids) or 'those documents'}: they "
                    "are not part of this conversation's document scope, so "
                    "nothing was searched. This is NOT a 'no matches' answer. "
                    "Use a document that is in scope - resolve one from a search "
                    "hit or the document tree - or tell the user the document is "
                    "out of scope."
                )
            except Exception as exc:
                # Same contract as the sibling document tools: degrade to an
                # `is_error` artifact rather than raising, or the default
                # ToolNode handler re-raises and the whole turn dies with an
                # empty error detail.
                return document_tool_failure(
                    tool_ref=DOCUMENT_SIMILARITY_TOOL_REF,
                    action="find similar passages",
                    exc=exc,
                    elapsed_s=time.monotonic() - started,
                    document_uid=", ".join(uids),
                )

            hits = result.hits
            content = {
                "anchor": anchor,
                "document_uids": uids,
                "hits": [
                    {
                        k: v
                        for k, v in hit.model_dump(mode="json").items()
                        if k in _LLM_FIELDS
                    }
                    for hit in hits
                ],
            }
            # `sources` keeps the dataset-pointer exclusion (metadata, never
            # citable) but switches off the score-ratio one: that filter drops
            # hits that are noise relative to the best match, which is the right
            # call for a corpus-wide search and the wrong one here - the caller
            # named these documents, so a weak match is a real finding about
            # them, often the interesting one ("nothing in B really matches").
            artifact = ToolInvocationResult(
                tool_ref=DOCUMENT_SIMILARITY_TOOL_REF,
                blocks=(ToolContentBlock(kind=ToolContentKind.JSON, data=content),),
                sources=select_citable_sources(hits, min_score_ratio=0.0),
            )
            return json.dumps(content), artifact

        return [find_similar_passages]


def _clamp(value: int, bounds: tuple[int, int]) -> int:
    low, high = bounds
    return max(low, min(value, high))


def _bad_call(message: str) -> tuple[str, ToolInvocationResult]:
    """A malformed tool call, answered as an `is_error` artifact the model can
    act on. Not `document_tool_failure`: nothing failed downstream, so its
    transport wording ("the Knowledge Flow service ...") would be a lie."""

    return message, ToolInvocationResult(
        tool_ref=DOCUMENT_SIMILARITY_TOOL_REF,
        is_error=True,
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
    )
