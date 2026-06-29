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

"""Upgrade legacy binary Office files (``.doc``, ``.ppt``) to OOXML via LibreOffice.

Why this exists:
- ``.doc`` / ``.ppt`` are legacy OLE/CFB binary formats. Unlike their OOXML
  successors (``.docx`` / ``.pptx``) they are not readable by python-docx /
  python-pptx / pandoc / markitdown.
- Rather than add second-class legacy parsers, we convert each legacy file to its
  modern equivalent once and then reuse the existing, well-tested OOXML extractors
  on every surface (corpus ingestion, chat attachments, fast text).

How to use:
- Call ``convert_doc_to_docx`` / ``convert_ppt_to_pptx`` and feed the returned
  path to the existing DOCX / PPTX processor. The caller owns ``out_dir``
  lifecycle (typically a ``tempfile.TemporaryDirectory``).

This mirrors the LibreOffice pattern already used by the PPTX slide renderer
(``convert_pptx_to_pdf``).
"""

from __future__ import annotations

import logging
import shutil
import subprocess  # nosec
from pathlib import Path

logger = logging.getLogger(__name__)

# OLE2 / Compound File Binary signature shared by legacy Office documents
# (.doc, .xls, .ppt). Used for a cheap validity check before spawning LibreOffice.
OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class LegacyOfficeConversionError(RuntimeError):
    """Raised when a legacy binary Office file cannot be upgraded to OOXML."""


def looks_like_ole_binary(file_path: Path) -> bool:
    """Cheap structural check that ``file_path`` is a legacy OLE binary file.

    Returns ``True`` when the file starts with the OLE2 compound-file signature
    shared by legacy ``.doc`` / ``.xls`` / ``.ppt`` documents. This avoids
    spawning LibreOffice just to reject obviously invalid inputs.
    """
    try:
        with file_path.open("rb") as handle:
            return handle.read(len(OLE2_MAGIC)) == OLE2_MAGIC
    except OSError as exc:
        logger.warning("[LEGACY-OFFICE] Failed to read header of %s: %s", file_path, exc)
        return False


def _convert_with_libreoffice(src_path: Path, out_dir: Path, *, convert_to: str, target_suffix: str) -> Path:
    """Convert ``src_path`` to ``target_suffix`` in ``out_dir`` via headless LibreOffice.

    :param convert_to: LibreOffice ``--convert-to`` argument (filter spec).
    :param target_suffix: expected output suffix, e.g. ``".docx"``.
    :raises LegacyOfficeConversionError: if LibreOffice is missing or conversion fails.
    """
    soffice_path = shutil.which("soffice")
    if not soffice_path:
        raise LegacyOfficeConversionError("LibreOffice executable 'soffice' not found in PATH. Please ensure LibreOffice is installed and available.")

    out_dir.mkdir(parents=True, exist_ok=True)
    expected_output = out_dir / f"{src_path.stem}{target_suffix}"

    try:
        subprocess.run(
            [
                soffice_path,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                convert_to,
                "--outdir",
                str(out_dir),
                str(src_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )  # nosec: controlled command arguments, shell=False
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="ignore").strip() if exc.stderr else str(exc)
        raise LegacyOfficeConversionError(f"LibreOffice conversion failed for '{src_path.name}': {detail}") from exc

    if not expected_output.exists():
        # LibreOffice exited 0 but did not produce the expected artifact; fall back
        # to the first matching file it emitted, if any, otherwise fail loudly.
        produced = sorted(out_dir.glob(f"*{target_suffix}"))
        if not produced:
            raise LegacyOfficeConversionError(f"LibreOffice conversion produced no '{target_suffix}' for '{src_path.name}'.")
        expected_output = produced[0]

    logger.info("[LEGACY-OFFICE] Converted %s -> %s via LibreOffice", src_path.name, expected_output.name)
    return expected_output


def convert_doc_to_docx(doc_path: Path, out_dir: Path) -> Path:
    """Convert a legacy ``.doc`` file to ``.docx`` via headless LibreOffice."""
    return _convert_with_libreoffice(doc_path, out_dir, convert_to="docx:MS Word 2007 XML", target_suffix=".docx")


def convert_ppt_to_pptx(ppt_path: Path, out_dir: Path) -> Path:
    """Convert a legacy ``.ppt`` file to ``.pptx`` via headless LibreOffice."""
    return _convert_with_libreoffice(ppt_path, out_dir, convert_to="pptx:Impress MS PowerPoint 2007 XML", target_suffix=".pptx")
