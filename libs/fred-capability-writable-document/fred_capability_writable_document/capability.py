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

"""`WritableDocumentCapability` — the writable_document feature as ONE capability (#1905).

Why this module exists:
- Kea shipped "Writable Documents" scattered across an in-process tool factory, a
  chat-part hydrated out of tool JSON (`fred_parts`), a bespoke controller, a
  Postgres store wired into `ApplicationContext`, and — crucially — orchestrator
  bookkeeping that diffed each session's last-activity time to decide when to tell
  the agent the user had edited a document. On Swift the WHOLE feature is this one
  `AgentCapability` (RFC AGENT-CAPABILITY-RFC.md §3): the manifest (contributed
  `writable_document` chat part, editor side panel, list/get/put/export router, one
  owned table) plus the chat-time middleware (the `write_document` tool, the
  user-edit notification, and the open-documents catalog prompt).

The three middleware hooks map one-to-one onto the Kea orchestrator seams they
replace:
- the `write_document` tool ports Kea's in-process tool verbatim (full-content
  replace, de-dup by exact title within the session, reuse `document_id` to revise
  in place) — but identity flows through the closure, never the tool schema (RFC §3.5).
- `abefore_model` replaces the orchestrator's `_collect_user_edited_documents`
  last-activity diff with a durable per-row flag (`agent_notified_at`): a user edit
  clears it (router PUT), and this hook injects the SAME system note Kea injected,
  then stamps the flag so the note fires exactly once.
- `awrap_model_call` replaces the orchestrator's model-only "documents already open"
  reminder, overlaying the write-instructions fragment (always) and the SAME catalog
  text (when documents exist) on the system prompt per model call (the
  `_McpInstructionsMiddleware` delivery path) so they survive across turns
  without being persisted.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, cast

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
    SidePanelSpec,
)
from fred_sdk.contracts.context import ToolInvocationResult, UiPart
from langchain.agents.middleware import AgentMiddleware, AgentState
from langchain.agents.middleware.types import ModelRequest, ModelResponse
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel

from fred_capability_writable_document.router import build_router
from fred_capability_writable_document.store import (
    WritableDocumentDoc,
    WritableDocumentRecord,
    get_writable_document_store,
    new_document_id,
)

logger = logging.getLogger(__name__)

WRITABLE_DOCUMENT_CAPABILITY_ID = "writable_document"

# The tool-result `tool_ref` this capability stamps on its artifact.
_TOOL_REF = "writable_document"


class WritableDocumentPart(BaseModel):
    """
    The capability's contributed `writable_document` chat part (#1905, RFC §3.6).

    Emitted as the `write_document` tool's artifact and rendered by the frontend as
    the collaborative editor pane. `updated_by` distinguishes an agent write from a
    user edit so the pane can reflect authorship.
    """

    type: Literal["writable_document"] = "writable_document"
    document_id: str
    title: str
    content_md: str
    updated_at: datetime
    updated_by: Literal["agent", "user"] = "agent"


def _edit_note_text(record: WritableDocumentRecord) -> str:
    """The system note injected when the user edited a document (Kea wording)."""

    return (
        f"The user edited the document '{record.title}' "
        f"(id={record.document_id}). Its current content is now:\n\n"
        f"{record.content_md}"
    )


def _open_documents_fragment(records: Sequence[WritableDocumentRecord]) -> str:
    """The open-documents catalog reminder overlaid on the system prompt (Kea wording)."""

    catalog = "\n".join(
        f"- '{record.title}' (document_id={record.document_id})" for record in records
    )
    return (
        "Collaborative documents already open in the editor for this "
        f"session:\n{catalog}\n\n"
        "When the user asks to modify, revise, correct, extend, shorten, "
        "reformat, or otherwise change one of these documents, call "
        "write_document with that exact document_id so the SAME document "
        "is updated in place. Only omit document_id when the user clearly "
        "wants a brand-new, separate document."
    )


# Non-negotiable behavioral fragment delivered whenever the capability is
# active (same prompt-fragment delivery path as the MCP capabilities'
# `agent_instructions` and the PPT filler's fill instructions). Without it,
# models answer "write me a report" inline in the chat instead of opening
# the collaborative editor.
_WRITE_INSTRUCTIONS = (
    "WRITABLE DOCUMENT: when the user asks — in any wording or language — to "
    "write, create, draft, or produce a document, report, email, memo, "
    "meeting notes, or any other textual deliverable, you MUST call the "
    "'write_document' tool; never write the deliverable itself in the chat. "
    "The tool opens the document in a side-by-side editor where the user can "
    "review, edit, and export it. In the chat, reply only with a short "
    "summary of what you put in the document."
)


class _WritableDocumentMiddleware(AgentMiddleware):
    """The writable_document runtime half: tool + edit-notification + catalog prompt.

    Identity (`user_id`, `session_id`) is closed over from `ctx.identity`; the store
    is resolved per call through the overridable provider so tests substitute a fake.
    """

    def __init__(self, ctx: CapabilityContext[EmptyModel, EmptyModel]) -> None:
        super().__init__()
        identity = ctx.identity
        session_id = identity.session_id
        user_id = identity.user_id

        @tool("write_document", response_format="content_and_artifact")
        async def write_document(
            title: str,
            content_markdown: str,
            document_id: str | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Create or update a collaborative document shown to the user in the editor panel.

            Use this whenever you are producing a deliverable document (report, email, memo,
            meeting notes) so the document is separated from the conversation and the user can
            edit it and export it to various formats (Word and Markdown).

            IMPORTANT - revise in place, never duplicate: to modify, correct, extend, shorten,
            reformat, or otherwise change a document that ALREADY exists, you MUST pass its
            existing document_id (returned as "saved (id=...)" by the previous call, and listed
            in the session's open-documents reminder). Omit document_id ONLY when the user
            clearly wants a brand-new, separate document.

            Provide the full document each time as Markdown in content_markdown (it replaces the
            previous content, it is not appended).
            """

            if not session_id:
                # No active session to scope the document to — fail gracefully so
                # the model gets a usable message instead of a crash.
                return (
                    "Cannot save the document: no active session.",
                    ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True),
                )

            store = get_writable_document_store()
            doc_id = document_id
            if doc_id is None:
                # Deterministic de-dup safety net: if a document with the same title
                # already exists in this session, revise it instead of creating a
                # duplicate. Agents reliably reuse the title when revising but sometimes
                # omit document_id; without this they would spawn a second editor tab.
                try:
                    existing = await store.list_for_session(session_id)
                except Exception:
                    logger.exception(
                        "[WRITABLE_DOC][TOOL] failed to list documents for session=%s",
                        session_id,
                    )
                    existing = []
                match = next(
                    (d for d in existing if (d.title or "").strip() == title.strip()),
                    None,
                )
                if match is not None:
                    doc_id = match.document_id
            if doc_id is None:
                doc_id = new_document_id()

            stored = await store.upsert(
                WritableDocumentRecord(
                    session_id=session_id,
                    document_id=doc_id,
                    user_id=user_id,
                    title=title,
                    content_md=content_markdown,
                    updated_by="agent",
                )
            )

            part = WritableDocumentPart(
                document_id=stored.document_id,
                title=stored.title,
                content_md=stored.content_md,
                updated_at=stored.updated_at or datetime.now(timezone.utc),
                updated_by="agent",
            )
            logger.info(
                "[WRITABLE_DOC][TOOL] session=%s document_id=%s title=%r len=%d",
                session_id,
                doc_id,
                title[:80],
                len(content_markdown),
            )
            artifact = ToolInvocationResult(
                tool_ref=_TOOL_REF,
                ui_parts=(cast(UiPart, part),),
            )
            return f"Document '{title}' saved (id={doc_id}).", artifact

        tools: Sequence[BaseTool] = [write_document]
        self.tools = tools
        self._session_id = session_id

    async def abefore_model(
        self, state: AgentState, runtime: Any
    ) -> dict[str, Any] | None:
        """Notify the agent, once, about documents the user edited since last turn.

        Replaces Kea's orchestrator last-activity diff with the durable
        `agent_notified_at` flag: pull the user-edited-and-unnotified rows, inject the
        SAME system note per document, then stamp each notified so it fires once.
        Returns None (no state update) when nothing changed.
        """

        del state, runtime
        if not self._session_id:
            return None
        store = get_writable_document_store()
        try:
            edited = await store.list_user_edited_unnotified(self._session_id)
        except Exception:
            logger.exception(
                "[WRITABLE_DOC] failed to list user-edited documents for session=%s",
                self._session_id,
            )
            return None
        if not edited:
            return None

        now = datetime.now(timezone.utc)
        messages: list[SystemMessage] = []
        for record in edited:
            messages.append(SystemMessage(_edit_note_text(record)))
            await store.mark_agent_notified(self._session_id, record.document_id, now)
        logger.info(
            "[WRITABLE_DOC] session=%s injecting %d user-edited document note(s): %s",
            self._session_id,
            len(edited),
            [record.document_id for record in edited],
        )
        return {"messages": messages}

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Overlay the write instructions and the open-documents catalog (per model call).

        Mirrors `_McpInstructionsMiddleware`: the static composed system prompt reaches
        `create_agent`; this middleware overlays the capability fragments per model call
        so the "use write_document" and "revise in place" reminders survive across
        turns without being persisted.
        """

        fragments = [_WRITE_INSTRUCTIONS]
        if self._session_id:
            store = get_writable_document_store()
            try:
                records = await store.list_for_session(self._session_id)
            except Exception:
                logger.exception(
                    "[WRITABLE_DOC] failed to list documents for session=%s",
                    self._session_id,
                )
                records = []
            if records:
                fragments.append(_open_documents_fragment(records))
        base = request.system_prompt or ""
        overlay = "\n\n".join(fragments)
        merged = f"{base}\n\n{overlay}" if base else overlay
        request = request.override(system_message=SystemMessage(content=merged))
        return await handler(request)


class WritableDocumentCapability(AgentCapability[EmptyModel, EmptyModel, EmptyModel]):
    """
    Co-author a session-scoped Markdown document from chat (#1905, Kea port).

    No agent-creation config, no upload slots, no chat controls, no HITL — the
    whole feature is the contributed chat part, the editor side panel, the
    list/get/put/export router, the one owned table, and the chat-time middleware.
    See the module docstring for the three middleware hooks and the Kea seams they
    replace.
    """

    manifest = CapabilityManifest(
        id=WRITABLE_DOCUMENT_CAPABILITY_ID,
        version="0.1.0",
        name="capability.writable_document.name",
        description="capability.writable_document.description",
        icon="edit_note",
        chat_parts=[WritableDocumentPart],
        side_panels=[SidePanelSpec(widget="writable_document_pane")],
        router=build_router(),
        tables=[WritableDocumentDoc],
        # CAPAB-02: needs a `before_model` state edit (user-edit detection ->
        # hidden system note) and a `wrap_model_call` prompt overlay for open
        # documents — both ReAct-only hooks `tools()` cannot express.
        # Explicitly ReAct-only rather than silently contributing zero tools
        # to a Graph agent that selects this capability.
        execution_models=("react",),
    )
    ConfigModel = EmptyModel

    @classmethod
    def migrations_location(cls) -> str:
        """The capability's own Alembic tree, applied under
        `cap_writable_document_alembic_version` by `python -m fred_runtime migrate`."""

        return str(Path(__file__).resolve().parent / "writable_document_migrations")

    def middleware(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> list[AgentMiddleware]:
        return [_WritableDocumentMiddleware(ctx)]
