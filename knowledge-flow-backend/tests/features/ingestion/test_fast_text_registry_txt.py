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

"""
Regression tests for `.txt` support as a conversation/session attachment (issue #1900).

Why this exists:
- Uploading a `.txt` attachment previously failed with
  `HTTPException(400, "No fast text processor configured for '.txt'")` because the
  default fast-text processor registry did not include `.txt`.
- These tests pin `.txt` (case-insensitive) to `FastLiteMarkdownProcessor` and verify
  that a plain-text file extracts its content, mirroring what `/fast/ingest` does with
  an uploaded attachment.
"""

import pytest

from knowledge_flow_backend.core.processors.input.fast_text_processor.fast_lite_markdown_processor import (
    FastLiteMarkdownProcessor,
)
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


@pytest.fixture
def controller() -> IngestionController:
    """Build a controller with only the fast-text registry wired up.

    The default registry is used because the test `Configuration` leaves
    `attachment_processors` unset (see conftest `app_context`).
    """
    ctrl = IngestionController.__new__(IngestionController)
    ctrl._fast_text_registry = ctrl._build_fast_text_registry()
    ctrl._fast_text_instances = {}
    return ctrl


@pytest.mark.parametrize("filename", ["notes.txt", "NOTES.TXT", "Notes.Txt"])
def test_txt_resolves_to_markdown_processor(controller: IngestionController, filename: str):
    processor = controller._get_fast_text_processor(filename)
    assert isinstance(processor, FastLiteMarkdownProcessor)


def test_txt_extraction_returns_plain_text(controller: IngestionController, tmp_path):
    txt_file = tmp_path / "hello.txt"
    txt_file.write_text("Hello, world.\nSecond line.\n", encoding="utf-8")

    processor = controller._get_fast_text_processor(txt_file.name)
    result = processor.extract(txt_file)

    assert "Hello, world." in result.text
    assert "Second line." in result.text
