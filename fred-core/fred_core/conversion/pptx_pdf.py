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

"""Shared, best-effort PPTX→PDF conversion using headless LibreOffice.

Why this lives in ``fred-core``:
- Both Knowledge Flow (slide vision enrichment) and the Agentic PPT-filler preview
  need the exact same ``soffice`` invocation. Keeping one implementation here means
  there is a single place to harden (timeout, error handling) instead of two drifting
  ``subprocess.run`` calls.

Contract:
- The conversion is **best-effort**: any failure (missing ``soffice``, a non-zero exit,
  a timeout, or no PDF produced) returns ``None`` (for the bytes helper) rather than
  raising through the caller. Callers decide how to degrade — the preview pane, for
  instance, still returns the ``.pptx`` when the PDF cannot be produced.
- The bytes helper (:func:`convert_pptx_bytes_to_pdf`) is **async and bounded**: it runs
  ``soffice`` off the event loop via ``asyncio.to_thread`` with a timeout, so it is safe
  to call from an async tool without stalling the turn.

``soffice`` is expected to be installed in both backend images.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess  # nosec: controlled command arguments, shell=False
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# LibreOffice can occasionally hang (font server, first-run profile init). A bounded
# timeout keeps a stuck conversion from stalling an async agent turn indefinitely.
DEFAULT_PPTX_PDF_TIMEOUT_SECONDS = 60.0

# Same export filter the Knowledge Flow processor has used in production: embed standard
# fonts and pin the PDF version so the rendered deck is faithful across viewers.
_PDF_EXPORT_FILTER = "pdf:writer_pdf_Export:EmbedStandardFonts=True,SelectPdfVersion=1"


def convert_pptx_file_to_pdf(
    pptx_path: Path,
    timeout_seconds: float = DEFAULT_PPTX_PDF_TIMEOUT_SECONDS,
) -> Path | None:
    """Convert a ``.pptx`` file to a PDF next to it using headless LibreOffice.

    Blocking; returns the produced ``.pdf`` path, or ``None`` when ``soffice`` is
    missing, fails, times out, or produces no file. Prefer :func:`convert_pptx_bytes_to_pdf`
    from async code — this variant exists for synchronous callers (e.g. the Knowledge Flow
    slide renderer) that already own a temp directory.
    """
    pdf_path = pptx_path.with_suffix(".pdf")
    soffice_path = shutil.which("soffice")
    if not soffice_path:
        logger.error(
            "[PPTX2PDF] LibreOffice (soffice) is not installed or not in PATH."
        )
        return None

    try:
        subprocess.run(  # nosec: controlled command arguments, shell=False
            [
                soffice_path,
                "--headless",
                "--nologo",
                "--nofirststartwizard",
                "--convert-to",
                _PDF_EXPORT_FILTER,
                "--outdir",
                str(pptx_path.parent),
                str(pptx_path),
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        logger.error(
            "[PPTX2PDF] LibreOffice conversion timed out after %.0fs.", timeout_seconds
        )
        return None
    except subprocess.CalledProcessError as exc:
        logger.error(
            "[PPTX2PDF] LibreOffice conversion failed: %s",
            exc.stderr.decode(errors="ignore") if exc.stderr else exc,
        )
        return None

    if pdf_path.exists():
        logger.info("[PPTX2PDF] Converted PPTX to PDF: %s", pdf_path)
        return pdf_path

    logger.warning("[PPTX2PDF] Conversion completed but PDF not found: %s", pdf_path)
    return None


async def convert_pptx_bytes_to_pdf(
    pptx_bytes: bytes,
    timeout_seconds: float = DEFAULT_PPTX_PDF_TIMEOUT_SECONDS,
) -> bytes | None:
    """Convert in-memory ``.pptx`` bytes to PDF bytes, off the event loop and bounded.

    Returns the PDF bytes, or ``None`` when the conversion is unavailable or fails (missing
    ``soffice``, non-zero exit, timeout, or no PDF produced). Never raises for a conversion
    problem, so a caller can treat the preview as best-effort.

    Example:
    ```python
    pdf = await convert_pptx_bytes_to_pdf(filled_bytes)
    if pdf is None:
        ...  # keep the .pptx, skip the preview
    ```
    """

    def _run() -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="pptx2pdf-") as tmp:
            pptx_path = Path(tmp) / "deck.pptx"
            pptx_path.write_bytes(pptx_bytes)
            pdf_path = convert_pptx_file_to_pdf(
                pptx_path, timeout_seconds=timeout_seconds
            )
            if pdf_path is None:
                return None
            return pdf_path.read_bytes()

    try:
        return await asyncio.to_thread(_run)
    except (
        Exception
    ):  # pragma: no cover - defensive: never let conversion break the caller
        logger.exception("[PPTX2PDF] Unexpected error during PPTX→PDF conversion.")
        return None
