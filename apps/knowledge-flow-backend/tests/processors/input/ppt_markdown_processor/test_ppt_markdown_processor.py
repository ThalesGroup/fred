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

"""Unit tests for the legacy ``.ppt`` ingestion + lightweight processors.

The LibreOffice conversion is mocked so the tests stay offline; the underlying
PptxMarkdownProcessor / LitePptxToMdExtractor are already covered elsewhere. We
only verify the legacy wrapper logic: convert -> delegate, the OLE validity
guard, and identity relabelling.
"""

from pathlib import Path
from unittest.mock import patch

from knowledge_flow_backend.core.processors.input.common.legacy_office import OLE2_MAGIC
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownResult
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_ppt_to_md_processor import LitePptToMdExtractor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_pptx_to_md_processor import LitePptxToMdExtractor
from knowledge_flow_backend.core.processors.input.ppt_markdown_processor.ppt_markdown_processor import PptMarkdownProcessor
from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.pptx_markdown_processor import PptxMarkdownProcessor


def _write_ppt(tmp_path: Path, name: str = "deck.ppt") -> Path:
    ppt = tmp_path / name
    ppt.write_bytes(OLE2_MAGIC + b"legacy powerpoint payload")
    return ppt


def test_check_file_validity_accepts_ole_ppt(tmp_path: Path):
    assert PptMarkdownProcessor().check_file_validity(_write_ppt(tmp_path)) is True


def test_check_file_validity_rejects_non_ole(tmp_path: Path):
    fake = tmp_path / "fake.ppt"
    fake.write_bytes(b"PK\x03\x04 not a legacy ppt")
    assert PptMarkdownProcessor().check_file_validity(fake) is False


def test_check_file_validity_rejects_empty(tmp_path: Path):
    empty = tmp_path / "empty.ppt"
    empty.write_bytes(b"")
    assert PptMarkdownProcessor().check_file_validity(empty) is False


def test_convert_file_to_markdown_converts_then_delegates(tmp_path: Path):
    ppt = _write_ppt(tmp_path)
    output_dir = tmp_path / "out"
    converted = tmp_path / "converted.pptx"

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.ppt_markdown_processor.ppt_markdown_processor.convert_ppt_to_pptx",
            return_value=converted,
        ) as mock_convert,
        patch.object(PptxMarkdownProcessor, "convert_file_to_markdown", return_value={"md_file": "ok"}) as mock_super,
    ):
        result = PptMarkdownProcessor().convert_file_to_markdown(ppt, output_dir, "uid-42")

    assert result == {"md_file": "ok"}
    mock_convert.assert_called_once()
    assert mock_convert.call_args.args[0] == ppt
    # Parent must receive the converted .pptx, not the original .ppt.
    mock_super.assert_called_once_with(converted, output_dir, "uid-42")


def test_lite_ppt_extract_relabels_identity_and_source_format(tmp_path: Path):
    ppt = _write_ppt(tmp_path, "slides.ppt")
    converted = tmp_path / "slides.pptx"

    canned = LiteMarkdownResult(
        document_name="slides.pptx",
        page_count=3,
        total_chars=5,
        truncated=False,
        markdown="hello",
        pages=[],
        extras={"engine": "python-pptx-slidewise"},
    )

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_ppt_to_md_processor.convert_ppt_to_pptx",
            return_value=converted,
        ),
        patch.object(LitePptxToMdExtractor, "extract", return_value=canned),
    ):
        result = LitePptToMdExtractor().extract(ppt)

    assert result.document_name == "slides.ppt"
    assert result.page_count == 3
    assert result.extras["source_format"] == "ppt"
    assert result.extras["engine"] == "python-pptx-slidewise"
