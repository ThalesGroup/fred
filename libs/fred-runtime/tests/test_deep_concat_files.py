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

"""Public concat tool behavior against the mounted conversation workspace."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import patch

import pytest
from deepagents.middleware.filesystem import FilesystemMiddleware
from fred_core.filesystem.structures import (
    FilesystemResourceInfo,
    FilesystemResourceInfoResult,
)
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.concat_files import ConcatFilesMiddleware
from fred_runtime.deep.conversation_port import DeepConversationFilesystemPort
from fred_runtime.deep.deep_runtime import build_conversation_filesystem
from langchain_core.messages import ToolMessage


class _Workspace:
    def __init__(self) -> None:
        self.storage = _MemoryFilesystem()
        service = ConversationFilesystemService(self.storage, "conversation-a")
        backend, permissions = build_conversation_filesystem(service)
        self.port = DeepConversationFilesystemPort(backend, permissions)

    async def write_text(self, path: str, content: str) -> None:
        await self.port.write_text(f"/{path}", content, origin="system")

    async def read_text(self, path: str) -> str:
        return await self.port.read_text(f"/{path}", origin="system")

    async def exists(self, path: str) -> bool:
        return await self.port.exists(f"/{path}", origin="system")


def _scratchpad() -> _Workspace:
    return _Workspace()


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

    async def mkdir(self, path: str) -> None:
        del path

    async def delete(self, path: str) -> None:
        self.files.pop(path, None)

    async def exists(self, path: str) -> bool:
        return path in self.files


async def _concat(scratchpad: _Workspace, **args: object) -> ToolMessage:
    tool = ConcatFilesMiddleware(scratchpad.port).tools[0]

    async def inline(operation: Any, *values: Any) -> Any:
        return operation(*values)

    with patch.object(asyncio, "to_thread", inline):
        result = await tool.ainvoke(
            {"type": "tool_call", "name": "concat_files", "args": args, "id": "concat"}
        )
    assert isinstance(result, ToolMessage)
    return result


@pytest.mark.asyncio
async def test_text_inputs_keep_order_and_whitespace_without_echoing_content() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("first.md", "  first\n")
    await scratchpad.write_text("second.md", "second  ")

    result = await _concat(
        scratchpad,
        paths=["/second.md", "/first.md"],
        output_path="/merged.md",
        join="exact",
    )

    assert result.status == "success"
    assert await scratchpad.read_text("merged.md") == "second    first\n"
    assert "/merged.md" in str(result.content)
    assert "second" not in str(result.content)


@pytest.mark.asyncio
async def test_mounted_input_keeps_exact_long_text_and_denies_mounted_output() -> None:
    workspace = _scratchpad()
    exact = "first\r\nsecond\rthird  " + "x" * 20000
    await workspace.write_text(".deep/artifact.txt", exact)

    success = await _concat(
        workspace,
        paths=["/.deep/artifact.txt"],
        output_path="/merged.txt",
    )
    assert success.status == "success"
    assert await workspace.read_text("merged.txt") == exact

    denied = await _concat(
        workspace,
        paths=["/.deep/artifact.txt"],
        output_path="/.deep/denied.txt",
    )
    assert getattr(denied.artifact, "is_error", False)
    assert "Permission denied" in str(denied.content)
    assert not await workspace.exists(".deep/denied.txt")
    assert (
        "conversations/conversation-a/scratchpad/.deep/denied.txt"
        not in workspace.storage.files
    )


@pytest.mark.asyncio
async def test_builtin_and_concat_share_one_virtual_workspace() -> None:
    workspace = _scratchpad()
    middleware = FilesystemMiddleware(
        backend=workspace.port.backend,
        _permissions=workspace.port.permissions,
    )
    tools = {entry.name: entry for entry in middleware.tools}
    runtime = cast(Any, SimpleNamespace(tool_call_id="shared-workspace"))

    written = await cast(Any, tools["write_file"]).coroutine(
        file_path="/built-in.txt", content="from builtin", runtime=runtime
    )
    assert written.status == "success"
    concatenated = await _concat(
        workspace, paths=["/built-in.txt"], output_path="/joined.txt"
    )
    assert concatenated.status == "success"
    read_back = await cast(Any, tools["read_file"]).coroutine(
        file_path="/joined.txt", runtime=runtime
    )
    assert read_back.status == "success"
    assert "from builtin" in str(read_back.content)


@pytest.mark.asyncio
async def test_markdown_headings_are_explicit_and_do_not_trim_bodies() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("part-one.md", "  Alpha\n")
    await scratchpad.write_text("part-two.md", "Beta  ")

    result = await _concat(
        scratchpad,
        paths=["/part-one.md", "/part-two.md"],
        output_path="/report.md",
        join="sections",
    )

    assert result.status == "success"
    assert await scratchpad.read_text("report.md") == (
        "## part one\n\n  Alpha\n\n## part two\n\nBeta  "
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "first_tail,second_head", [("", ""), ("\n", ""), ("\n\n", "\n")]
)
async def test_lines_join_continues_one_markdown_table(
    first_tail: str, second_head: str
) -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text(
        "first.md", f"| ID | Score |\n| --- | --- |\n| 1 | 8 |{first_tail}"
    )
    await scratchpad.write_text("second.md", f"{second_head}| 2 | 9 |")

    result = await _concat(
        scratchpad,
        paths=["/first.md", "/second.md"],
        output_path="/merged.md",
    )

    assert result.status == "success"
    assert await scratchpad.read_text("merged.md") == (
        "| ID | Score |\n| --- | --- |\n| 1 | 8 |\n| 2 | 9 |"
    )


@pytest.mark.asyncio
async def test_csv_rejects_sections_join() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("first.csv", "1,2")

    result = await _concat(
        scratchpad,
        paths=["/first.csv"],
        output_path="/merged.csv",
        join="sections",
    )

    assert getattr(result.artifact, "is_error", False)
    assert not await scratchpad.exists("merged.csv")


@pytest.mark.asyncio
async def test_csv_exact_join_preserves_input_boundaries() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("first.csv", "1,2")
    await scratchpad.write_text("second.csv", "3,4")

    result = await _concat(
        scratchpad,
        paths=["/first.csv", "/second.csv"],
        output_path="/merged.csv",
        join="exact",
    )

    assert result.status == "success"
    assert await scratchpad.read_text("merged.csv") == "1,23,4"


@pytest.mark.asyncio
async def test_existing_output_requires_explicit_replacement() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("part.md", "new")
    await scratchpad.write_text("report.md", "old")
    args = {
        "paths": ["/part.md"],
        "output_path": "/report.md",
    }

    refused = await _concat(scratchpad, **args)
    assert getattr(refused.artifact, "is_error", False)
    assert await scratchpad.read_text("report.md") == "old"

    replaced = await _concat(scratchpad, **args, replace=True)
    assert not getattr(replaced.artifact, "is_error", False)
    assert await scratchpad.read_text("report.md") == "new"


@pytest.mark.asyncio
async def test_output_cannot_replace_an_input_even_with_replace_enabled() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("part.md", "keep this")

    result = await _concat(
        scratchpad,
        paths=["/part.md"],
        output_path="/part.md",
        replace=True,
    )

    assert getattr(result.artifact, "is_error", False)
    assert await scratchpad.read_text("part.md") == "keep this"


@pytest.mark.asyncio
async def test_missing_later_input_never_creates_output() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("part.md", "ready")

    result = await _concat(
        scratchpad,
        paths=["/part.md", "/missing.md"],
        output_path="/report.md",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "missing.md" in str(result.content)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_invalid_path_cannot_escape_conversation() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("part.md", "ready")

    result = await _concat(
        scratchpad,
        paths=["/../.deep/secret.md"],
        output_path="/report.md",
    )

    assert getattr(result.artifact, "is_error", False)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_empty_inputs_cannot_create_a_misleading_deliverable() -> None:
    scratchpad = _scratchpad()

    result = await _concat(scratchpad, paths=[], output_path="/report.md")

    assert getattr(result.artifact, "is_error", False)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_csv_mode_preserves_quoted_records_and_adds_missing_boundary_newline() -> (
    None
):
    scratchpad = _scratchpad()
    await scratchpad.write_text("batch-1.csv", 'a,b\n1,"two, too"')
    await scratchpad.write_text("batch-2.csv", '3,"four\nfive"\n6,seven')

    result = await _concat(
        scratchpad,
        paths=["/batch-1.csv", "/batch-2.csv"],
        output_path="/merged.csv",
    )

    assert not getattr(result.artifact, "is_error", False)
    assert await scratchpad.read_text("merged.csv") == (
        'a,b\n1,"two, too"\n3,"four\nfive"\n6,seven'
    )


@pytest.mark.asyncio
async def test_csv_column_mismatch_reports_each_file_and_writes_nothing() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("batch-1.csv", "1,2\n3,4")
    await scratchpad.write_text("batch-2.csv", '5,"six,seven",8')

    result = await _concat(
        scratchpad,
        paths=["/batch-1.csv", "/batch-2.csv"],
        output_path="/merged.csv",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "batch-1.csv: 2" in str(result.content)
    assert "batch-2.csv: 3" in str(result.content)
    assert not await scratchpad.exists("merged.csv")


@pytest.mark.asyncio
async def test_csv_row_mismatch_in_one_batch_is_an_error() -> None:
    scratchpad = _scratchpad()
    await scratchpad.write_text("batch.csv", "1,2\n3,4,5")

    result = await _concat(
        scratchpad,
        paths=["/batch.csv"],
        output_path="/merged.csv",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "batch.csv: 2/3" in str(result.content)
    assert not await scratchpad.exists("merged.csv")
