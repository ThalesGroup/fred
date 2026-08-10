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

"""Regression tests for the fitz.Document lifecycle in LitePdfToMdProcessor /
LitePdfMarkdownProcessor (the deprecated "v1" lite PDF path, still part of
`lightweight_markdown_processor`). All three methods used to open a
fitz.Document via fitz.open() and never call .close() on it.
"""

from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownOptions
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pdf_to_md_processor import (
    LitePdfMarkdownProcessor,
    LitePdfToMdProcessor,
)
from tests.processors.input.lightweight_markdown_processor.conftest import FitzOpenSpy


@pytest.fixture
def processor() -> LitePdfToMdProcessor:
    with pytest.deprecated_call():
        return LitePdfToMdProcessor()


def test_extract_pages_with_fitz_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path, processor: LitePdfToMdProcessor):
    result = processor._extract_pages_with_fitz(sample_pdf_file, LiteMarkdownOptions(add_page_headings=True))

    assert result.markdown
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_extract_pages_with_fitz_closes_the_document_even_on_failure(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path, processor: LitePdfToMdProcessor, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(processor, "_safe_page_range", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        processor._extract_pages_with_fitz(sample_pdf_file, LiteMarkdownOptions())

    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_check_file_validity_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path):
    with pytest.deprecated_call():
        markdown_processor = LitePdfMarkdownProcessor()

    assert markdown_processor.check_file_validity(sample_pdf_file) is True
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_extract_file_metadata_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path):
    with pytest.deprecated_call():
        markdown_processor = LitePdfMarkdownProcessor()

    metadata = markdown_processor.extract_file_metadata(sample_pdf_file)

    assert metadata["page_count"] >= 1
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed
