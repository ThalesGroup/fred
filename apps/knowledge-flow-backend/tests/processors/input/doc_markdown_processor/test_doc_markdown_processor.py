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

"""Unit tests for the legacy ``.doc`` ingestion + lightweight processors.

These tests mock the LibreOffice conversion so they stay offline and fast: the
DocxMarkdownProcessor / LiteDocxToMdProcessor delegation paths are already
covered by their own suites. Here we only verify the legacy wrapper logic:
convert -> delegate, plus the OLE validity guard and identity relabelling.
"""

from pathlib import Path
from unittest.mock import patch

from knowledge_flow_backend.core.processors.input.common.legacy_office import OLE2_MAGIC
from knowledge_flow_backend.core.processors.input.doc_markdown_processor.doc_markdown_processor import DocMarkdownProcessor
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import DocxMarkdownProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_doc_to_md_processor import LiteDocToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import LiteDocxToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownResult


def _write_doc(tmp_path: Path, name: str = "sample.doc") -> Path:
    doc = tmp_path / name
    doc.write_bytes(OLE2_MAGIC + b"legacy word payload")
    return doc


def test_check_file_validity_accepts_ole_doc(tmp_path: Path):
    assert DocMarkdownProcessor().check_file_validity(_write_doc(tmp_path)) is True


def test_check_file_validity_rejects_non_ole(tmp_path: Path):
    fake = tmp_path / "fake.doc"
    fake.write_bytes(b"PK\x03\x04 not a legacy doc")
    assert DocMarkdownProcessor().check_file_validity(fake) is False


def test_check_file_validity_rejects_empty(tmp_path: Path):
    empty = tmp_path / "empty.doc"
    empty.write_bytes(b"")
    assert DocMarkdownProcessor().check_file_validity(empty) is False


def test_convert_file_to_markdown_converts_then_delegates(tmp_path: Path):
    doc = _write_doc(tmp_path)
    output_dir = tmp_path / "out"
    converted = tmp_path / "converted.docx"

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.doc_markdown_processor.doc_markdown_processor.convert_doc_to_docx",
            return_value=converted,
        ) as mock_convert,
        patch.object(DocxMarkdownProcessor, "convert_file_to_markdown", return_value={"md_file": "ok"}) as mock_super,
    ):
        result = DocMarkdownProcessor().convert_file_to_markdown(doc, output_dir, "uid-123")

    assert result == {"md_file": "ok"}
    mock_convert.assert_called_once()
    assert mock_convert.call_args.args[0] == doc
    # Parent must receive the converted .docx, not the original .doc.
    mock_super.assert_called_once_with(converted, output_dir, "uid-123")


def test_extract_file_metadata_converts_then_delegates(tmp_path: Path):
    doc = _write_doc(tmp_path)
    converted = tmp_path / "converted.docx"

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.doc_markdown_processor.doc_markdown_processor.convert_doc_to_docx",
            return_value=converted,
        ),
        patch.object(DocxMarkdownProcessor, "extract_file_metadata", return_value={"author": "Ada"}) as mock_super,
    ):
        meta = DocMarkdownProcessor().extract_file_metadata(doc)

    assert meta == {"author": "Ada"}
    mock_super.assert_called_once_with(converted)


def test_convert_file_to_markdown_leaves_no_intermediate_in_output_dir(tmp_path: Path):
    """The converted .docx lives only in a temp dir; the persistent output_dir must
    contain the markdown (+ media) but never the intermediate office file."""
    doc = _write_doc(tmp_path)
    output_dir = tmp_path / "out"
    sample_docx = Path(__file__).parents[1] / "docx_markdown_processor" / "assets" / "sample.docx"

    with patch(
        "knowledge_flow_backend.core.processors.input.doc_markdown_processor.doc_markdown_processor.convert_doc_to_docx",
        return_value=sample_docx,
    ):
        result = DocMarkdownProcessor().convert_file_to_markdown(doc, output_dir, "uid-doc")

    assert Path(result["md_file"]).exists()
    leaked = sorted(p.name for p in output_dir.rglob("*") if p.suffix.lower() in {".doc", ".docx", ".odt", ".ppt", ".pptx"})
    assert leaked == [], f"intermediate office file leaked into persistent output_dir: {leaked}"


def test_lite_doc_extract_relabels_identity_and_source_format(tmp_path: Path):
    doc = _write_doc(tmp_path, "report.doc")
    converted = tmp_path / "report.docx"

    canned = LiteMarkdownResult(
        document_name="report.docx",
        page_count=None,
        total_chars=5,
        truncated=False,
        markdown="hello",
        pages=[],
        extras={"engine": "markitdown"},
    )

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_doc_to_md_processor.convert_doc_to_docx",
            return_value=converted,
        ),
        patch.object(LiteDocxToMdProcessor, "extract", return_value=canned),
    ):
        result = LiteDocToMdProcessor().extract(doc)

    # Original .doc identity is preserved and the source format is recorded.
    assert result.document_name == "report.doc"
    assert result.markdown == "hello"
    assert result.extras["source_format"] == "doc"
    assert result.extras["engine"] == "markitdown"
