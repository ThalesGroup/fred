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

"""Regression tests for issue #1645 — Markdown tables must be preserved as a
whole during ingestion across light/medium/rich modes.

The three ingestion modes share the same chunker (``SemanticSplitter``), so
covering it here covers all three.
"""

from langchain_core.documents import Document

from knowledge_flow_backend.core.processors.output.vectorization_processor.semantic_splitter import (
    SemanticSplitter,
)

SMALL_TABLE = (
    "| col1 | col2 | col3 |\n"
    "| --- | --- | --- |\n"
    "| a | b | c |\n"
    "| d | e | f |\n"
)


def _table_chunks(chunks):
    return [c for c in chunks if c.metadata.get("block_type") == "markdown_table"]


def _non_table_chunks(chunks):
    return [c for c in chunks if c.metadata.get("block_type") != "markdown_table"]


def test_small_table_remains_in_one_chunk():
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    doc = Document(page_content=f"# Heading\n\n{SMALL_TABLE}\n")
    chunks = splitter.split(doc)

    tables = _table_chunks(chunks)
    assert len(tables) == 1
    assert tables[0].page_content.strip() == SMALL_TABLE.strip()
    assert tables[0].metadata.get("is_table") is True
    assert tables[0].metadata.get("table_id")  # id was assigned


def test_text_before_and_after_table_chunked_separately():
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    text = (
        "# Heading\n\n"
        "Paragraph before the table.\n\n"
        f"{SMALL_TABLE}\n"
        "Paragraph after the table.\n"
    )
    chunks = splitter.split(Document(page_content=text))

    tables = _table_chunks(chunks)
    assert len(tables) == 1
    assert "| col1 | col2 | col3 |" in tables[0].page_content

    non_tables = _non_table_chunks(chunks)
    joined = "\n".join(c.page_content for c in non_tables)
    assert "Paragraph before the table." in joined
    assert "Paragraph after the table." in joined
    # The table marker placeholders must never leak into produced chunks.
    for c in chunks:
        assert "<<TABLE_" not in c.page_content
        assert "TABLE_START" not in c.page_content
        assert "TABLE_END" not in c.page_content


def _build_large_table(num_rows: int, cols: int = 3) -> str:
    header = "| " + " | ".join(f"col{i}" for i in range(cols)) + " |"
    sep = "| " + " | ".join("---" for _ in range(cols)) + " |"
    rows = []
    for r in range(num_rows):
        rows.append("| " + " | ".join(f"r{r}c{i}" for i in range(cols)) + " |")
    return "\n".join([header, sep, *rows]) + "\n"


def test_large_table_splits_only_on_row_boundaries_and_repeats_header():
    big_table = _build_large_table(num_rows=80, cols=4)
    splitter = SemanticSplitter(chunk_size=400, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=big_table))

    tables = _table_chunks(chunks)
    assert len(tables) > 1, "Large table must split into multiple parts"

    seen_rows: list[str] = []
    for idx, t in enumerate(tables):
        lines = t.page_content.splitlines()
        # Header + separator must repeat in EVERY part.
        assert lines[0].startswith("| col0 | col1 | col2 | col3 |"), f"part {idx} missing header"
        assert lines[1].startswith("| --- | --- | --- | --- |"), f"part {idx} missing separator"
        # Subsequent lines must each be a complete pipe row (no row was split mid-way).
        for line in lines[2:]:
            assert line.startswith("| r"), f"part {idx} has a non-row line: {line!r}"
            assert line.endswith("|"), f"part {idx} has a truncated row: {line!r}"
            seen_rows.append(line)
        # Metadata identifies the part and its row range.
        assert t.metadata["table_part"] == idx
        assert t.metadata["row_start"] < t.metadata["row_end"]

    # All 80 rows must be present in original order across parts.
    expected_rows = [line for line in big_table.splitlines()[2:] if line.strip()]
    assert seen_rows == expected_rows


def test_multiple_tables_are_each_preserved_independently():
    text = (
        "# Tables\n\n"
        f"{SMALL_TABLE}\n"
        "Some prose between the two tables.\n\n"
        f"{SMALL_TABLE}\n"
    )
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=text))

    tables = _table_chunks(chunks)
    assert len(tables) == 2
    ids = {t.metadata["table_id"] for t in tables}
    assert len(ids) == 2  # distinct ids for distinct tables
    for t in tables:
        assert t.page_content.strip() == SMALL_TABLE.strip()


def test_pipe_text_without_separator_row_is_not_treated_as_table():
    # Lines containing pipes that are NOT a markdown table must stay as prose
    # and never be wrapped or chunk-protected as a table.
    text = (
        "# Notes\n\n"
        "Use the command `foo | bar` to pipe output.\n"
        "Another sentence | with an embedded pipe character.\n"
        "And one more line.\n"
    )
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=text))

    tables = _table_chunks(chunks)
    assert tables == []


def test_fenced_code_block_with_pipes_is_not_treated_as_table():
    text = (
        "# Snippet\n\n"
        "```\n"
        "| a | b |\n"
        "| --- | --- |\n"
        "| 1 | 2 |\n"
        "```\n"
        "Following prose.\n"
    )
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=text))

    assert _table_chunks(chunks) == []
    # Code fence content must still appear in some chunk.
    joined = "\n".join(c.page_content for c in chunks)
    assert "| --- | --- |" in joined


def test_pre_annotated_tables_are_idempotent():
    annotated = (
        "<!-- TABLE_START:id=docx_1 -->\n"
        f"{SMALL_TABLE.rstrip()}\n"
        "<!-- TABLE_END -->\n"
    )
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=annotated))

    tables = _table_chunks(chunks)
    assert len(tables) == 1
    assert tables[0].metadata["table_id"] == "docx_1"
    assert tables[0].page_content.strip() == SMALL_TABLE.strip()


def test_auto_annotation_does_not_misdetect_separator_inside_text():
    # A line of pipes followed by something that *looks* like a separator
    # but is missing a pipe — must not be detected.
    text = (
        "# Notes\n\n"
        "Some line | with pipes\n"
        "----------- (no pipes here, so not a separator row)\n"
        "Another line.\n"
    )
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=text))
    assert _table_chunks(chunks) == []


def test_split_preserves_row_order_in_metadata():
    big_table = _build_large_table(num_rows=40, cols=3)
    splitter = SemanticSplitter(chunk_size=300, chunk_overlap=0)
    chunks = splitter.split(Document(page_content=big_table))
    tables = _table_chunks(chunks)
    assert len(tables) >= 2

    # row_start ranges must be monotonically increasing and contiguous.
    prev_end = 0
    for t in tables:
        assert t.metadata["row_start"] == prev_end
        assert t.metadata["row_end"] > t.metadata["row_start"]
        prev_end = t.metadata["row_end"]
    # Last part covers up to the last data row (40 rows total).
    assert prev_end == 40


# ---------------------------------------------------------------------------
# Order-preservation tests (regression for issue #1645 post-fix regression)
# ---------------------------------------------------------------------------


def _chunk_contents(chunks):
    return [c.page_content for c in chunks]


def test_chunk_order_text_before_table_then_text_after():
    """Content before a table must appear before the table chunk, not after."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    text = (
        "# Section\n\n"
        "Paragraph before.\n\n"
        f"{SMALL_TABLE}\n"
        "Paragraph after.\n"
    )
    chunks = splitter.split(Document(page_content=text))

    # Locate the single table chunk and check its position in the list.
    table_positions = [i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"]
    assert len(table_positions) == 1, "Expected exactly one table chunk"
    table_pos = table_positions[0]

    # The chunk containing "before" must come before the table.
    before_positions = [i for i, c in enumerate(chunks) if "Paragraph before." in c.page_content]
    assert before_positions, "Paragraph before not found in any chunk"
    assert before_positions[0] < table_pos, "Text before table must precede the table chunk"

    # The chunk containing "after" must come after the table.
    after_positions = [i for i, c in enumerate(chunks) if "Paragraph after." in c.page_content]
    assert after_positions, "Paragraph after not found in any chunk"
    assert after_positions[0] > table_pos, "Text after table must follow the table chunk"


def test_chunk_order_multiple_tables_interleaved_text():
    """With two tables, prose between them must sit between the two table chunks."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    text = (
        "# Doc\n\n"
        f"{SMALL_TABLE}\n"
        "Middle prose.\n\n"
        f"{SMALL_TABLE}\n"
        "Trailing prose.\n"
    )
    chunks = splitter.split(Document(page_content=text))

    table_positions = [i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"]
    assert len(table_positions) == 2, "Expected two table chunks"

    middle_positions = [i for i, c in enumerate(chunks) if "Middle prose." in c.page_content]
    assert middle_positions, "Middle prose not found in any chunk"
    # Middle prose must sit between the two tables.
    assert table_positions[0] < middle_positions[0] < table_positions[1], (
        "Middle prose must appear between the two table chunks"
    )

    trailing_positions = [i for i, c in enumerate(chunks) if "Trailing prose." in c.page_content]
    assert trailing_positions, "Trailing prose not found in any chunk"
    assert trailing_positions[0] > table_positions[1], "Trailing prose must follow the second table chunk"


def test_heading_paragraph_table_paragraph_document_order():
    """Full heading → paragraph → table → paragraph sequence preserves order."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    text = (
        "# Title\n\n"
        "Introduction paragraph.\n\n"
        f"{SMALL_TABLE}\n"
        "Conclusion paragraph.\n"
    )
    chunks = splitter.split(Document(page_content=text))

    contents = _chunk_contents(chunks)
    table_idx = next((i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"), None)
    assert table_idx is not None

    intro_idx = next((i for i, c in enumerate(chunks) if "Introduction paragraph." in c.page_content), None)
    concl_idx = next((i for i, c in enumerate(chunks) if "Conclusion paragraph." in c.page_content), None)

    assert intro_idx is not None, "Introduction paragraph missing"
    assert concl_idx is not None, "Conclusion paragraph missing"
    assert intro_idx < table_idx < concl_idx, (
        f"Expected intro({intro_idx}) < table({table_idx}) < conclusion({concl_idx})"
    )
    # No placeholder artefacts in any chunk.
    for c in chunks:
        assert "<<TABLE_" not in c.page_content
        assert "TABLE_START" not in c.page_content


def test_table_followed_by_list_preserves_order():
    """A table immediately followed by a bullet list keeps list after table."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    text = (
        "# List after table\n\n"
        f"{SMALL_TABLE}\n"
        "- item one\n"
        "- item two\n"
        "- item three\n"
    )
    chunks = splitter.split(Document(page_content=text))

    table_idx = next((i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"), None)
    assert table_idx is not None

    list_idx = next((i for i, c in enumerate(chunks) if "item one" in c.page_content), None)
    assert list_idx is not None, "List content missing from chunks"
    assert list_idx > table_idx, "List must appear after the table chunk"


def test_large_table_crossing_chunk_boundary_order_with_surrounding_text():
    """A large table surrounded by text splits across chunk boundaries but
    surrounding text retains correct relative order."""
    splitter = SemanticSplitter(chunk_size=400, chunk_overlap=0)
    big_table = _build_large_table(num_rows=30, cols=3)
    text = f"Header prose.\n\n{big_table}\nFooter prose.\n"
    chunks = splitter.split(Document(page_content=text))

    table_indices = [i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"]
    assert len(table_indices) > 1, "Large table must split into multiple parts"

    header_idx = next((i for i, c in enumerate(chunks) if "Header prose." in c.page_content), None)
    footer_idx = next((i for i, c in enumerate(chunks) if "Footer prose." in c.page_content), None)

    assert header_idx is not None, "Header prose missing"
    assert footer_idx is not None, "Footer prose missing"
    assert header_idx < table_indices[0], "Header must precede all table parts"
    assert footer_idx > table_indices[-1], "Footer must follow all table parts"


# ---------------------------------------------------------------------------
# Issue #1774 — large production table (200 rows)
# ---------------------------------------------------------------------------

_200_ROW_TABLE_COLS = 9  # matches large-table-test_pd1.md schema


def _build_200_row_table() -> str:
    """Reproduce the shape of large-table-test_pd1.md (200 rows, 9 cols,
    realistic description lengths) so the splitter is tested at production scale."""
    header = "| Property | Type | Required | Default | Category | Environment | Version | Example | Description |"
    sep = "|-----------|--------|----------|---------|----------|-------------|---------|---------|-------------|"
    rows = []
    for i in range(1, 201):
        prop = f"property{i:02d}"
        desc = f"Description for {prop} used in integration and validation pipelines."
        rows.append(f"| {prop} | string | Yes | value{i:02d} | Core | DEV | 1.0 | sample{i:02d} | {desc} |")
    return "\n".join([header, sep, *rows]) + "\n"


def test_200_row_table_produces_multiple_chunks_all_rows_present():
    """A 200-row production-scale table must be split into multiple chunks,
    every row must appear exactly once, and no placeholder artefacts may leak."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    big_table = _build_200_row_table()
    doc = Document(page_content=big_table)
    chunks = splitter.split(doc)

    tables = _table_chunks(chunks)
    assert len(tables) > 1, "200-row table must produce multiple table chunks"

    # Collect every data row seen across all table chunks.
    all_rows: list[str] = []
    for t in tables:
        lines = t.page_content.splitlines()
        # First two lines must be header + separator in EVERY chunk.
        assert lines[0].startswith("| Property |"), f"header missing in chunk: {lines[0]!r}"
        assert lines[1].startswith("|---"), f"separator missing in chunk: {lines[1]!r}"
        all_rows.extend(lines[2:])

    expected_rows = [line for line in big_table.splitlines()[2:] if line.strip()]
    assert all_rows == expected_rows, "All 200 rows must appear in original order across chunks"

    # No placeholder leakage.
    for c in chunks:
        assert "<<TABLE_" not in c.page_content
        assert "TABLE_START" not in c.page_content


def test_200_row_table_chunk_id_is_sequential_and_monotonic():
    """chunk_id assigned by split() must be a strict 0-based sequence so
    downstream vectorization can derive chunk_index correctly."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    doc = Document(page_content=_build_200_row_table())
    chunks = splitter.split(doc)

    ids = [c.metadata.get("chunk_id") for c in chunks]
    assert ids == list(range(len(chunks))), "chunk_id must be 0-based sequential across all chunks"

    table_chunks = _table_chunks(chunks)
    table_ids = [c.metadata.get("chunk_id") for c in table_chunks]
    assert table_ids == sorted(table_ids), "Table chunks must appear in document order (ascending chunk_id)"


def test_200_row_table_with_intro_text_preserves_document_order():
    """When a 200-row table is preceded by a heading and intro paragraph,
    the intro text must come before all table chunks in the chunk list."""
    splitter = SemanticSplitter(chunk_size=1500, chunk_overlap=0)
    intro = "# Large Configuration Reference\n\nThis document is used to test markdown table ingestion.\n\n"
    doc = Document(page_content=intro + _build_200_row_table())
    chunks = splitter.split(doc)

    table_indices = [i for i, c in enumerate(chunks) if c.metadata.get("block_type") == "markdown_table"]
    intro_indices = [i for i, c in enumerate(chunks) if "Large Configuration Reference" in c.page_content]

    assert table_indices, "Table chunks must exist"
    assert intro_indices, "Intro chunk must exist"
    assert intro_indices[0] < table_indices[0], "Intro text must precede all table chunks"

    table_ids = [chunks[i].metadata.get("chunk_id") for i in table_indices]
    assert table_ids == sorted(table_ids), "Table chunks must be in ascending chunk_id order"
