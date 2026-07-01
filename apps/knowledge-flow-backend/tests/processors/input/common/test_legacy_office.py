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

"""Unit tests for the legacy Office (.doc/.ppt) -> OOXML LibreOffice converter."""

import zipfile
from pathlib import Path

import pytest

from knowledge_flow_backend.core.processors.input.common import legacy_office
from knowledge_flow_backend.core.processors.input.common.legacy_office import (
    ODT_MIMETYPE,
    OLE2_MAGIC,
    LegacyOfficeConversionError,
    convert_doc_to_docx,
    convert_odt_to_docx,
    convert_ppt_to_pptx,
    looks_like_odf,
    looks_like_ole_binary,
)


def _write_odt(path: Path, *, mimetype: str = ODT_MIMETYPE, with_content: bool = True) -> Path:
    """Write a minimal ODF-like ZIP package for validity tests."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", mimetype)
        if with_content:
            archive.writestr("content.xml", "<office:document-content/>")
    return path


def test_looks_like_ole_binary_detects_ole_header(tmp_path: Path):
    ole_file = tmp_path / "legacy.doc"
    ole_file.write_bytes(OLE2_MAGIC + b"the rest of the binary payload")
    assert looks_like_ole_binary(ole_file) is True


def test_looks_like_ole_binary_rejects_non_ole(tmp_path: Path):
    plain = tmp_path / "plain.txt"
    plain.write_bytes(b"PK\x03\x04 this is actually a zip/ooxml header")
    assert looks_like_ole_binary(plain) is False


def test_looks_like_ole_binary_handles_missing_file(tmp_path: Path):
    assert looks_like_ole_binary(tmp_path / "does-not-exist.doc") is False


def test_convert_doc_to_docx_raises_when_soffice_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(legacy_office.shutil, "which", lambda _: None)
    with pytest.raises(LegacyOfficeConversionError, match="soffice"):
        convert_doc_to_docx(tmp_path / "x.doc", tmp_path / "out")


def test_convert_ppt_to_pptx_raises_when_soffice_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(legacy_office.shutil, "which", lambda _: None)
    with pytest.raises(LegacyOfficeConversionError, match="soffice"):
        convert_ppt_to_pptx(tmp_path / "x.ppt", tmp_path / "out")


def test_convert_doc_to_docx_returns_expected_artifact(tmp_path: Path, monkeypatch):
    """LibreOffice is mocked; the converter must return the produced .docx path."""
    monkeypatch.setattr(legacy_office.shutil, "which", lambda _: "/usr/bin/soffice")

    src = tmp_path / "memo.doc"
    src.write_bytes(OLE2_MAGIC)
    out_dir = tmp_path / "out"

    def fake_run(cmd, **kwargs):
        # Simulate LibreOffice writing <stem>.docx into the out dir.
        (out_dir / "memo.docx").write_bytes(b"PK\x03\x04 fake docx")

        class _Completed:
            returncode = 0

        return _Completed()

    monkeypatch.setattr(legacy_office.subprocess, "run", fake_run)

    result = convert_doc_to_docx(src, out_dir)
    assert result == out_dir / "memo.docx"
    assert result.exists()


def test_convert_doc_to_docx_raises_when_no_output(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(legacy_office.shutil, "which", lambda _: "/usr/bin/soffice")
    monkeypatch.setattr(legacy_office.subprocess, "run", lambda cmd, **kwargs: None)
    with pytest.raises(LegacyOfficeConversionError, match="produced no"):
        convert_doc_to_docx(tmp_path / "memo.doc", tmp_path / "out")


def test_looks_like_odf_accepts_matching_mimetype(tmp_path: Path):
    odt = _write_odt(tmp_path / "doc.odt")
    assert looks_like_odf(odt, ODT_MIMETYPE) is True


def test_looks_like_odf_rejects_wrong_mimetype(tmp_path: Path):
    other = _write_odt(tmp_path / "sheet.odt", mimetype="application/vnd.oasis.opendocument.spreadsheet")
    assert looks_like_odf(other, ODT_MIMETYPE) is False


def test_looks_like_odf_rejects_non_zip(tmp_path: Path):
    plain = tmp_path / "plain.odt"
    plain.write_bytes(b"\xd0\xcf\x11\xe0 not a zip")
    assert looks_like_odf(plain, ODT_MIMETYPE) is False


def test_convert_odt_to_docx_raises_when_soffice_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(legacy_office.shutil, "which", lambda _: None)
    with pytest.raises(LegacyOfficeConversionError, match="soffice"):
        convert_odt_to_docx(tmp_path / "x.odt", tmp_path / "out")
