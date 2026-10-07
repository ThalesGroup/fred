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

"""The patterns preview deck: one slide per inventory pattern, in inventory
order, so a PDF conversion yields one thumbnail page per pattern for the
review widget. Layout patterns are instantiated with their zone roles typed
into the placeholders; example slides are copied as they are. The same PDF,
rasterised with numbered slot marks, is what the vision labelling looks at."""

from __future__ import annotations

import io
import threading
from typing import Any, Collection, Dict, List, cast

import pypdfium2 as pdfium
from PIL import Image, ImageDraw, ImageFont

from fred_capability_ppt_filler.builder.models import (
    Pattern,
    TemplateInventory,
    Zone,
)
from fred_capability_ppt_filler.builder.render import (
    _all_layouts,
    _duplicate_slide,
    _remove_slides,
)
from fred_capability_ppt_filler.pptx_archive import open_presentation


def build_patterns_deck(template_bytes: bytes, inventory: TemplateInventory) -> bytes:
    """Return ``.pptx`` bytes with one slide per pattern (CPU-bound; call off the loop)."""
    presentation = open_presentation(template_bytes)
    layouts = _all_layouts(presentation)
    slides_by_id = {slide.slide_id: slide for slide in presentation.slides}
    original_ids = list(slides_by_id)
    blank = layouts[-1] if layouts else None
    for pattern in inventory.patterns:
        # Page N must stay pattern N for the review: a pattern that cannot be
        # rendered (uncopyable parts, vanished source) still gets a page.
        if pattern.source == "layout":
            if pattern.source_index >= len(layouts):
                if blank is not None:
                    presentation.slides.add_slide(blank)
                continue
            slide = presentation.slides.add_slide(layouts[pattern.source_index])
            for shape in slide.placeholders:
                if not shape.has_text_frame:
                    continue
                shape = cast(Any, shape)
                zone = next(
                    (
                        z
                        for z in pattern.zones
                        if z.key == f"ph:{shape.placeholder_format.idx}"
                    ),
                    None,
                )
                shape.text_frame.text = zone.role.capitalize() if zone else ""
        else:
            source = slides_by_id.get(int(pattern.id.split(":", 1)[1]))
            if source is not None and pattern.exclusion_reason != "unsupported_parts":
                _duplicate_slide(presentation, source)
            elif source is not None:
                presentation.slides.add_slide(source.slide_layout)
            elif blank is not None:
                presentation.slides.add_slide(blank)
    _remove_slides(presentation, original_ids)
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


# PDFium is not thread-safe: every use in the process goes through this lock.
_PDFIUM_LOCK = threading.Lock()
_MARK_COLOR = (230, 0, 126)


def numbered_slots(pattern: Pattern) -> List[Zone]:
    """The slots the vision marks number, in order: slot N is element N-1."""
    slots = [zone for zone in pattern.zones if zone.role != "keep"]
    for group in pattern.groups:
        slots.extend(zone for item in group.items for zone in item)
    return slots


def marked_pattern_images(
    patterns_pdf: bytes,
    inventory: TemplateInventory,
    pattern_ids: Collection[str],
    *,
    width_px: int = 1024,
) -> Dict[str, bytes]:
    """PNG per requested pattern, its slots outlined and numbered.

    Page N of the patterns PDF is pattern N; a page-count mismatch yields
    nothing rather than a misattributed image. CPU-bound: call off the loop.
    """
    wanted = {
        index: pattern
        for index, pattern in enumerate(inventory.patterns)
        if pattern.id in pattern_ids
    }
    images: Dict[str, bytes] = {}
    with _PDFIUM_LOCK:
        document = pdfium.PdfDocument(patterns_pdf)
        try:
            if len(document) != len(inventory.patterns):
                return {}
            for index, pattern in wanted.items():
                page = document[index]
                bitmap = page.render(scale=width_px / page.get_width())
                image = bitmap.to_pil().convert("RGB")
                page.close()
                images[pattern.id] = _mark_slots(image, numbered_slots(pattern))
        finally:
            document.close()
    return images


def _mark_slots(image: Image.Image, slots: List[Zone]) -> bytes:
    draw = ImageDraw.Draw(image)
    width, height = image.size
    size = max(14, width // 48)
    font = ImageFont.load_default(size=size)
    for number, zone in enumerate(slots, start=1):
        left, top = zone.box.x * width // 1000, zone.box.y * height // 1000
        right = left + max(zone.box.w * width // 1000, 1)
        bottom = top + max(zone.box.h * height // 1000, 1)
        draw.rectangle((left, top, right, bottom), outline=_MARK_COLOR, width=3)
        badge = draw.textbbox((left, top), str(number), font=font)
        pad = size // 4
        draw.rectangle(
            (left, top, badge[2] + 2 * pad, badge[3] + 2 * pad), fill=_MARK_COLOR
        )
        draw.text((left + pad, top + pad), str(number), fill="white", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
