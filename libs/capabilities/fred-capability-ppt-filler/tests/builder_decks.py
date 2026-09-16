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

"""In-code synthetic templates for the builder tests (no checked-in binaries).

Each builder returns ``.pptx`` bytes. ``build_showcase_template`` assembles the
example-slide cases the analysis rules are written for: an agenda of numbered
groups, KPI cards, a team roster, a process, sample-text boxes, shared
footers, an icon bank, a chart, a table, declared shape names, an ``intent:``
note and a purely decorative divider.
"""

from __future__ import annotations

import io
from typing import Any, List, Optional, cast

from deck_builders import png_bytes
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

# python-pptx default template layout indices.
(
    L_TITLE,
    L_CONTENT,
    L_SECTION,
    L_TWO,
    L_COMPARISON,
    L_TITLE_ONLY,
    L_BLANK,
    L_CAPTION,
    L_PICTURE,
) = range(9)

FOOTER = "Confidential - internal use only"
FONT_HEADING = Pt(20)
FONT_BODY = Pt(12)
FONT_NUMBER = Pt(48)


def _save(presentation) -> bytes:
    buffer = io.BytesIO()
    presentation.save(buffer)
    return buffer.getvalue()


def _textbox(
    shapes,
    x: float,
    y: float,
    w: float,
    h: float,
    text: str,
    size=None,
    name: Optional[str] = None,
):
    box = shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    box.text_frame.text = text
    if size is not None:
        for paragraph in box.text_frame.paragraphs:
            for run in paragraph.runs:
                run.font.size = size
    if name:
        box.name = name
    return box


def _footer(slide) -> None:
    _textbox(slide.shapes, 0.5, 7.0, 6.0, 0.3, FOOTER, Pt(8))


def _set_title(slide, title: str) -> None:
    cast(Any, slide.shapes.title).text = title


def _titled(presentation, title: str):
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_TITLE_ONLY])
    _set_title(slide, title)
    return slide


def add_agenda_slide(presentation, count: int = 4):
    """Title + N groups of (number, heading) laid out on a grid."""
    slide = _titled(presentation, "Agenda")
    for index in range(count):
        col, row = index % 2, index // 2
        group = slide.shapes.add_group_shape()
        x, y = 0.6 + col * 4.6, 1.8 + row * 2.4
        _textbox(group.shapes, x, y, 1.0, 0.6, f"0{index + 1}", FONT_NUMBER)
        _textbox(
            group.shapes,
            x,
            y + 0.8,
            4.0,
            0.9,
            "Titre du chapitre sur une a deux lignes",
            FONT_HEADING,
        )
    _footer(slide)
    return slide


def add_kpi_slide(presentation, count: int = 4):
    """Title + N groups of (value, label); the icon of each card sits over the
    card but outside its group, as designers do."""
    slide = _titled(presentation, "Key figures")
    for index in range(count):
        group = slide.shapes.add_group_shape()
        x = 0.5 + index * 2.3
        _textbox(group.shapes, x, 1.6, 1.6, 0.2, "", None)
        _textbox(group.shapes, x, 2.6, 1.6, 1.0, f"{60 + index * 10}%", FONT_NUMBER)
        _textbox(group.shapes, x, 3.7, 1.6, 0.35, f"KPI #{index + 1}", FONT_BODY)
        slide.shapes.add_picture(
            io.BytesIO(png_bytes(12, 12)),
            Inches(x + 0.2),
            Inches(1.9),
            Inches(0.4),
            Inches(0.4),
        )
    _footer(slide)
    return slide


def add_steps_slide(presentation, count: int = 3):
    slide = _titled(presentation, "Process")
    for index in range(count):
        group = slide.shapes.add_group_shape()
        x = 0.5 + index * 3.1
        _textbox(group.shapes, x, 1.6, 0.8, 1.2, str(index + 1), FONT_NUMBER)
        _textbox(group.shapes, x, 3.0, 2.8, 0.5, f"Etape {index + 1}", FONT_HEADING)
        _textbox(group.shapes, x, 3.6, 2.8, 2.5, "Changez ce texte", FONT_BODY)
    return slide


def add_team_slide(presentation, count: int = 6):
    slide = _titled(presentation, "Team")
    for index in range(count):
        col, row = index % 3, index // 3
        group = slide.shapes.add_group_shape()
        x, y = 0.5 + col * 3.1, 1.8 + row * 2.6
        _textbox(group.shapes, x, y, 2.0, 0.3, "Poste en une ligne", Pt(9))
        _textbox(group.shapes, x, y + 0.35, 2.0, 0.3, "Nom", Pt(9))
    return slide


def add_free_text_slide(presentation):
    """Free boxes: one sample text (zone), one real content label (not a zone)."""
    slide = _titled(presentation, "Free text")
    _textbox(
        slide.shapes, 0.5, 1.5, 8.0, 4.0, "Cliquez ici pour ajouter du texte", Pt(18)
    )
    _textbox(slide.shapes, 0.5, 6.2, 3.0, 0.4, "Source: annual report 2025", Pt(10))
    _footer(slide)
    return slide


def add_declared_slide(presentation):
    """Shape names from the Selection pane declare roles; a `keep` name hides a box."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_BLANK])
    _textbox(slide.shapes, 0.5, 0.5, 9.0, 1.0, "Quarterly review", Pt(28), name="title")
    _textbox(
        slide.shapes,
        0.5,
        1.8,
        9.0,
        3.5,
        "Some real looking paragraph of content.",
        Pt(14),
        name="body_main",
    )
    _textbox(slide.shapes, 0.5, 6.0, 4.0, 0.5, "Do not touch me", Pt(10), name="keep")
    slide.notes_slide.notes_text_frame.text = "intent: statement"
    return slide


def add_icon_bank_slide(presentation, pictures: int = 24):
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_BLANK])
    _textbox(slide.shapes, 0.3, 3.0, 2.0, 0.5, "1/3", Pt(24))
    for index in range(pictures):
        col, row = index % 8, index // 8
        slide.shapes.add_picture(
            io.BytesIO(png_bytes(8, 8)),
            Inches(2.5 + col * 0.9),
            Inches(1.0 + row * 1.2),
            Inches(0.5),
            Inches(0.5),
        )
    return slide


def add_chart_slide(presentation):
    slide = _titled(presentation, "Chart")
    data = CategoryChartData()
    data.categories = ["A", "B"]
    data.add_series("S", (1, 2))
    slide.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED,
        Inches(1),
        Inches(1.5),
        Inches(7),
        Inches(5),
        data,
    )
    return slide


def add_table_slide(presentation):
    slide = _titled(presentation, "Table")
    slide.shapes.add_table(3, 3, Inches(1), Inches(1.5), Inches(8), Inches(4))
    return slide


def add_divider_slide(presentation):
    """Title-only instance of a title+body layout, over a large graphic."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_CONTENT])
    _set_title(slide, "Motif")
    body = cast(Any, slide.placeholders[1])
    body._element.getparent().remove(body._element)
    for top in (4.0, 5.2):
        slide.shapes.add_picture(
            io.BytesIO(png_bytes(40, 4)),
            Inches(0),
            Inches(top),
            Inches(10),
            Inches(0.8),
        )
    return slide


def add_pure_instance_slide(presentation):
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_CONTENT])
    _set_title(slide, "Cliquez ici pour modifier le titre")
    cast(
        Any, slide.placeholders[1]
    ).text_frame.text = "Cliquez ici pour ajouter du texte"
    return slide


def add_big_picture_slide(presentation):
    slide = _titled(presentation, "Photo")
    slide.shapes.add_picture(
        io.BytesIO(png_bytes(40, 40)), Inches(0.5), Inches(1.5), Inches(9), Inches(5)
    )
    return slide


def add_scaled_kpi_slide(presentation):
    """KPI cards whose groups were resized after authoring (ext = chExt / 2),
    the first label box narrower than its siblings."""
    slide = _titled(presentation, "Scaled figures")
    for index in range(3):
        group = slide.shapes.add_group_shape()
        x = 0.5 + index * 3.0
        _textbox(group.shapes, x, 2.0, 1.6, 1.0, f"{10 + index}%", FONT_NUMBER)
        _textbox(
            group.shapes,
            x,
            3.2,
            0.7 if index == 0 else 1.6,
            0.35,
            f"KPI #{index + 1}",
            FONT_BODY,
        )
        # Shrink the group's placement without touching its child space.
        group.width = int(group.width / 2)
        group.height = int(group.height / 2)
    return slide


def add_notes_without_body_slide(presentation):
    """A notes slide whose body placeholder was deleted (no text frame)."""
    slide = _titled(presentation, "Silent notes")
    _textbox(
        slide.shapes, 0.5, 1.5, 8.0, 3.0, "Cliquez ici pour ajouter du texte", Pt(18)
    )
    notes = slide.notes_slide
    for shape in list(notes.placeholders):
        if (
            shape.placeholder_format.type is not None
            and shape.placeholder_format.type.name == "BODY"
        ):
            shape._element.getparent().remove(shape._element)
    return slide


def add_two_group_columns_slide(presentation):
    """Two grouped columns (heading + body): two siblings, not a list."""
    slide = _titled(presentation, "Two columns")
    for index in range(2):
        group = slide.shapes.add_group_shape()
        x = 0.5 + index * 4.6
        _textbox(group.shapes, x, 1.6, 4.0, 0.5, "Changez ce titre", FONT_HEADING)
        _textbox(group.shapes, x, 2.3, 4.0, 3.5, "Changez ce texte", FONT_BODY)
    return slide


def build_showcase_template() -> bytes:
    presentation = Presentation()
    add_agenda_slide(presentation)
    add_kpi_slide(presentation)
    add_steps_slide(presentation)
    add_team_slide(presentation)
    add_free_text_slide(presentation)
    add_declared_slide(presentation)
    add_icon_bank_slide(presentation)
    add_chart_slide(presentation)
    add_table_slide(presentation)
    add_divider_slide(presentation)
    add_pure_instance_slide(presentation)
    add_big_picture_slide(presentation)
    add_scaled_kpi_slide(presentation)
    add_notes_without_body_slide(presentation)
    add_two_group_columns_slide(presentation)
    return _save(presentation)


def add_cover_photo_slide(presentation):
    """A full-bleed photo with the title written over it: the picture is drawn
    first, so replacing it must not bring it in front of the text."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_BLANK])
    slide.shapes.add_picture(
        io.BytesIO(png_bytes(64, 36)),
        Inches(0),
        Inches(0),
        Inches(10),
        Inches(7.5),
    )
    _textbox(slide.shapes, 0.8, 2.5, 6.0, 1.2, "Changez ce titre", Pt(36))
    return slide


def build_layouts_only_template() -> bytes:
    return _save(Presentation())


def build_spaced_template(
    space_before_pt: int = 24, no_wrap_title: bool = True
) -> bytes:
    """A deck whose layout declares body line spacing and space before each
    paragraph — the shape of a corporate master — plus a figure that does not
    wrap. Both are read off the layout, never off the slide's own text.
    """
    presentation = Presentation()
    layout = presentation.slide_layouts[L_CONTENT]
    for placeholder in layout.placeholders:
        if placeholder.placeholder_format.idx == 0:
            body = placeholder.text_frame._txBody.find(qn("a:bodyPr"))
            if no_wrap_title:
                # Sized to its text, the way a designer sets a figure.
                body.set("wrap", "none")
            else:
                # Wraps inside its width and grows downwards - a cover title.
                body.set("wrap", "square")
                body.append(body.makeelement(qn("a:spAutoFit"), {}))
            continue
        body = placeholder.text_frame._txBody
        lst = body.makeelement(qn("a:lstStyle"), {})
        lvl = body.makeelement(qn("a:lvl1pPr"), {})
        spacing = body.makeelement(qn("a:lnSpc"), {})
        spacing.append(body.makeelement(qn("a:spcPct"), {"val": "114000"}))
        before = body.makeelement(qn("a:spcBef"), {})
        before.append(
            body.makeelement(qn("a:spcPts"), {"val": str(space_before_pt * 100)})
        )
        lvl.append(spacing)
        lvl.append(before)
        lst.append(lvl)
        body.insert(1, lst)

    slide = presentation.slides.add_slide(layout)
    _set_title(slide, "Changez ce titre")
    for placeholder in slide.placeholders:
        if placeholder.placeholder_format.idx != 0:
            cast(Any, placeholder).text_frame.text = "Changez ce texte"
    _footer(slide)
    return _save(presentation)


def build_slides(builders: List) -> bytes:
    presentation = Presentation()
    for builder in builders:
        builder(presentation)
    return _save(presentation)


__all__ = [name for name in globals() if name.startswith(("add_", "build_"))] + [
    "FOOTER",
    "Emu",
]
