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

"""Vision enrichment helpers for PPTX slides."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from knowledge_flow_backend.core.processors.input.pptx_markdown_processor.utils.pptx_slide_renderer import (
    convert_pptx_to_pdf,
    render_pdf_pages_to_png,
)

logger = logging.getLogger(__name__)


def enrich_slides_with_vision(
    pptx_path: Path,
    slide_numbers: list[int],
    output_dir: Path,
    image_describer,
) -> dict[int, str]:
    """Return slide-level visual enrichments for the selected slide numbers."""
    if not slide_numbers:
        return {}

    if image_describer is None:
        logger.warning("[PROCESSOR][PPTX] No image describer available for vision enrichment.")
        return {}

    pdf_path = convert_pptx_to_pdf(pptx_path)
    if pdf_path is None:
        logger.warning("[PROCESSOR][PPTX] PPTX to PDF conversion failed; skipping vision enrichment.")
        return {}

    slides_dir = output_dir / "slides_png"
    rendered_slides = render_pdf_pages_to_png(pdf_path, slide_numbers, slides_dir)

    enrichments: dict[int, str] = {}

    for slide_number, png_path in rendered_slides.items():
        try:
            image_base64 = base64.b64encode(png_path.read_bytes()).decode("utf-8")
            description = image_describer.describe(image_base64).strip()
            if not description:
                description = "Visual enrichment not available."
            enrichments[slide_number] = description
        except Exception as exc:
            logger.warning(
                "[PROCESSOR][PPTX] Vision enrichment failed for slide %s: %s",
                slide_number,
                exc,
            )
            enrichments[slide_number] = "Visual enrichment not available."

    logger.info(
        "[PROCESSOR][PPTX] Generated vision enrichments for %s slide(s).",
        len(enrichments),
    )
    return enrichments
