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

"""Regression tests for DoclingPdfExtractor's DocumentConverter caching.

Building a DocumentConverter loads the OCR/layout/picture-classification ONNX
models from disk. Rebuilding it per document (the previous behavior) reloads
that whole pipeline on every file processed. These tests assert the converter
is built exactly once and reused across multiple extract() calls.
"""

import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor import DoclingPdfExtractor


class FakeDocument:
    pictures: list = []

    def export_to_markdown(self, image_mode=None, image_placeholder=None) -> str:
        return "# ok\n"


class FakeDocumentConverter:
    build_count = 0

    def __init__(self, *, format_options):
        FakeDocumentConverter.build_count += 1

    def convert(self, file_path):
        return SimpleNamespace(document=FakeDocument())


@pytest.fixture(autouse=True)
def _reset_build_count():
    FakeDocumentConverter.build_count = 0
    yield


@pytest.fixture
def patched_extractor(monkeypatch: pytest.MonkeyPatch) -> DoclingPdfExtractor:
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor.get_configuration",
        lambda: SimpleNamespace(processing=SimpleNamespace(path_base_model="/tmp/fake-models")),
    )
    monkeypatch.setattr(
        "knowledge_flow_backend.core.processors.input.pdf_markdown_processor.docling_processor.DocumentConverter",
        FakeDocumentConverter,
    )
    return DoclingPdfExtractor(num_threads=2)


def test_extract_builds_the_converter_only_once_across_calls(patched_extractor: DoclingPdfExtractor, tmp_path: Path):
    for _ in range(3):
        md_text, images = patched_extractor.extract(Path("irrelevant.pdf"), str(tmp_path))
        assert md_text == "# ok\n"

    assert FakeDocumentConverter.build_count == 1


def test_get_document_converter_is_thread_safe(patched_extractor: DoclingPdfExtractor):
    barrier = threading.Barrier(8)

    def _call():
        barrier.wait(timeout=5)
        patched_extractor._get_document_converter()

    threads = [threading.Thread(target=_call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert FakeDocumentConverter.build_count == 1
