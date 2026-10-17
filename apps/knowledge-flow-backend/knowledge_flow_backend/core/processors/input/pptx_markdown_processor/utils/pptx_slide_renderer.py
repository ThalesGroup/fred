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

"""Renders PPTX slides as PNG images for vision enrichment.

PPTX→PDF conversion itself lives in ``fred_core.conversion`` - one hardened
``soffice`` invocation shared with the PPT-filler preview.
"""

from __future__ import annotations

import json
import logging
import subprocess  # nosec B404 - fixed Python executable and script; no shell
import sys
from pathlib import Path

logger = logging.getLogger(__name__)
RENDER_TIMEOUT_SECONDS = 120


def render_pdf_pages_to_png(pdf_path: Path, slide_numbers: list[int], out_dir: Path) -> dict[int, Path]:
    """Render a deck in its own process: PDFium must not share concurrent native calls.

    Docling also uses PDFium in the parent worker. A per-deck child isolates that
    native state and releases all native memory on success, failure or timeout.
    subprocess.run kills and reaps the child when the timeout expires.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if not slide_numbers:
        return {}
    result = subprocess.run(  # nosec B603 - fixed executable/script, paths passed as separate arguments
        [sys.executable, str(Path(__file__).resolve()), str(pdf_path.resolve()), str(out_dir.resolve()), json.dumps(slide_numbers)],
        capture_output=True,
        text=True,
        check=True,
        timeout=RENDER_TIMEOUT_SECONDS,
    )
    if result.stderr:
        logger.info("[PROCESSOR][PPTX] %s", result.stderr.strip())
    return {number: out_dir / f"slide_{number:03d}.png" for number in json.loads(result.stdout)}


def _render_in_child(pdf_path: Path, slide_numbers: list[int], out_dir: Path) -> list[int]:
    import pypdfium2 as pdfium

    rendered = []
    with pdfium.PdfDocument(pdf_path) as doc:
        for number in dict.fromkeys(slide_numbers):
            if number < 1 or number > len(doc):
                logger.warning("Requested slide %s is out of PDF page range for %s", number, pdf_path)
                continue
            page = doc[number - 1]
            try:
                bitmap = page.render(scale=2)
                try:
                    with bitmap.to_pil() as image:
                        image.save(out_dir / f"slide_{number:03d}.png")
                finally:
                    bitmap.close()
            finally:
                page.close()
            rendered.append(number)
    return rendered


if __name__ == "__main__":
    print(json.dumps(_render_in_child(Path(sys.argv[1]), json.loads(sys.argv[3]), Path(sys.argv[2]))))
