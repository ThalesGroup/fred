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

"""Regression tests for the fitz.Document lifecycle in LitePdfToMdExtractor.

This is the extractor wired to the `fast` ingestion profile in production
(see deploy/charts/fred/values.yaml, x-fast-input-processors). pymupdf4llm's
to_markdown() opens its own fitz.Document when given a path and never closes
it, so the extractor must open the document itself and close it explicitly —
otherwise every ingested PDF leaks native MuPDF memory (pages, xref table)
that accumulates across ingestion batches until the worker pod OOMs.
"""

from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite2_pdf_to_md_processor import (
    LitePdfMarkdownProcessor,
    LitePdfToMdExtractor,
)
from tests.processors.input.lightweight_markdown_processor.conftest import FitzOpenSpy


def test_extract_pymupdf4llm_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path):
    extractor = LitePdfToMdExtractor()
    result = extractor.extract(sample_pdf_file)

    assert result.markdown
    assert result.extras == {"engine": "pymupdf4llm"}
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_extract_pymupdf4llm_closes_the_document_even_on_failure(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite2_pdf_to_md_processor.pymupdf4llm.to_markdown",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    extractor = LitePdfToMdExtractor()
    # extract() catches the primary-engine failure and falls back to markitdown,
    # so it won't raise — but the leaked/closed state of the fitz.Document from
    # the failed pymupdf4llm attempt is exactly what we're checking here.
    extractor.extract(sample_pdf_file)

    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_processor_check_file_validity_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path):
    processor = LitePdfMarkdownProcessor()
    assert processor.check_file_validity(sample_pdf_file) is True
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed


def test_processor_extract_file_metadata_closes_the_document(fitz_open_spy: FitzOpenSpy, sample_pdf_file: Path):
    processor = LitePdfMarkdownProcessor()
    metadata = processor.extract_file_metadata(sample_pdf_file)

    assert metadata["page_count"] >= 1
    assert len(fitz_open_spy.opened) == 1
    assert fitz_open_spy.opened[0].is_closed
