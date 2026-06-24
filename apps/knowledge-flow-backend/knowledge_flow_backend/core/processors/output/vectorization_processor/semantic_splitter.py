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

import logging
import re
from typing import List, Tuple

from langchain_core.documents import Document
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from knowledge_flow_backend.core.stores.vector.base_text_splitter import BaseTextSplitter

logger = logging.getLogger(__name__)

_WS_CLASS = r"[ \t\r\n\u00A0]+"  # space, tabs, CR/LF, NBSP

# Marker shape used to protect tables across the pipeline. The PDF/DOCX
# processors emit numeric ids; here we use an "auto_" prefix so we never
# collide with annotations produced upstream.
_TABLE_START_RE = re.compile(r"^\s*<!--\s*TABLE_START:id=([^\s>]+?)\s*-->\s*$")
_TABLE_END_RE = re.compile(r"^\s*<!--\s*TABLE_END\s*-->\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _is_pipe_row(line: str) -> bool:
    s = line.strip()
    return "|" in s and not s.startswith("```") and not s.startswith("~~~")


def _is_pipe_separator(line: str) -> bool:
    """Markdown table separator: only `|`, `-`, `:`, whitespace; at least one of each
    `|` and `-`."""
    s = line.strip()
    if "|" not in s or "-" not in s:
        return False
    return all(ch in "|-: \t" for ch in s)


def _short(s: str, n: int = 160) -> str:
    """Short, visible snippet for logs (make whitespace visible)."""
    s = s.replace("\n", "⏎").replace("\r", "␍").replace("\t", "⟶")
    s = s.replace("\u00a0", "⍽")  # NBSP made visible
    return (s[:n] + "…") if len(s) > n else s


def _build_ws_tolerant_pattern(needle: str) -> str:
    """Turn needle into a regex: collapse any whitespace runs to [_WS_CLASS]+."""
    parts = []
    in_ws = False
    for ch in needle:
        # treat ordinary and non-breaking spaces as whitespace
        if ch in (" ", "\t", "\r", "\n", "\x0b", "\x0c", "\u00a0"):
            if not in_ws:
                parts.append(f"(?:{_WS_CLASS})")
                in_ws = True
        else:
            parts.append(re.escape(ch))
            in_ws = False
    return "".join(parts)


class SemanticSplitter(BaseTextSplitter):
    def __init__(self, chunk_size: int = 1500, chunk_overlap: int = 150, preserve_tables: bool = True):
        """
        Initializes the SemanticSplitter with specified chunk size and overlap.
        Args:
            chunk_size (int, optional): The maximum number of characters in each chunk. Defaults to 1500.
            chunk_overlap (int, optional): The number of overlapping characters between consecutive chunks. Defaults to 150.
            preserve_tables (bool, optional): If true, keep annotated markdown tables intact. Defaults to True.
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.preserve_tables = preserve_tables

    def _auto_annotate_unmarked_tables(self, text: str) -> str:
        """
        Detect plain (unannotated) Markdown pipe tables and wrap them with
        ``<!-- TABLE_START:id=auto_N --> ... <!-- TABLE_END -->`` markers so the
        rest of the splitter pipeline treats them as atomic blocks.

        Why:
            Issue #1645 — table rows must not be split across chunks. Upstream
            processors (DOCX, PDF) already annotate; ``.md`` / ``.txt`` and the
            lightweight processors do not. Doing the detection here means light,
            medium and rich ingestion modes all benefit without per-processor
            duplication.

        Detection rules (intentionally conservative):
            - skip pre-existing TABLE_START/TABLE_END blocks untouched
            - skip lines inside fenced code blocks (``` or ~~~)
            - a table starts on a pipe-row whose next non-empty line is a
              Markdown separator row (only ``|``, ``-``, ``:``, whitespace and
              at least one of ``|`` and ``-``)
            - the table extends through subsequent contiguous pipe-rows; a
              blank line ends it
        """
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        auto_idx = 0
        in_fence = False
        fence_token: str | None = None

        while i < len(lines):
            line = lines[i]
            stripped = line.lstrip()

            # Track fenced code blocks; pipes inside them are never tables.
            if _FENCE_RE.match(line):
                token = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_token = token
                elif token == fence_token:
                    in_fence = False
                    fence_token = None
                out.append(line)
                i += 1
                continue
            if in_fence:
                out.append(line)
                i += 1
                continue

            # Preserve existing annotations untouched.
            if _TABLE_START_RE.match(line):
                out.append(line)
                i += 1
                while i < len(lines):
                    out.append(lines[i])
                    if _TABLE_END_RE.match(lines[i]):
                        i += 1
                        break
                    i += 1
                continue

            # Pipe table: a pipe-row immediately followed by a separator row.
            if i + 1 < len(lines) and _is_pipe_row(line) and _is_pipe_separator(lines[i + 1]):
                start = i
                i += 2  # consume header + separator
                while i < len(lines) and lines[i].strip() and _is_pipe_row(lines[i]):
                    i += 1
                table_md = "\n".join(lines[start:i]).rstrip()
                if table_md:
                    out.append(f"<!-- TABLE_START:id=auto_{auto_idx} -->")
                    out.append(table_md)
                    out.append("<!-- TABLE_END -->")
                    auto_idx += 1
                continue

            out.append(line)
            i += 1

        # Preserve a single trailing newline if the original text had one.
        result = "\n".join(out)
        if text.endswith("\n") and not result.endswith("\n"):
            result += "\n"
        return result

    def _extract_and_replace_tables(self, text: str) -> Tuple[str, dict]:
        """
        Extracts annotated Markdown tables from the text and replaces them with unique placeholders.

        Matches tables marked with <!-- TABLE_START:id=... --> and <!-- TABLE_END -->, stores them
        in a dictionary, and replaces each with <<TABLE_id>> in the text.

        Args:
            text (str): Input text containing annotated Markdown tables.

        Returns:
            Tuple[str, dict]:
                - Modified text with table placeholders.
                - Dictionary mapping table IDs to their Markdown content.
        """
        pattern = r"<!-- TABLE_START:id=(.*?) -->\n(.*?)\n<!-- TABLE_END -->"
        table_map = {}

        def replacer(match):
            table_id, table_md = match.group(1), match.group(2)
            table_map[table_id] = table_md.strip()
            return f"<<TABLE_{table_id}>>"

        new_text = re.sub(pattern, replacer, text, flags=re.DOTALL)

        return new_text, table_map

    def _split_large_table(self, table_md: str, table_id: str) -> List[Document]:
        """
        Splits a large Markdown table into smaller chunks based on the configured chunk size.

        Preserves the table header + separator row in **every** chunk and stamps
        metadata so consumers can re-stitch the table or filter on
        ``block_type=='markdown_table'``. Row order is preserved.

        Args:
            table_md (str): The Markdown string of the full table.
            table_id (str): The unique identifier for the table.

        Returns:
            List[Document]: A list of Document objects, each containing a chunk of the original table.
        """
        lines = table_md.strip().split("\n")
        if len(lines) < 3:
            return [
                Document(
                    page_content=table_md,
                    metadata={
                        "is_table": True,
                        "block_type": "markdown_table",
                        "table_id": table_id,
                        "table_chunk_id": 0,
                        "table_part": 0,
                        "row_start": 0,
                        "row_end": max(len(lines) - 2, 0),
                    },
                )
            ]

        header = f"{lines[0]}\n{lines[1]}"
        rows = lines[2:]

        sub_tables: List[Document] = []
        current_rows: list[str] = []
        chunk_index = 0
        chunk_row_start = 0
        cursor = 0  # zero-based row index into ``rows``

        def _flush(end_exclusive: int) -> None:
            nonlocal chunk_index, chunk_row_start
            if not current_rows:
                return
            sub_tables.append(
                Document(
                    page_content=f"{header}\n{chr(10).join(current_rows)}",
                    metadata={
                        "is_table": True,
                        "block_type": "markdown_table",
                        "table_id": table_id,
                        "table_chunk_id": chunk_index,
                        "table_part": chunk_index,
                        "row_start": chunk_row_start,
                        "row_end": end_exclusive,
                    },
                )
            )
            chunk_index += 1
            chunk_row_start = end_exclusive

        for row in rows:
            projected = len(header) + 1 + len("\n".join(current_rows + [row]))
            if current_rows and projected > self.chunk_size:
                _flush(cursor)
                current_rows = [row]
            else:
                current_rows.append(row)
            cursor += 1

        _flush(cursor)
        return sub_tables

    def semantic_chunking(self, text: str) -> List[Document]:
        """
        Splits a Markdown document into semantically meaningful chunks with special handling for tables.

        Extracts tables and replaces them with placeholders, splits the text using Markdown headers
        and recursive chunking, then reinserts the tables (splitting large ones if needed).

        Args:
            text (str): The full Markdown text to be chunked.

        Returns:
            List[Document]: A list of Document chunks, including text sections and individual table chunks.
        """

        # 0. Auto-annotate plain Markdown tables that upstream processors did
        #    not wrap (e.g. ``.md``/``.txt`` ingestion and the lightweight
        #    PDF/DOCX/PPTX paths). Idempotent: existing markers are preserved.
        text = self._auto_annotate_unmarked_tables(text)

        # 1. Extract tables + replace with placeholder
        text_with_placeholders, table_map = self._extract_and_replace_tables(text)

        # 2. Split text according to Markdown headings
        markdown_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[
                ("#", "Header 1"),
                ("##", "Header 2"),
                ("###", "Header 3"),
                ("####", "Header 4"),
                ("#####", "Header 5"),
            ],
            strip_headers=False,
        )
        md_chunks = markdown_splitter.split_text(text_with_placeholders)

        # 3. Apply RecursiveCharacterTextSplitter if the chunk is too long
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap, separators=["\n\n", "\n", " ", ""])
        sub_chunks = []
        for chunk in md_chunks:
            if len(chunk.page_content) > self.chunk_size:
                sub_chunks.extend(text_splitter.split_documents([chunk]))
            else:
                sub_chunks.append(chunk)

        # ---- 3.5 Compute anchors (char_start/char_end) against the placeholder'd text ----
        total = len(sub_chunks)
        ok = 0
        used_fb = 0
        cursor = 0  # rolling pointer to prefer forward matches, helps with overlaps

        for i, c in enumerate(sub_chunks):
            txt = c.page_content or ""
            if not txt:
                logger.debug("chunk[%d]: empty content, skip anchoring", i)
                continue

            # First: exact search from rolling cursor, then global
            idx = text_with_placeholders.find(txt, cursor)
            fb = False
            if idx == -1:
                idx = text_with_placeholders.find(txt)
            # Fallback: whitespace-tolerant regex (NBSP/newlines/etc.)
            if idx == -1:
                pat = _build_ws_tolerant_pattern(txt)
                m = re.search(pat, text_with_placeholders[cursor:], flags=re.MULTILINE)
                if m:
                    idx = cursor + m.start()
                    fb = True

            if idx != -1:
                if c.metadata is None:
                    c.metadata = {}
                c.metadata["char_start"] = idx
                c.metadata["char_end"] = idx + len(txt)
                ok += 1
                used_fb += int(fb)

                # Advance cursor (respecting overlap)
                if self.chunk_overlap > 0:
                    cursor = max(idx + len(txt) - self.chunk_overlap, idx)
                else:
                    cursor = idx + len(txt)

                logger.debug("anchor ok  | chunk=%d len=%d idx=%d cursor->%d fallback=%s preview=%r", i, len(txt), idx, cursor, fb, _short(txt))
            else:
                # Diagnostics for misses
                window = text_with_placeholders[cursor : cursor + max(0, len(txt) + 200)]
                logger.debug("anchor miss| chunk=%d len=%d cursor=%d needle=%r haystack_win=%r", i, len(txt), cursor, _short(txt), _short(window))

        logger.info("Anchoring summary: %d/%d chunks anchored (fallback used on %d).", ok, total, used_fb)

        # 4. Reinsert tables — walk each chunk in text order so that content
        #    before a placeholder stays before the table and content after it
        #    stays after. The previous implementation stripped all placeholders
        #    at once and emitted tables in a batch at the end, which collapsed
        #    surrounding text into one merged chunk and placed every table after
        #    it, breaking document order (issue #1645 regression).
        final_chunks = []
        _placeholder_re = re.compile(r"<<TABLE_(.*?)>>")

        for chunk in sub_chunks:
            chunk_text = chunk.page_content

            if "<<TABLE_" not in chunk_text:
                final_chunks.append(chunk)
                continue

            prev_end = 0
            for m in _placeholder_re.finditer(chunk_text):
                before = chunk_text[prev_end : m.start()].strip()
                if before:
                    final_chunks.append(
                        Document(
                            page_content=before,
                            metadata=dict(chunk.metadata or {}),
                        )
                    )

                table_id = m.group(1)
                table_md = table_map.get(table_id, "")
                if table_md:
                    if len(table_md) <= self.chunk_size:
                        final_chunks.append(
                            Document(
                                page_content=table_md,
                                metadata={
                                    "is_table": True,
                                    "block_type": "markdown_table",
                                    "table_id": table_id,
                                    "table_chunk_id": 0,
                                    "table_part": 0,
                                },
                            )
                        )
                    else:
                        final_chunks.extend(self._split_large_table(table_md, table_id))

                prev_end = m.end()

            tail = chunk_text[prev_end:].strip()
            if tail:
                final_chunks.append(
                    Document(
                        page_content=tail,
                        metadata=dict(chunk.metadata or {}),
                    )
                )

        return final_chunks

    def split(self, document: Document) -> List[Document]:
        """
        Splits a document into semantically meaningful chunks and enriches metadata.

        Applies semantic chunking to the document content and adds metadata such as
        original document length and chunk index to each resulting chunk.

        Args:
            document (Document): The input document to split.

        Returns:
            List[Document]: A list of semantically chunked Document objects with enriched metadata.
        """
        semantic_chunks = self.semantic_chunking(document.page_content)
        base_metadata = document.metadata.copy()
        base_metadata["original_doc_length"] = len(document.page_content)

        for chunk_id, chunk in enumerate(semantic_chunks):
            chunk.metadata.update({**base_metadata, "chunk_id": chunk_id})

        return semantic_chunks
