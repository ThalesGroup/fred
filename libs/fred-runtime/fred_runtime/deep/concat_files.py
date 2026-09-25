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

"""Deterministic Deep file assembly through Fred's virtual filesystem port."""

from __future__ import annotations

import asyncio
import csv
import io
from collections.abc import Sequence
from pathlib import PurePosixPath
from typing import Literal

from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPort,
    ConversationScratchpadError,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool

_TOOL_REF = "runtime:concat_files"
JoinMode = Literal["exact", "lines", "sections"]


class ConcatFilesMiddleware(AgentMiddleware):
    """Expose one conversation-bound tool to a Deep parent or native child."""

    def __init__(self, filesystem: ConversationFilesystemPort) -> None:
        super().__init__()

        @tool("concat_files", response_format="content_and_artifact")
        async def concat_files(
            paths: list[str],
            output_path: str,
            join: JoinMode = "lines",
            replace: bool = False,
        ) -> tuple[str, ToolInvocationResult]:
            """Concatenate ordered workspace text files into an output file.

            Use absolute paths such as `/notes.md`.

            Join modes:
            - "lines" (default): ensure exactly one newline between files.
            - "exact": preserve input text unchanged.
            - "sections": add filename-based Markdown `##` headings and blank
              lines between files.

            When every input is `.csv`, quoted fields are respected, all records
            must have the same column count, and "sections" is unavailable.
            CSV inputs should omit repeated headers.

            Set replace=True to overwrite an existing output. The result is a
            bounded summary, not the merged content.
            """
            if not paths:
                return _error("concat_files needs at least one input path.")
            if output_path in paths:
                return _error("Output path must differ from every input path.")
            try:
                if not replace and await filesystem.exists(output_path, origin="agent"):
                    return _error(f"Output already exists: {output_path}.")
                contents = []
                for path in paths:
                    try:
                        contents.append(
                            await filesystem.read_text(path, origin="agent")
                        )
                    except ConversationScratchpadError as exc:
                        return _error(f"Cannot read {path}: {exc}")
                merged = await asyncio.to_thread(_assemble, paths, contents, join)
                await filesystem.write_text(output_path, merged, origin="agent")
            except (ConversationScratchpadError, ValueError) as exc:
                return _error(f"Cannot concatenate files: {exc}")
            return (
                f"Concatenated {len(paths)} file(s) into {output_path}.",
                ToolInvocationResult(tool_ref=_TOOL_REF),
            )

        self.tools: Sequence[BaseTool] = [concat_files]


def _error(message: str) -> tuple[str, ToolInvocationResult]:
    return message, ToolInvocationResult(tool_ref=_TOOL_REF, is_error=True)


def _heading(path: str) -> str:
    return PurePosixPath(path).stem.replace("_", " ").replace("-", " ")


def _join_lines(contents: list[str], newline_count: int) -> str:
    if not contents:
        return ""
    merged = contents[0]
    for content in contents[1:]:
        merged = merged.rstrip("\r\n") + "\n" * newline_count + content.lstrip("\r\n")
    return merged


def _assemble(
    paths: list[str],
    contents: list[str],
    join: JoinMode,
) -> str:
    if all(path.lower().endswith(".csv") for path in paths):
        if join == "sections":
            raise ValueError("CSV inputs do not support join='sections'")
        counts: list[tuple[int, ...]] = []
        for path, content in zip(paths, contents, strict=True):
            try:
                widths = {
                    len(row) for row in csv.reader(io.StringIO(content), strict=True)
                }
            except csv.Error as exc:
                raise ValueError(f"Invalid CSV in {path}: {exc}") from exc
            counts.append(tuple(sorted(widths)) if widths else (0,))
        if any(len(widths) != 1 or widths[0] != counts[0][0] for widths in counts):
            details = ", ".join(
                f"{path}: {'/'.join(map(str, widths))} columns"
                for path, widths in zip(paths, counts, strict=True)
            )
            raise ValueError(f"CSV column count mismatch: {details}")
    if join == "sections":
        return _join_lines(
            [
                f"## {_heading(path)}\n\n{body}"
                for path, body in zip(paths, contents, strict=True)
            ],
            2,
        )
    if join == "lines":
        return _join_lines(contents, 1)
    if join == "exact":
        return "".join(contents)
    raise ValueError(f"Unknown join mode: {join}")
