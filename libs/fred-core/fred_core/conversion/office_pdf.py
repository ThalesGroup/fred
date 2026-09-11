# Copyright Thales 2026
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

"""Shared, best-effort Office→PDF conversion using headless LibreOffice.

Why this lives in ``fred-core``:
- Knowledge Flow (slide vision enrichment, the Word/PowerPoint native preview) and the
  Agentic PPT-filler preview all need the exact same ``soffice`` invocation.
  Keeping one implementation here means there is a single place to harden
  (timeout, error handling) instead of several drifting ``subprocess.run`` calls.

Contract:
- The conversion is **best-effort**: any failure (missing ``soffice``, a non-zero exit,
  a timeout, or no PDF produced) returns ``None`` rather than raising through the caller.
  Callers decide how to degrade — the preview pane, for instance, still returns the
  ``.pptx`` when the PDF cannot be produced.
- The bytes helper (:func:`convert_office_bytes_to_pdf`) is **async and bounded**: it runs
  ``soffice`` off the event loop on a small dedicated pool with a timeout, so it is safe
  to call from an async tool or request handler without stalling the turn.
- Format-agnostic: LibreOffice picks its import filter from the source file's extension,
  so ``.docx``, ``.doc``, ``.odt``, ``.pptx``, ``.ppt`` and spreadsheets all go through
  this one entry point. The caller owns the extension it passes.

``soffice`` is expected to be installed in both backend images.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import subprocess  # nosec: controlled command arguments, shell=False
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

logger = logging.getLogger(__name__)

# Each conversion is a full LibreOffice process (~220 MB RSS). A private profile per
# call means they no longer serialize on the shared one, so bound them here or a burst
# of agent turns fans out to the default executor's thread count and OOMs the pod.
# Dedicated executor rather than a module-level asyncio.Semaphore: it is loop-agnostic,
# so it survives callers that run their own event loop.
MAX_CONCURRENT_CONVERSIONS = 4
_conversion_executor = ThreadPoolExecutor(
    max_workers=MAX_CONCURRENT_CONVERSIONS, thread_name_prefix="office2pdf"
)

# LibreOffice can occasionally hang (font server, first-run profile init). A bounded
# timeout keeps a stuck conversion from stalling an async agent turn indefinitely.
DEFAULT_OFFICE_PDF_TIMEOUT_SECONDS = 60.0

# Each LibreOffice application has its own PDF export filter, and asking Writer's for
# an Impress deck is only tolerated by some builds — others exit 0 and write nothing.
# The filter follows the source format; an unlisted one leaves the choice to soffice.
_PDF_EXPORT_OPTIONS = "EmbedStandardFonts=True,SelectPdfVersion=1"
_PDF_EXPORT_FILTERS = {
    ".docx": "writer_pdf_Export",
    ".doc": "writer_pdf_Export",
    ".odt": "writer_pdf_Export",
    ".pptx": "impress_pdf_Export",
    ".ppt": "impress_pdf_Export",
    ".odp": "impress_pdf_Export",
    ".xlsx": "calc_pdf_Export",
    ".xls": "calc_pdf_Export",
    ".ods": "calc_pdf_Export",
}


def _export_filter_for(suffix: str) -> str:
    app_filter = _PDF_EXPORT_FILTERS.get(suffix.lower())
    return f"pdf:{app_filter}:{_PDF_EXPORT_OPTIONS}" if app_filter else "pdf"


def convert_office_file_to_pdf(
    source_path: Path,
    timeout_seconds: float = DEFAULT_OFFICE_PDF_TIMEOUT_SECONDS,
) -> Path | None:
    """Convert an office document to a PDF next to it using headless LibreOffice.

    Blocking; returns the produced ``.pdf`` path, or ``None`` when ``soffice`` is
    missing, fails, times out, or produces no file. Prefer
    :func:`convert_office_bytes_to_pdf` from async code — this variant exists for
    synchronous callers (e.g. the Knowledge Flow slide renderer) that already own a
    temp directory.
    """
    pdf_path = source_path.with_suffix(".pdf")
    pdf_path.unlink(missing_ok=True)
    soffice_path = shutil.which("soffice")
    if not soffice_path:
        logger.error(
            "[OFFICE2PDF] LibreOffice (soffice) is not installed or not in PATH."
        )
        return None

    try:
        # A private profile per conversion. LibreOffice's default profile is
        # single-instance: concurrent headless conversions sharing it, or a profile
        # left in a bad state, make soffice exit 0 and write nothing. Costs ~1s of
        # first-run init, which is noise next to the surrounding agent turn.
        with tempfile.TemporaryDirectory(
            prefix="soffice-profile-", ignore_cleanup_errors=True
        ) as profile_dir:
            subprocess.run(  # nosec: controlled command arguments, shell=False
                [
                    soffice_path,
                    f"-env:UserInstallation={Path(profile_dir).as_uri()}",
                    "--headless",
                    "--nologo",
                    "--nofirststartwizard",
                    "--convert-to",
                    _export_filter_for(source_path.suffix),
                    "--outdir",
                    str(source_path.parent),
                    str(source_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout_seconds,
            )
    except subprocess.TimeoutExpired:
        logger.error(
            "[OFFICE2PDF] LibreOffice conversion timed out after %.0fs.",
            timeout_seconds,
        )
        return None
    except subprocess.CalledProcessError as exc:
        logger.error(
            "[OFFICE2PDF] LibreOffice conversion failed: %s",
            exc.stderr.decode(errors="ignore") if exc.stderr else exc,
        )
        return None

    if pdf_path.exists():
        logger.info("[OFFICE2PDF] Converted %s to PDF: %s", source_path.name, pdf_path)
        return pdf_path

    logger.warning("[OFFICE2PDF] Conversion completed but PDF not found: %s", pdf_path)
    return None


async def convert_office_bytes_to_pdf(
    source_bytes: bytes,
    *,
    suffix: str,
    timeout_seconds: float = DEFAULT_OFFICE_PDF_TIMEOUT_SECONDS,
) -> bytes | None:
    """Convert in-memory office-document bytes to PDF bytes, off the event loop and bounded.

    ``suffix`` is the source file's extension (``".pptx"``, ``".docx"``, ``".doc"``, …):
    LibreOffice selects its import filter from it, so passing the wrong one fails the
    conversion. Returns the PDF bytes, or ``None`` when the conversion is unavailable or
    fails. Never raises for a conversion problem, so a caller can treat the result as
    best-effort.

    Example:
    ```python
    pdf = await convert_office_bytes_to_pdf(filled_bytes, suffix=".pptx")
    if pdf is None:
        ...  # keep the .pptx, skip the preview
    ```
    """

    def _run() -> bytes | None:
        with tempfile.TemporaryDirectory(prefix="office2pdf-") as tmp:
            source_path = Path(tmp) / f"source{suffix}"
            source_path.write_bytes(source_bytes)
            pdf_path = convert_office_file_to_pdf(
                source_path, timeout_seconds=timeout_seconds
            )
            if pdf_path is None:
                return None
            return pdf_path.read_bytes()

    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_conversion_executor, _run)
    except (
        Exception
    ):  # pragma: no cover - defensive: never let conversion break the caller
        logger.exception("[OFFICE2PDF] Unexpected error during Office→PDF conversion.")
        return None
