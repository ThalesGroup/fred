# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deep tools bridging its working files to the shared conversation catalogue."""

from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID, uuid4

import httpx
from fred_sdk.contracts.context import (
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPort,
    WorkspaceFsPort,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool

TOOL_NAMES = (
    "list_conversation_files",
    "read_conversation_file",
    "publish_conversation_file",
)
MAX_BYTES = 4 * 1024 * 1024


class ConversationFilesMiddleware(AgentMiddleware):
    """Use the same middleware tool registration as Deep's concat_files tool."""

    def __init__(
        self,
        filesystem: ConversationFilesystemPort,
        catalogue: WorkspaceFsPort,
        session_id: str,
    ) -> None:
        super().__init__()

        @tool(TOOL_NAMES[0], response_format="content_and_artifact")
        async def list_conversation_files(
            limit: int = 100, offset: int = 0
        ) -> tuple[str, ToolInvocationResult]:
            """List delivered files in this conversation (up to 100 per page).

            Each document_id identifies a file: pass it unchanged to
            read_conversation_file. Each content_id identifies a revision, NOT
            a file: never pass it as document_id. A listed content_id is not a
            read receipt: read the bytes before preparing a replacement.
            """
            files = await catalogue.list(limit=limit, offset=offset)
            return (
                "\n".join(file.model_dump_json() for file in files)
                or "No delivered files.",
                ToolInvocationResult(tool_ref=f"runtime:{TOOL_NAMES[0]}"),
            )

        @tool(TOOL_NAMES[1], response_format="content_and_artifact")
        async def read_conversation_file(
            document_id: Annotated[
                str,
                "File document_id from list_conversation_files, or document_uid "
                "from publication. Never use content_id (a revision identity).",
            ],
            workspace_path: str,
        ) -> tuple[str, ToolInvocationResult]:
            """Copy a delivered UTF-8 Markdown/CSV into a new workspace file.

            List files first and copy the selected entry's document_id exactly.
            Do not use its content_id, path or name as document_id. If the file
            is unavailable, list again and correct document_id before retrying.
            Choose an unused absolute workspace_path, ending in .md or .csv.
            Read/edit it with the workspace tools. Retain the returned content_id
            unchanged as expected_content_id when publishing a replacement.
            This reads up to 4 MiB and never takes an independent latest snapshot.
            """
            _mime(workspace_path)
            if await filesystem.exists(workspace_path, origin="agent"):
                return _error(
                    TOOL_NAMES[1],
                    "Reading the conversation file failed: the workspace path already "
                    "exists. Choose another unused workspace_path and retry. "
                    "The existing file was not changed.",
                )
            try:
                result = await catalogue.read(document_id, max_bytes=MAX_BYTES)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code not in (404, 422):
                    raise
                return _error(
                    TOOL_NAMES[1],
                    "Reading the conversation file failed: the file is unavailable "
                    "in this conversation or document_id is invalid. "
                    "Call list_conversation_files and copy the file's document_id "
                    "exactly; content_id identifies a revision and cannot be used "
                    "to read a file. No workspace file was created.",
                )
            except httpx.TransportError:
                return _error(
                    TOOL_NAMES[1],
                    "Reading the conversation file failed: the connection failed. "
                    "Retry with the same document_id. No workspace file was created.",
                )
            await filesystem.write_text(
                workspace_path, result.content.decode("utf-8"), origin="agent"
            )
            return (
                f"Read document_id={result.document_id}, content_id={result.content_id} "
                f"into {workspace_path}. Use read_file to inspect its text.",
                ToolInvocationResult(tool_ref=f"runtime:{TOOL_NAMES[1]}"),
            )

        @tool(TOOL_NAMES[2], response_format="content_and_artifact")
        async def publish_conversation_file(
            workspace_path: str,
            path: str,
            expected_content_id: str | None = None,
            request_key: str | None = None,
        ) -> tuple[str, ToolInvocationResult]:
            """Deliver an existing workspace Markdown/CSV to this conversation.

            path is the relative catalogue path, e.g. reports/report.md. Null
            expected_content_id creates only; for replacement pass the content_id
            returned by read_conversation_file BEFORE editing. Never obtain a new
            snapshot to bypass a conflict. The source is the saved workspace file,
            not the editor buffer. Maximum 4 MiB. On uncertain transport failure,
            replay the returned request_key with exactly the same arguments and
            unchanged workspace bytes. A CP conflict requires a fresh read and edit.
            The receipt's document_uid is the file identity to use as document_id
            when reading; content_id is only the published revision identity.
            """
            mime = _mime(path)
            _mime(workspace_path)
            key = str(UUID(request_key)) if request_key is not None else str(uuid4())
            content = (
                await filesystem.read_text(workspace_path, origin="agent")
            ).encode("utf-8")
            if len(content) > MAX_BYTES:
                raise ValueError("Deliverable exceeds the 4 MiB transfer limit")
            try:
                artifact = await catalogue.write(
                    f"outputs/{session_id}/{path}",
                    content,
                    expected_content_id=expected_content_id,
                    request_key=key,
                    content_type=mime,
                )
            except httpx.TransportError:
                return _error(
                    TOOL_NAMES[2],
                    "Publishing the conversation file failed: delivery is unconfirmed "
                    f"because the connection failed. Replay request_key={key} with identical "
                    "arguments and unchanged workspace bytes.",
                )
            return (
                artifact.model_dump_json(),
                ToolInvocationResult(
                    tool_ref=f"runtime:{TOOL_NAMES[2]}",
                    ui_parts=(artifact.to_link_part(),),
                ),
            )

        self.tools: Sequence[BaseTool] = [
            list_conversation_files,
            read_conversation_file,
            publish_conversation_file,
        ]


def _error(tool_name: str, message: str) -> tuple[str, ToolInvocationResult]:
    # The model reads the text; streamed and persisted UI errors use the trusted
    # artifact blocks. Keep the same safe cause and recovery instruction in both.
    return message, ToolInvocationResult(
        tool_ref=f"runtime:{tool_name}",
        blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
        is_error=True,
    )


def _mime(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in {".md", ".csv"}:
        raise ValueError(
            "Only Markdown (.md) and CSV (.csv) deliverables are supported"
        )
    return "text/markdown" if suffix == ".md" else "text/csv"
