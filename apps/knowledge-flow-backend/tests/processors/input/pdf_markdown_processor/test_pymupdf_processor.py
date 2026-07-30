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

"""Regression tests for the fitz.Document lifecycle in PyMuPdfExtractor.

pymupdf4llm.to_markdown() opens its own fitz.Document when given a path and
never closes it, so PyMuPdfExtractor must open the document itself and close
it explicitly — otherwise every PDF processed with the `pymupdf` extractor
(medium/rich profile) leaks native MuPDF memory that accumulates across
ingestion batches until the worker pod OOMs.
"""

from pathlib import Path

import fitz
import pytest

from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pymupdf_processor import PyMuPdfExtractor


@pytest.fixture
def sample_pdf_file() -> Path:
    return Path(__file__).parent / "assets" / "sample.pdf"


@pytest.fixture
def fitz_open_spy(monkeypatch: pytest.MonkeyPatch):
    opened: list[fitz.Document] = []
    real_open = fitz.open

    def spy_open(*args, **kwargs):
        doc = real_open(*args, **kwargs)
        opened.append(doc)
        return doc

    monkeypatch.setattr(fitz, "open", spy_open)
    return opened


def test_extract_closes_the_document(fitz_open_spy: list, sample_pdf_file: Path, tmp_path: Path):
    extractor = PyMuPdfExtractor()
    md_text, images = extractor.extract(sample_pdf_file, str(tmp_path))

    assert md_text
    assert len(fitz_open_spy) == 1
    assert fitz_open_spy[0].is_closed


def test_extract_closes_the_document_even_on_failure(fitz_open_spy: list, sample_pdf_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.pymupdf_processor.pymupdf4llm.to_markdown",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    extractor = PyMuPdfExtractor()
    with pytest.raises(RuntimeError):
        extractor.extract(sample_pdf_file, str(tmp_path))

    assert len(fitz_open_spy) == 1
    assert fitz_open_spy[0].is_closed
