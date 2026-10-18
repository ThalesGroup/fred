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

"""Built-in presentation of live conversation files for parents and children."""

import json
from pathlib import PurePosixPath

from fred_sdk.contracts.context import (
    ConversationFilePart,
    ToolContentBlock,
    ToolContentKind,
    ToolInvocationResult,
)
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPort,
    ConversationScratchpadError,
    ConversationScratchpadUnsupportedContentError,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool

from fred_runtime.deep.conversation_port import normalize_virtual_path


def file_reference(
    session_id: str, path: str, *, editable: bool
) -> ConversationFilePart:
    path = normalize_virtual_path(path)
    suffix = PurePosixPath(path).suffix.lower()
    viewer = (
        "markdown"
        if suffix in {".md", ".markdown"}
        else "html"
        if suffix in {".html", ".htm"}
        else "text"
    )
    return ConversationFilePart(
        session_id=session_id,
        path=path,
        viewer=viewer,
        editable=editable,
    )


def ensure_presentable(content: str) -> None:
    if "\x00" in content:
        raise ConversationScratchpadUnsupportedContentError(
            "Only UTF-8 text files can be opened."
        )


class OpenFileMiddleware(AgentMiddleware):
    def __init__(
        self, filesystem: ConversationFilesystemPort | None, session_id: str
    ) -> None:
        super().__init__()

        @tool("open", response_format="content_and_artifact")
        async def open_file(path: str) -> tuple[str, ToolInvocationResult]:
            """Request presentation of an existing UTF-8 conversation file in the chat panel.

            Use an absolute virtual path. Returns a bounded reference, never the
            file body. This does not pause execution or confirm browser receipt.
            """
            if filesystem is None:
                return (
                    "Conversation file storage is unavailable.",
                    ToolInvocationResult(
                        tool_ref="runtime:open",
                        is_error=True,
                        blocks=(
                            ToolContentBlock(
                                kind=ToolContentKind.TEXT,
                                text="Conversation file storage is unavailable.",
                            ),
                        ),
                    ),
                )
            try:
                reference = file_reference(
                    session_id, path, editable=filesystem.is_editable(path)
                )
                ensure_presentable(
                    await filesystem.read_text(reference.path, origin="agent")
                )
            except (ConversationScratchpadError, ValueError) as exc:
                message = "Cannot open file: " + str(exc)[:512]
                return message, ToolInvocationResult(
                    tool_ref="runtime:open",
                    is_error=True,
                    blocks=(ToolContentBlock(kind=ToolContentKind.TEXT, text=message),),
                )
            return "File presentation requested: " + json.dumps(
                {
                    "path": reference.path,
                    "viewer": reference.viewer,
                    "editable": reference.editable,
                },
                ensure_ascii=True,
            ), ToolInvocationResult(
                tool_ref="runtime:open",
                ui_parts=(reference,),
            )

        self.tools = [open_file]
