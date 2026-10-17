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

"""Real permissive PDF extraction, page contracts and persisted UTF-8 output."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from reportlab.pdfgen import canvas

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import LitePdfMarkdownProcessor, LitePdfToMdProcessor


@pytest.fixture
def pdf(tmp_path: Path) -> Path:
    path = tmp_path / "pages.pdf"
    doc = canvas.Canvas(str(path))
    doc.setTitle("Airport report")
    doc.setAuthor("Fred")
    for number in range(1, 4):
        doc.drawString(40, 740, f"Page {number}: Gate A12 Flight 456 Ready")
        doc.showPage()
    doc.save()
    return path


@pytest.mark.parametrize(("selection", "numbers"), [(None, [1, 2, 3]), ((2, 3), [2, 3]), ((-2, 2), [1, 2]), ((99, 100), [3]), ((3, 1), [3])])
def test_source_page_numbers_and_clamped_ranges(pdf: Path, selection, numbers):
    result = LitePdfToMdProcessor().extract(pdf, LiteMarkdownOptions(page_range=selection))
    assert result.page_count == 3
    assert [page.page_no for page in result.pages] == numbers
    assert result.extras == {"engine": "pypdf-pagewise"}
    for page in result.pages:
        assert page.markdown.startswith(f"## Page {page.page_no}\n\n")
        assert f"Page {page.page_no}: Gate A12 Flight 456 Ready" in page.markdown
    assert result.total_chars == len(result.markdown)


def test_limits_keep_only_complete_page_records(pdf: Path):
    processor = LitePdfToMdProcessor()
    complete = processor.extract(pdf)
    limit = len(complete.pages[0].markdown) + 5
    limited = processor.extract(pdf, LiteMarkdownOptions(max_chars=limit))
    assert limited.truncated
    assert len(limited.markdown) <= limit + 2  # Shared truncation helper appends a newline and marker.
    assert [p.page_no for p in limited.pages] == [1]


def test_disable_page_headings_and_per_page_output(pdf: Path):
    result = LitePdfToMdProcessor().extract(pdf, LiteMarkdownOptions(page_range=(2, 2), add_page_headings=False, return_per_page=False))
    assert "## Page" not in result.markdown
    assert "Page 2:" in result.markdown
    assert not result.pages


def test_whole_document_markitdown(pdf: Path):
    result = LitePdfToMdProcessor().extract(pdf, LiteMarkdownOptions(add_page_headings=False, return_per_page=False))
    assert result.extras == {"engine": "markitdown"}
    assert "456" in result.markdown


def test_page_failure_never_becomes_whole_document(pdf: Path, monkeypatch):
    processor = LitePdfToMdProcessor()

    def fail(*args):
        raise ValueError("broken page")

    monkeypatch.setattr(processor, "_extract_pages_with_pypdf", fail)
    monkeypatch.setattr(processor, "_extract_with_markitdown", lambda *a: pytest.fail("Page structure would be lost"))
    with pytest.raises(ValueError, match="broken page"):
        processor.extract(pdf)


def test_whole_document_failure_can_fall_back_to_pypdf(pdf: Path, monkeypatch):
    processor = LitePdfToMdProcessor()
    monkeypatch.setattr(processor._md, "convert", lambda *a: SimpleNamespace(markdown=""))
    result = processor.extract(pdf, LiteMarkdownOptions(add_page_headings=False, return_per_page=False))
    assert result.extras == {"engine": "pypdf-pagewise"}
    assert "456" in result.markdown


def test_metadata_validity_and_output(pdf: Path, tmp_path: Path):
    processor = LitePdfMarkdownProcessor()
    assert processor.check_file_validity(pdf)
    metadata = processor.extract_file_metadata(pdf)
    assert metadata["page_count"] == 3
    assert metadata["title"] == "Airport report"
    assert metadata["author"] == "Fred"
    converted = processor.convert_file_to_markdown(pdf, tmp_path / "output", "doc-1")
    assert "## Page 3" in Path(converted["md_file"]).read_text(encoding="utf-8")
    invalid = tmp_path / "invalid.pdf"
    invalid.write_text("not a PDF")
    assert not processor.check_file_validity(invalid)


def test_surrogates_are_removed_without_optional_normalization():
    assert LitePdfToMdProcessor()._normalize("été" + chr(0xD800), LiteMarkdownOptions(normalize_whitespace=False)) == "été"


@pytest.mark.parametrize("missing_chars", [1, 2])
def test_truncation_marker_does_not_complete_a_source_page(pdf: Path, missing_chars: int):
    processor = LitePdfToMdProcessor()
    complete = processor.extract(pdf)
    limit = len(complete.pages[0].markdown) - missing_chars
    limited = processor.extract(pdf, LiteMarkdownOptions(max_chars=limit))
    assert limited.truncated
    assert limited.pages == []
