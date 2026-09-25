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

from fred_sdk.contracts.context import ToolInvocationResult
from fred_sdk.contracts.runtime import (
    ConversationFilesystemPort,
    ConversationScratchpadError,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, tool

_TOOL_REF = "runtime:concat_files"


class ConcatFilesMiddleware(AgentMiddleware):
    """Expose one conversation-bound tool to a Deep parent or native child."""

    def __init__(self, filesystem: ConversationFilesystemPort) -> None:
        super().__init__()

        @tool("concat_files", response_format="content_and_artifact")
        async def concat_files(
            paths: list[str],
            output_path: str,
            heading_per_file: bool = False,
            replace: bool = False,
        ) -> tuple[str, ToolInvocationResult]:
            """Concatenate ordered workspace text files into an output file.

            Use absolute paths such as `/notes.md`. The output contains the exact
            input text in the specified order, with no inserted separators.
            Set heading_per_file for Markdown `##` headings derived from input
            filenames, with blank lines between sections. When every input is
            `.csv`, write headerless CSV batches: quoted fields are respected,
            all records must have the same column count, and a missing newline
            is added between batches. Tell sub-agents not to write CSV headers.
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
                merged = await asyncio.to_thread(
                    _assemble, paths, contents, heading_per_file
                )
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


def _join_csv_files(contents: list[str]) -> str:
    pieces: list[str] = []
    for content in contents:
        if pieces and pieces[-1] and not pieces[-1].endswith(("\r", "\n")):
            pieces.append("\n")
        pieces.append(content)
    return "".join(pieces)


def _assemble(
    paths: list[str],
    contents: list[str],
    heading_per_file: bool,
) -> str:
    if all(path.lower().endswith(".csv") for path in paths):
        if heading_per_file:
            raise ValueError("Markdown headings cannot be added to CSV output")
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
        return _join_csv_files(contents)
    if heading_per_file:
        return "\n\n".join(
            f"## {_heading(path)}\n\n{body}"
            for path, body in zip(paths, contents, strict=True)
        )
    return "".join(contents)
