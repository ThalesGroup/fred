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

"""Shared in-code ``.pptx`` builders for the capability/fill/analyze tests.

Decks are built with python-pptx (no checked-in binaries), mirroring the helper
style already used by ``tests/test_parser.py`` and ``tests/test_anchors.py``.
Keeping them here avoids duplicating the same builders across ``test_fill.py``,
``test_validate_config.py`` and ``test_analyze_route.py``.
"""

from __future__ import annotations

import io
from typing import List, Tuple

from fred_capability_ppt_filler.parser import SlideSchema, parse
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

# (text-box body, notes text) per slide.
SlideSpec = Tuple[str, str]

# An image-key notes block: type:image + a folder, plus prose so it is well-formed.
IMAGE_NOTES = "{{logo}}:\n- type: image\n- folder: Brand/Logos\nThe company logo"


def build_deck(slides: List[SlideSpec]) -> bytes:
    """Build a ``.pptx`` with one text box and one notes block per slide spec."""
    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]  # blank
    for body, notes in slides:
        slide = presentation.slides.add_slide(blank_layout)
        textbox = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(8), Inches(2))
        textbox.text_frame.text = body
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def build_image_deck(slides: List[Tuple[str, List[str]]]) -> bytes:
    """Build a deck whose slides each carry one or more textbox specs.

    ``slides`` is a list of ``(notes, [textbox_text, ...])``. Each textbox is
    added at a distinct, fixed box (4in wide, 2in tall) so image anchors have a
    real geometry to fit a picture inside.
    """
    presentation = Presentation()
    blank_layout = presentation.slide_layouts[6]  # blank
    for notes, textboxes in slides:
        slide = presentation.slides.add_slide(blank_layout)
        for offset, text in enumerate(textboxes):
            box = slide.shapes.add_textbox(
                Inches(1),
                Inches(1 + 2 * offset),
                Inches(4),  # wider than tall -> a square image fits the HEIGHT
                Inches(2),
            )
            box.text_frame.text = text
        if notes:
            slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def build_table_deck(notes: str, cell_texts: List[str]) -> bytes:
    """Build a one-slide deck whose key-bearing shape is a 1xN TABLE, plus notes.

    A ``{{key}}`` sitting in a table cell is an invalid picture location, so this
    exercises the image-location refusal path.
    """
    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[6])
    table = slide.shapes.add_table(
        1, len(cell_texts), Inches(1), Inches(1), Inches(8), Inches(1)
    ).table
    for col, text in enumerate(cell_texts):
        table.cell(0, col).text = text
    if notes:
        slide.notes_slide.notes_text_frame.text = notes
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def schema_slides(deck: bytes) -> List[SlideSchema]:
    """Parse a deck and return its persisted-style ``schema_slides`` list."""
    return parse(deck).slides


def image_schema(
    deck: bytes, *, slide: int, key: str, tag_id: str = "tag-xyz"
) -> List[SlideSchema]:
    """Parse a deck and stamp a resolved ``folder_tag_id`` on one image key.

    The save-time processor is what resolves the folder to a tag id; here we set
    it directly on the parsed schema so the fill tool sees the same persisted
    shape it would after a real save.
    """
    slides = parse(deck).slides
    for slide_schema in slides:
        if slide_schema.slide != slide:
            continue
        for key_field in slide_schema.keys:
            if key_field.key == key:
                key_field.folder_tag_id = tag_id
    return slides


def png_bytes(width: int = 10, height: int = 10, color: str = "red") -> bytes:
    """A tiny, valid PNG with the given pixel dimensions (no checked-in binaries)."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def webp_bytes(width: int = 10, height: int = 10, color: str = "red") -> bytes:
    """A tiny, valid WEBP. Pillow decodes it but python-pptx's ``add_picture``
    cannot embed WEBP, so the fill tool must transcode it to PNG first."""
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="WEBP")
    return buffer.getvalue()


def picture_shapes(slide) -> list:
    """Every PICTURE shape on a slide (python-pptx exposes ``shape_type`` PICTURE)."""
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    return [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]


def add_fixture(presentation, container, left, top, width, height) -> None:
    """Put a non-placeholder shape on a slide layout or master.

    That is how a template carries its logo, its band or its footer: the shape
    is INHERITED by every slide using the layout. python-pptx cannot draw on a
    layout or a master directly, so the shape is built on a scratch slide and
    its element moved over.
    """
    from pptx.enum.shapes import MSO_SHAPE

    scratch = presentation.slides.add_slide(presentation.slide_layouts[6])
    element = scratch.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, height
    )._element
    element.getparent().remove(element)
    container.shapes._spTree.append(element)
    slide_ids = presentation.slides._sldIdLst
    scratch_id = list(slide_ids)[-1]
    presentation.part.drop_rel(scratch_id.rId)
    slide_ids.remove(scratch_id)


#: The house style of `build_house_style_template`, so tests assert against one
#: source rather than repeating magic numbers.
HOUSE_CORNER = 0.2
HOUSE_GAP_IN = 0.3
HOUSE_INSET_IN = 0.2


def build_house_style_template():
    """A template with opinions: outlined cards, round corners, wide insets,
    a measurable gap between columns, and figures written UNDER their label.

    None of that is what the capability would choose on its own, which is the
    point: composing in this template's language means reading it back.
    """
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_SHAPE
    from pptx.util import Inches, Pt

    presentation = Presentation()
    slide = presentation.slides.add_slide(presentation.slide_layouts[5])
    slide.shapes.title.text = "How this house draws"

    width, height, top = Inches(2.6), Inches(2.0), Inches(2.0)
    for index in range(3):
        left = Inches(0.5 + index * (2.6 + HOUSE_GAP_IN))
        card = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
        )
        card.adjustments[0] = HOUSE_CORNER
        card.fill.background()
        card.line.color.rgb = RGBColor(0x33, 0x33, 0x33)
        card.text_frame.margin_left = Inches(HOUSE_INSET_IN)
        card.text_frame.text = f"Pillar {index}"
        card.text_frame.paragraphs[0].runs[0].font.size = Pt(16)

    # The figure goes UNDER the words that name it.
    label = slide.shapes.add_textbox(Inches(0.5), Inches(4.6), Inches(2.6), Inches(0.4))
    label.text_frame.text = "Conversion"
    figure = slide.shapes.add_textbox(
        Inches(0.5), Inches(5.1), Inches(2.6), Inches(0.7)
    )
    figure.text_frame.text = "62%"
    return presentation


def build_cover_only_template():
    """A template shaped like a real corporate one that went wrong: its only
    placeholders sit on a COVER and a CONTACT slide, both a narrow column on
    the right. Nothing in it says where content goes.

    This is the shape that produced a deck of title slides: the content band
    was read off the cover, and no card fitted in it.
    """
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = Inches(13.333), Inches(7.5)
    # Only a cover layout and a blank one, like the template that failed: no
    # layout in it says where content goes.
    master = presentation.slide_masters[0]
    keep = {presentation.slide_layouts[0].name, presentation.slide_layouts[6].name}
    id_list = master._element.get_or_add_sldLayoutIdLst()
    for entry, layout in zip(list(id_list), list(master.slide_layouts)):
        if layout.name not in keep:
            id_list.remove(entry)
    for text in ("Cover", "Contact"):
        slide = presentation.slides.add_slide(presentation.slide_layouts[0])
        title, subtitle = slide.shapes.title, slide.placeholders[1]
        for shape in (title, subtitle):
            shape.left, shape.width = Inches(8.0), Inches(4.5)
        title.top, title.height = Inches(2.2), Inches(1.2)
        subtitle.top, subtitle.height = Inches(3.6), Inches(2.0)
        title.text = text
        subtitle.text_frame.text = "one line"
    return presentation


ICON_NAMES = [
    "Inclusion",
    "Autonomie",
    "Communautes",
    "Observabilite",
    "Empreintes",
]


def build_icon_bank_template():
    """A template carrying a bank of NAMED icons, the way a real charter does.

    The bank is a slide of pictures and nothing else — the shape the analysis
    already recognises and excludes from rendering. Naming them is what makes
    them usable: an icon called "Picture 12" cannot be asked for.
    """
    import io as _io

    from PIL import Image
    from pptx import Presentation
    from pptx.util import Inches

    presentation = Presentation()
    presentation.slide_width, presentation.slide_height = Inches(13.333), Inches(7.5)
    content = presentation.slides.add_slide(presentation.slide_layouts[1])
    content.shapes.title.text = "Content"
    content.placeholders[1].text_frame.text = "A line of body text"

    bank = presentation.slides.add_slide(presentation.slide_layouts[6])
    buffer = _io.BytesIO()
    Image.new("RGB", (64, 64), (20, 90, 160)).save(buffer, format="PNG")
    for index in range(24):
        buffer.seek(0)
        picture = bank.shapes.add_picture(
            buffer,
            Inches(0.3 + (index % 8) * 1.6),
            Inches(0.6 + (index // 8) * 1.6),
            Inches(0.9),
            Inches(0.9),
        )
        if index < len(ICON_NAMES):
            picture._element.find(
                ".//{http://schemas.openxmlformats.org/presentationml/2006/main}cNvPr"
            ).set("descr", ICON_NAMES[index])
    return presentation
