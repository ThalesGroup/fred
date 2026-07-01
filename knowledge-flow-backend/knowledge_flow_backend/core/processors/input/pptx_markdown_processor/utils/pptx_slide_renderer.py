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

"""Renders PPTX slides as PNG images for vision enrichment."""

from __future__ import annotations

import logging
from pathlib import Path

import fitz
from fred_core import convert_pptx_file_to_pdf

logger = logging.getLogger(__name__)


def convert_pptx_to_pdf(pptx_path: Path) -> Path | None:
    """Convert a PPTX file to PDF using headless LibreOffice.

    Thin wrapper over the shared ``fred_core`` helper so the ``soffice`` invocation lives
    in one place (see ``fred_core.conversion.pptx_pdf``). Returns the produced ``.pdf``
    path, or ``None`` on any failure — the enricher already treats ``None`` as "skip".
    """
    return convert_pptx_file_to_pdf(pptx_path)


def render_pdf_pages_to_png(pdf_path: Path, slide_numbers: list[int], out_dir: Path) -> dict[int, Path]:
    """Render selected PDF pages to PNG images keyed by 1-based slide number."""
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[int, Path] = {}

    doc = fitz.open(pdf_path)
    try:
        for slide_number in slide_numbers:
            page_index = slide_number - 1
            if page_index < 0 or page_index >= len(doc):
                logger.warning(
                    "[PROCESSOR][PPTX] Requested slide %s is out of PDF page range for %s",
                    slide_number,
                    pdf_path,
                )
                continue

            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            png_path = out_dir / f"slide_{slide_number:03d}.png"
            pix.save(str(png_path))
            rendered[slide_number] = png_path

        logger.info(
            "[PROCESSOR][PPTX] Rendered %s slide PNG(s) from %s into %s",
            len(rendered),
            pdf_path,
            out_dir,
        )
        return rendered
    finally:
        doc.close()
