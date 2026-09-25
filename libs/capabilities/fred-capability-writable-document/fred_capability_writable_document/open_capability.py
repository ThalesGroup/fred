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

"""Opt-in demo tool that copies a Deep workspace Markdown file into the editor."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import PurePosixPath

from fred_sdk.contracts.capability import (
    AgentCapability,
    CapabilityContext,
    CapabilityManifest,
    EmptyModel,
)
from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import ConversationScratchpadError
from langchain_core.tools import BaseTool, tool

from fred_capability_writable_document.capability import save_writable_document

logger = logging.getLogger(__name__)

_TOOL_REF = "open_writable_document"
_MAX_IMPORT_BYTES = 1024 * 1024


def _markdown_path(path: str) -> str:
    if not path.startswith("/"):
        raise ValueError("Use an absolute workspace path, such as /report.md.")
    if PurePosixPath(path).suffix.lower() != ".md":
        raise ValueError("Only Markdown (.md) files can be opened in this editor.")
    return path


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)


class OpenWritableDocumentCapability(
    AgentCapability[EmptyModel, EmptyModel, EmptyModel]
):
    """Add a separately enabled import tool; writable_document owns the editor."""

    manifest = CapabilityManifest(
        id="open_writable_document",
        version="0.1.0",
        name="capability.open_writable_document.name",
        description="capability.open_writable_document.description",
        icon="edit_document",
        execution_models=("react",),
    )
    ConfigModel = EmptyModel

    def tools(
        self, ctx: CapabilityContext[EmptyModel, EmptyModel]
    ) -> Sequence[BaseTool]:
        filesystem = ctx.services.conversation_filesystem
        session_id = ctx.identity.session_id
        user_id = ctx.identity.user_id

        @tool("open_writable_document", response_format="content_and_artifact")
        async def open_writable_document(
            path: str,
            title: str,
        ) -> tuple[str, ToolInvocationResult]:
            """Open an existing conversation Markdown file in the user's editor.

            Use this after writing a final .md file, including one assembled with
            concat_files. Pass its absolute workspace path (for example /report.md).
            The editor receives a copy: later editor changes do not modify the file.
            The user must also have the writable_document capability enabled.
            Do not read the file or repeat its content in the chat.
            """

            if not session_id:
                return _error("Cannot open a file without an active conversation.")
            if filesystem is None:
                return _error("Conversation files are unavailable on this agent.")
            if not title.strip():
                return _error("Give the document a non-empty title.")
            try:
                content = await filesystem.read_text(
                    _markdown_path(path), origin="agent"
                )
            except (ValueError, ConversationScratchpadError) as exc:
                return _error(f"Cannot open {path}: {exc}")
            if len(content.encode("utf-8")) > _MAX_IMPORT_BYTES:
                return _error(
                    "This Markdown file is too large for the demo editor (1 MiB limit)."
                )
            try:
                return await save_writable_document(
                    session_id=session_id,
                    user_id=user_id,
                    title=title,
                    content_markdown=content,
                    tool_ref=_TOOL_REF,
                )
            except Exception:
                logger.exception(
                    "Failed to import workspace Markdown for session=%s", session_id
                )
                return _error("Could not save the Markdown file in the editor.")

        return [open_writable_document]
