# Copyright Thales 2025
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

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class FastPageText:
    page_no: int
    text: str
    char_count: int


@dataclass
class FastTextResult:
    document_name: str
    page_count: Optional[int]
    total_chars: int
    truncated: bool
    text: str
    pages: List[FastPageText] = field(default_factory=list)
    extras: dict = field(default_factory=dict)


@dataclass
class FastTextOptions:
    include_tables: bool = True
    max_table_rows: int = 20
    max_table_cols: int = 10
    include_images: bool = False
    page_range: Optional[Tuple[int, int]] = None  # inclusive (1-based for PDF)
    max_chars: Optional[int] = 60_000
    normalize_whitespace: bool = True
    add_page_headings: bool = True
    return_per_page: bool = True
    trim_empty_lines: bool = True
    fast: bool = False


def enforce_max_chars(text: str, max_chars: Optional[int]) -> tuple[str, bool]:
    if max_chars is None or max_chars <= 0:
        return text, False
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars].rstrip() + "\n…", True


def collapse_whitespace(text: str) -> str:
    """Conservative whitespace normalization.
    - Replace Windows newlines
    - Collapse 3+ newlines to 2
    - Strip trailing spaces per line
    """
    if not text:
        return text
    # Normalize newlines
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Strip trailing spaces per line
    t = "\n".join(line.rstrip() for line in t.split("\n"))
    # Collapse excessive blank lines
    while "\n\n\n" in t:
        t = t.replace("\n\n\n", "\n\n")
    return t


def trim_empty_lines(text: str) -> str:
    if not text:
        return text
    lines = text.split("\n")
    start = 0
    end = len(lines) - 1
    while start <= end and not lines[start].strip():
        start += 1
    while end >= start and not lines[end].strip():
        end -= 1
    if start > end:
        return ""
    return "\n".join(lines[start : end + 1])


class BaseFastTextProcessor(ABC):
    """
    Base interface for all fast text processors. These
    processors extract various file types into text format with minimal
    dependencies and resource usage.

    A typical usage is to generate a text representation of a file's
    content to be attached to a conversation or document in Fred, without
    the overhead of full parsing or indexing.

    All subclasses must implement the 'extract' method, which takes
    a file path and options, and returns a BaseFastTextResult.
    """

    @abstractmethod
    def extract(self, file_path: Path, options: FastTextOptions | None = None) -> FastTextResult:
        """
        Extracts content from a file and returns it as a LiteMarkdownResult.

        :param file_path: The Path object pointing to the file.
        :param options: Configuration options for extraction (e.g., max chars/rows).
        :return: A LiteMarkdownResult containing the Markdown string and metadata.
        """
        pass
