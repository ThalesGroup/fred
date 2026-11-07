# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Deep tools bridging its working files to the shared conversation catalogue."""

from collections.abc import Sequence
from pathlib import PurePosixPath
from uuid import UUID, uuid4

import httpx
from fred_sdk.contracts.context import ToolInvocationResult
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

            Use the document_id to read a file. A listed content_id is not a
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
            document_id: str, workspace_path: str
        ) -> tuple[str, ToolInvocationResult]:
            """Copy a delivered UTF-8 Markdown/CSV into a new workspace file.

            Choose an unused absolute workspace_path, ending in .md or .csv.
            Read/edit it with the workspace tools. Retain the returned content_id
            unchanged as expected_content_id when publishing a replacement.
            This reads up to 4 MiB and never takes an independent latest snapshot.
            """
            _mime(workspace_path)
            if await filesystem.exists(workspace_path, origin="agent"):
                raise ValueError(
                    "Choose an unused workspace path for the delivered file"
                )
            result = await catalogue.read(document_id, max_bytes=MAX_BYTES)
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
                return (
                    f"Delivery unconfirmed. Replay request_key={key} with identical "
                    "arguments and unchanged workspace bytes.",
                    ToolInvocationResult(
                        tool_ref=f"runtime:{TOOL_NAMES[2]}", is_error=True
                    ),
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


def _mime(path: str) -> str:
    suffix = PurePosixPath(path).suffix.lower()
    if suffix not in {".md", ".csv"}:
        raise ValueError(
            "Only Markdown (.md) and CSV (.csv) deliverables are supported"
        )
    return "text/markdown" if suffix == ".md" else "text/csv"
