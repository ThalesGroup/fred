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

"""Unit tests for the OpenDocument ``.odt`` ingestion + lightweight processors.

The LibreOffice conversion is mocked so the tests stay offline; the underlying
DocxMarkdownProcessor / LiteDocxToMdProcessor are covered by their own suites. We
only verify the ODT wrapper logic: convert -> delegate, the ODF validity guard,
and identity relabelling.
"""

import zipfile
from pathlib import Path
from unittest.mock import patch

from knowledge_flow_backend.core.processors.input.common.legacy_office import ODT_MIMETYPE
from knowledge_flow_backend.core.processors.input.docx_markdown_processor.docx_markdown_processor import DocxMarkdownProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_docx_to_md_processor import LiteDocxToMdProcessor
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_markdown_structures import LiteMarkdownResult
from knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_odt_to_md_processor import LiteOdtToMdProcessor
from knowledge_flow_backend.core.processors.input.odt_markdown_processor.odt_markdown_processor import OdtMarkdownProcessor


def _write_odt(tmp_path: Path, name: str = "sample.odt", *, mimetype: str = ODT_MIMETYPE) -> Path:
    odt = tmp_path / name
    with zipfile.ZipFile(odt, "w") as archive:
        archive.writestr("mimetype", mimetype)
        archive.writestr("content.xml", "<office:document-content/>")
    return odt


def test_check_file_validity_accepts_odf_text(tmp_path: Path):
    assert OdtMarkdownProcessor().check_file_validity(_write_odt(tmp_path)) is True


def test_check_file_validity_rejects_wrong_odf_type(tmp_path: Path):
    ods = _write_odt(tmp_path, "sheet.odt", mimetype="application/vnd.oasis.opendocument.spreadsheet")
    assert OdtMarkdownProcessor().check_file_validity(ods) is False


def test_check_file_validity_rejects_non_zip(tmp_path: Path):
    fake = tmp_path / "fake.odt"
    fake.write_bytes(b"\xd0\xcf\x11\xe0 not a zip")
    assert OdtMarkdownProcessor().check_file_validity(fake) is False


def test_check_file_validity_rejects_empty(tmp_path: Path):
    empty = tmp_path / "empty.odt"
    empty.write_bytes(b"")
    assert OdtMarkdownProcessor().check_file_validity(empty) is False


def test_convert_file_to_markdown_converts_then_delegates(tmp_path: Path):
    odt = _write_odt(tmp_path)
    output_dir = tmp_path / "out"
    converted = tmp_path / "converted.docx"

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.odt_markdown_processor.odt_markdown_processor.convert_odt_to_docx",
            return_value=converted,
        ) as mock_convert,
        patch.object(DocxMarkdownProcessor, "convert_file_to_markdown", return_value={"md_file": "ok"}) as mock_super,
    ):
        result = OdtMarkdownProcessor().convert_file_to_markdown(odt, output_dir, "uid-7")

    assert result == {"md_file": "ok"}
    mock_convert.assert_called_once()
    assert mock_convert.call_args.args[0] == odt
    mock_super.assert_called_once_with(converted, output_dir, "uid-7")


def test_lite_odt_extract_relabels_identity_and_source_format(tmp_path: Path):
    odt = _write_odt(tmp_path, "notes.odt")
    converted = tmp_path / "notes.docx"

    canned = LiteMarkdownResult(
        document_name="notes.docx",
        page_count=None,
        total_chars=5,
        truncated=False,
        markdown="hello",
        pages=[],
        extras={"engine": "markitdown"},
    )

    with (
        patch(
            "knowledge_flow_backend.core.processors.input.lightweight_markdown_processor.lite_odt_to_md_processor.convert_odt_to_docx",
            return_value=converted,
        ),
        patch.object(LiteDocxToMdProcessor, "extract", return_value=canned),
    ):
        result = LiteOdtToMdProcessor().extract(odt)

    assert result.document_name == "notes.odt"
    assert result.markdown == "hello"
    assert result.extras["source_format"] == "odt"
    assert result.extras["engine"] == "markitdown"
