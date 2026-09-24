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

"""Integration coverage for Deep's protected internal filesystem mount."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.deep_runtime import (
    _build_conversation_backend,
)
from langchain_core.messages import ToolMessage


class _MemoryFilesystem:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    async def read(self, path: str) -> bytes:
        try:
            return self.files[path]
        except KeyError as exc:
            raise FileNotFoundError(path) from exc

    async def write(self, path: str, data: bytes | str) -> None:
        self.files[path] = data if isinstance(data, bytes) else data.encode()

    async def list(self, prefix: str = "") -> list[FilesystemResourceInfoResult]:
        return [
            FilesystemResourceInfoResult(
                path=path,
                size=len(content),
                type=FilesystemResourceInfo.FILE,
                modified=datetime.now(UTC),
            )
            for path, content in sorted(self.files.items())
            if path.startswith(prefix)
        ]

    async def delete(self, path: str) -> None:
        self.files.pop(path, None)

    async def mkdir(self, path: str) -> None:
        del path

    async def exists(self, path: str) -> bool:
        return path in self.files


@pytest.mark.asyncio
async def test_model_write_and_edit_permissions_preserve_deep_internal_file() -> None:
    filesystem = ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    internal = filesystem.namespace(".deep")
    await internal.write_text("artifact.txt", "original")
    backend = _build_conversation_backend(filesystem)
    middleware = FilesystemMiddleware(
        backend=backend,
        _permissions=[
            FilesystemPermission(operations=["write"], paths=["/.deep/**"], mode="deny")
        ],
    )
    tools = {entry.name: entry for entry in middleware.tools}
    runtime = cast(Any, SimpleNamespace(tool_call_id="model-filesystem-call"))

    write = await cast(Any, tools["write_file"]).coroutine(
        file_path="/.deep/artifact.txt", content="overwritten", runtime=runtime
    )
    edit = await cast(Any, tools["edit_file"]).coroutine(
        file_path="/.deep/artifact.txt",
        old_string="original",
        new_string="edited",
        runtime=runtime,
    )

    assert isinstance(write, ToolMessage)
    assert write.status == "error"
    assert "permission denied for write" in str(write.content)
    assert isinstance(edit, ToolMessage)
    assert edit.status == "error"
    assert "permission denied for write" in str(edit.content)
    assert await internal.read_text("artifact.txt") == "original"

    root_write = await cast(Any, tools["write_file"]).coroutine(
        file_path="/notes.txt", content="shared", runtime=runtime
    )
    root_read = await cast(Any, tools["read_file"]).coroutine(
        file_path="/notes.txt", runtime=runtime
    )
    assert root_write.status == "success"
    assert root_read.status == "success"
    assert "shared" in str(root_read.content)


@pytest.mark.asyncio
async def test_trusted_backend_routes_deep_artifacts_to_persistent_namespace() -> None:
    filesystem = ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    internal = filesystem.namespace(".deep")
    backend = _build_conversation_backend(filesystem)

    result = await backend.awrite(
        "/.deep/large_tool_results/tool-call", "trusted middleware content"
    )

    assert backend.artifacts_root == "/.deep"
    assert result.error is None
    assert result.path == "/.deep/large_tool_results/tool-call"
    artifact_paths = await internal.list("large_tool_results")
    assert artifact_paths == ("large_tool_results/tool-call",)
    assert (
        await internal.read_text("large_tool_results/tool-call")
        == "trusted middleware content"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("root", [None, "/"])
async def test_root_search_aggregates_workspace_and_internal_mount(
    root: str | None,
) -> None:
    filesystem = ConversationFilesystemService(_MemoryFilesystem(), "conversation-a")
    await filesystem.scratchpad().write_text("notes/shared.md", "shared needle")
    await filesystem.namespace(".deep").write_text(
        "large_tool_results/result.md", "internal needle"
    )
    backend = _build_conversation_backend(filesystem)

    globbed = await backend.aglob("**/*.md", path=root)
    grepped = await backend.agrep("needle", path=root, glob="*.md")

    assert globbed.error is None
    assert [match["path"] for match in globbed.matches or []] == [
        "/.deep/large_tool_results/result.md",
        "/notes/shared.md",
    ]
    assert grepped.error is None
    assert [match["path"] for match in grepped.matches or []] == [
        "/notes/shared.md",
        "/.deep/large_tool_results/result.md",
    ]


@pytest.mark.asyncio
async def test_unmounted_paths_use_root_workspace() -> None:
    storage = _MemoryFilesystem()
    backend = _build_conversation_backend(
        ConversationFilesystemService(storage, "conversation-a")
    )

    written = await backend.awrite("/outside/notes.md", "needle")
    read = await backend.aread("/outside/notes.md")
    grepped = await backend.agrep("needle", path="/outside/")

    assert written.error is None
    assert read.file_data == {"content": "needle", "encoding": "utf-8"}
    assert (
        storage.files["conversations/conversation-a/scratchpad/outside/notes.md"]
        == b"needle"
    )
    assert [match["path"] for match in grepped.matches or []] == ["/outside/notes.md"]


def test_missing_conversation_filesystem_fails_closed() -> None:
    with pytest.raises(RuntimeError, match="requires a conversation filesystem"):
        _build_conversation_backend(None)
