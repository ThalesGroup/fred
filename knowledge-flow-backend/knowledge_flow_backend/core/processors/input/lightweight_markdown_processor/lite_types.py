from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class LiteMarkdownOptions:
    """
    Options to control the lightweight extraction.

    - include_tables: include simple pipe tables (truncated to limits)
    - max_table_rows/max_table_cols: truncation for tables
    - include_images: placeholder-only; current extractors skip image rendering
    - page_range: zero- or one-based inclusive page selection depending on format
    - max_chars: hard cap of output size (post-assembly)
    - normalize_whitespace: collapse multiple spaces/newlines
    - add_page_headings: add '## Page N' markers (PDF only)
    - return_per_page: include per-page payloads when applicable
    - trim_empty_lines: remove leading/trailing blank lines per block
    """

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


@dataclass
class LitePageMarkdown:
    page_no: int
    markdown: str
    char_count: int


@dataclass
class LiteMarkdownResult:
    document_name: str
    page_count: Optional[int]
    total_chars: int
    truncated: bool
    markdown: str
    pages: List[LitePageMarkdown] = field(default_factory=list)
    extras: dict = field(default_factory=dict)


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
