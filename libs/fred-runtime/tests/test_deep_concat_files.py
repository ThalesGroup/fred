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

"""Public concat tool behavior against the conversation scratchpad port."""

from __future__ import annotations

import pytest
from fred_core.filesystem.local_filesystem import LocalFilesystem
from fred_runtime.conversation_filesystem import ConversationFilesystemService
from fred_runtime.deep.concat_files import ConcatFilesMiddleware
from fred_sdk.contracts.runtime import ConversationScratchpadPort
from langchain_core.messages import ToolMessage


def _scratchpad(tmp_path: object) -> ConversationScratchpadPort:
    return ConversationFilesystemService(
        LocalFilesystem(str(tmp_path)), "conversation-a"
    ).scratchpad()


async def _concat(
    scratchpad: ConversationScratchpadPort, **args: object
) -> ToolMessage:
    tool = ConcatFilesMiddleware(scratchpad).tools[0]
    result = await tool.ainvoke(
        {"type": "tool_call", "name": "concat_files", "args": args, "id": "concat"}
    )
    assert isinstance(result, ToolMessage)
    return result


@pytest.mark.asyncio
async def test_text_inputs_keep_order_and_whitespace_without_echoing_content(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("first.md", "  first\n")
    await scratchpad.write_text("second.md", "second  ")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/second.md", "/scratchpad/first.md"],
        output_path="/scratchpad/merged.md",
    )

    assert result.status == "success"
    assert await scratchpad.read_text("merged.md") == "second    first\n"
    assert "/scratchpad/merged.md" in str(result.content)
    assert "second" not in str(result.content)


@pytest.mark.asyncio
async def test_markdown_headings_are_explicit_and_do_not_trim_bodies(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("part-one.md", "  Alpha\n")
    await scratchpad.write_text("part-two.md", "Beta  ")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/part-one.md", "/scratchpad/part-two.md"],
        output_path="/scratchpad/report.md",
        heading_per_file=True,
    )

    assert result.status == "success"
    assert await scratchpad.read_text("report.md") == (
        "## part one\n\n  Alpha\n\n\n## part two\n\nBeta  "
    )


@pytest.mark.asyncio
async def test_existing_output_requires_explicit_replacement(tmp_path: object) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("part.md", "new")
    await scratchpad.write_text("report.md", "old")
    args = {
        "paths": ["/scratchpad/part.md"],
        "output_path": "/scratchpad/report.md",
    }

    refused = await _concat(scratchpad, **args)
    assert getattr(refused.artifact, "is_error", False)
    assert await scratchpad.read_text("report.md") == "old"

    replaced = await _concat(scratchpad, **args, replace=True)
    assert not getattr(replaced.artifact, "is_error", False)
    assert await scratchpad.read_text("report.md") == "new"


@pytest.mark.asyncio
async def test_output_cannot_replace_an_input_even_with_replace_enabled(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("part.md", "keep this")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/part.md"],
        output_path="/scratchpad/part.md",
        replace=True,
    )

    assert getattr(result.artifact, "is_error", False)
    assert await scratchpad.read_text("part.md") == "keep this"


@pytest.mark.asyncio
async def test_missing_later_input_never_creates_output(tmp_path: object) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("part.md", "ready")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/part.md", "/scratchpad/missing.md"],
        output_path="/scratchpad/report.md",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "missing.md" in str(result.content)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_invalid_path_cannot_escape_conversation(tmp_path: object) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("part.md", "ready")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/../.deep/secret.md"],
        output_path="/scratchpad/report.md",
    )

    assert getattr(result.artifact, "is_error", False)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_empty_inputs_cannot_create_a_misleading_deliverable(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)

    result = await _concat(scratchpad, paths=[], output_path="/scratchpad/report.md")

    assert getattr(result.artifact, "is_error", False)
    assert not await scratchpad.exists("report.md")


@pytest.mark.asyncio
async def test_csv_mode_preserves_quoted_records_and_adds_missing_boundary_newline(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("batch-1.csv", 'a,b\n1,"two, too"')
    await scratchpad.write_text("batch-2.csv", '3,"four\nfive"\n6,seven')

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/batch-1.csv", "/scratchpad/batch-2.csv"],
        output_path="/scratchpad/merged.csv",
    )

    assert not getattr(result.artifact, "is_error", False)
    assert await scratchpad.read_text("merged.csv") == (
        'a,b\n1,"two, too"\n3,"four\nfive"\n6,seven'
    )


@pytest.mark.asyncio
async def test_csv_column_mismatch_reports_each_file_and_writes_nothing(
    tmp_path: object,
) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("batch-1.csv", "1,2\n3,4")
    await scratchpad.write_text("batch-2.csv", '5,"six,seven",8')

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/batch-1.csv", "/scratchpad/batch-2.csv"],
        output_path="/scratchpad/merged.csv",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "batch-1.csv: 2" in str(result.content)
    assert "batch-2.csv: 3" in str(result.content)
    assert not await scratchpad.exists("merged.csv")


@pytest.mark.asyncio
async def test_csv_row_mismatch_in_one_batch_is_an_error(tmp_path: object) -> None:
    scratchpad = _scratchpad(tmp_path)
    await scratchpad.write_text("batch.csv", "1,2\n3,4,5")

    result = await _concat(
        scratchpad,
        paths=["/scratchpad/batch.csv"],
        output_path="/scratchpad/merged.csv",
    )

    assert getattr(result.artifact, "is_error", False)
    assert "batch.csv: 2/3" in str(result.content)
    assert not await scratchpad.exists("merged.csv")
