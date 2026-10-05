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

"""Template analysis rules, each on the synthetic slide written for it, plus the
reference corporate template (optional, `PPT_BUILDER_REFERENCE_TEMPLATE`)."""

from __future__ import annotations

import io
import os
from typing import Any, cast

import pytest
from builder_decks import (
    FOOTER,
    L_TITLE,
    L_TITLE_ONLY,
    add_agenda_slide,
    add_divider_slide,
    build_layouts_only_template,
    build_showcase_template,
    build_slides,
    build_spaced_template,
)
from fred_capability_ppt_filler.builder.analysis import (
    ANALYSIS_VERSION,
    FrameMetrics,
    analyze_template,
    estimate_capacity,
)
from fred_capability_ppt_filler.builder.lexicon import (
    is_sample_text,
    role_from_shape_name,
)
from fred_capability_ppt_filler.builder.models import Box, TemplateInventory
from lxml import etree  # pyright: ignore[reportAttributeAccessIssue]
from pptx import Presentation
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Inches


@pytest.fixture(scope="module")
def showcase() -> TemplateInventory:
    result = analyze_template(build_showcase_template())
    assert result.errors == []
    assert result.inventory is not None
    return result.inventory


def _slide(inventory: TemplateInventory, label: str):
    matches = [
        p for p in inventory.patterns if p.source == "slide" and p.label == label
    ]
    assert matches, (
        f"no slide pattern labelled {label!r}: {[p.label for p in inventory.patterns]}"
    )
    return matches[0]


def _layout(inventory: TemplateInventory, name: str):
    return next(
        p for p in inventory.patterns if p.source == "layout" and p.name == name
    )


# --- layouts -----------------------------------------------------------------


def test_default_layouts_classify_by_placeholder_signature():
    inventory = analyze_template(build_layouts_only_template()).inventory
    assert inventory is not None
    kinds = {p.name: p.kind for p in inventory.patterns}
    assert kinds["Title Slide"] == "cover"
    assert kinds["Title and Content"] == "bullets"
    assert kinds["Section Header"] == "section"
    assert kinds["Two Content"] == "two_columns"
    assert kinds["Comparison"] == "comparison"
    assert kinds["Picture with Caption"] == "image_text"
    assert all(p.labelled_by == "heuristic" for p in inventory.patterns)
    blank = _layout(inventory, "Blank")
    assert not blank.included and blank.exclusion_reason == "no_placeholder"


def test_layout_zones_carry_roles_and_capacity():
    inventory = analyze_template(build_layouts_only_template()).inventory
    assert inventory is not None
    content = _layout(inventory, "Title and Content")
    roles = {z.key: z.role for z in content.zones}
    assert roles == {"ph:0": "title", "ph:1": "body"}
    body = next(z for z in content.zones if z.role == "body")
    # Inherited from the master body style (32 pt in the default template).
    assert body.font_pt == 32
    assert body.max_chars and body.max_chars > 200
    assert body.max_lines and body.max_lines >= 5


# --- example slides -----------------------------------------------------------


def test_agenda_groups_become_a_numbered_list(showcase):
    agenda = _slide(showcase, "Agenda")
    assert agenda.kind == "agenda"
    assert [z.role for z in agenda.zones] == ["title"]
    (group,) = agenda.groups
    assert group.count == 4
    assert group.item_zones == ["number", "heading"]
    assert [z.sample for z in group.items[0]] == [
        "01",
        "Titre du chapitre sur une a deux lignes",
    ]
    assert len(group.item_keys) == 4


def test_kpi_groups_are_figures_with_number_and_label(showcase):
    kpi = _slide(showcase, "Key figures")
    assert kpi.kind == "figures"
    (group,) = kpi.groups
    assert group.count == 4
    assert group.item_zones == ["number", "label"]


def test_sequential_numbers_with_text_make_a_process(showcase):
    steps = _slide(showcase, "Process")
    assert steps.kind == "process"
    (group,) = steps.groups
    assert group.item_zones == ["number", "heading", "body"]


def test_same_font_pairs_read_heading_then_label(showcase):
    team = _slide(showcase, "Team")
    assert team.kind == "team"
    (group,) = team.groups
    assert group.count == 6
    assert group.item_zones == ["heading", "label"]


def test_every_free_text_box_is_a_zone_sample_or_not(showcase):
    free = _slide(showcase, "Free text")
    roles = {z.sample: z.role for z in free.zones}
    assert roles["Cliquez ici pour ajouter du texte"] == "body"
    assert roles["Source: annual report 2025"] == "label"
    assert free.kind == "bullets"


def test_shared_footer_is_never_a_zone(showcase):
    assert FOOTER in showcase.shared_texts
    for pattern in showcase.patterns:
        assert all(z.sample != FOOTER for z in pattern.zones)


def test_shape_names_and_kind_note_override_heuristics(showcase):
    declared = _slide(showcase, "Quarterly review")
    roles = {z.role for z in declared.zones}
    assert roles == {"title", "body"}
    assert all(z.sample != "Do not touch me" for z in declared.zones)
    # The legacy `intent: statement` directive still reads as a quote.
    assert declared.kind == "quote"


def test_icon_bank_chart_and_table_are_excluded_by_default(showcase):
    by_reason = {
        p.exclusion_reason: p
        for p in showcase.patterns
        if not p.included and p.source == "slide"
    }
    assert set(by_reason) == {"icon_bank", "chart", "table"}
    assert by_reason["chart"].label == "Chart"
    assert by_reason["table"].label == "Table"


def test_title_only_over_graphics_is_decoration(showcase):
    divider = _slide(showcase, "Motif")
    assert divider.kind == "other" and not divider.reusable


def test_pure_layout_instance_is_folded_into_its_layout(showcase):
    labels = [p.label for p in showcase.patterns if p.source == "slide"]
    assert not any(label.startswith("Title and Content (") for label in labels)


def test_large_free_picture_is_a_replaceable_image(showcase):
    photo = _slide(showcase, "Photo")
    assert [z.role for z in photo.zones] == ["title", "image"]
    assert photo.kind == "image_text"


def test_example_slide_of_an_existing_kind_is_preferred(showcase):
    photo = _slide(showcase, "Photo")
    assert photo.preferred  # the default template has a Picture with Caption layout
    agenda = _slide(showcase, "Agenda")
    assert not agenda.preferred


def test_decorative_slide_is_never_preferred():
    # Used verbatim, a decorative example would otherwise outrank the closing layout.
    def name_blank_layout_merci(presentation):
        presentation.slide_layouts[6]._element.cSld.set("name", "Merci")

    inventory = analyze_template(
        build_slides([name_blank_layout_merci, add_agenda_slide, add_divider_slide])
    ).inventory
    assert inventory is not None
    merci = _layout(inventory, "Merci")
    assert merci.kind == "closing" and merci.included and merci.reusable
    motif = _slide(inventory, "Motif")
    assert motif.kind == "other" and not motif.preferred


def test_example_slide_placeholders_inherit_their_font_size(showcase):
    agenda = _slide(showcase, "Agenda")
    title = next(z for z in agenda.zones if z.role == "title")
    # Inherited from the master title style (44 pt in the default template),
    # so the capacity the catalogue quotes is the real one.
    assert title.font_pt == 44
    assert title.max_chars and title.max_chars < 40


def test_notes_without_body_placeholder_do_not_abort_the_analysis(showcase):
    silent = _slide(showcase, "Silent notes")
    assert silent.kind == "bullets"


def test_two_sibling_groups_are_columns_not_a_list(showcase):
    two = _slide(showcase, "Two columns")
    assert two.groups == []
    assert two.kind == "comparison"
    assert sorted(z.role for z in two.zones) == [
        "body",
        "body",
        "heading",
        "heading",
        "title",
    ]


def test_summary_counts(showcase):
    summary = showcase.summary()
    assert summary.layouts == 11
    assert summary.excluded == 4  # Blank layout + icon bank + chart + table
    assert summary.fixed == 1
    assert (
        summary.patterns
        == summary.layouts + summary.slides - summary.excluded - summary.fixed
    )


def test_unreadable_upload_is_one_error():
    result = analyze_template(b"not a pptx")
    assert result.inventory is None
    assert [e.code for e in result.errors] == ["invalid_upload"]


# --- lexicon -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Cliquez ici pour modifier le titre", True),
        ("CHANGEZ CE TEXTE", True),
        ("Titre du chapitre sur une à deux lignes", True),
        ("Lorem ipsum dolor", True),
        ("Nom", True),
        ("Revenue grew 12 % in 2025", False),
        ("Texte et images", False),
        ("3 icônes + texte", False),
    ],
)
def test_sample_text_lexicon(text, expected):
    assert is_sample_text(text) is expected


@pytest.mark.parametrize(
    "name,expected",
    [
        ("TextBox 12", None),
        ("Title 1", None),
        ("Image 44", None),
        ("Titre 3", None),
        ("title", "title"),
        ("Sous_titre", "subtitle"),
        ("heading_2", "heading"),
        ("image-main", "image"),
        ("keep", "keep"),
    ],
)
def test_shape_name_declarations(name, expected):
    assert role_from_shape_name(name) == expected


# --- reference template -------------------------------------------------------------

REFERENCE = os.environ.get("PPT_BUILDER_REFERENCE_TEMPLATE")

# label -> (kind, group count, item roles) for the reference corporate deck.
REFERENCE_EXPECTATIONS = {
    "SOMMAIRE": ("agenda", 8, ["number", "heading"]),
    "Indicateurs de performance / chiffres clés": ("figures", 4, ["number", "label"]),
    "3 icônes + texte": ("cards", 3, ["body"]),
    "Planche de processus": ("process", 3, ["number", "heading", "body"]),
    "Timeline jusqu’à 6 ans": ("timeline", 6, ["number", "heading", "body"]),
    "Equipe": ("team", 22, ["heading", "label"]),
}

_reference = pytest.mark.skipif(
    not REFERENCE or not os.path.exists(REFERENCE or ""),
    reason="reference template not provided",
)


@_reference
def test_reference_template_free_form_slides():
    inventory = analyze_template(open(REFERENCE, "rb").read()).inventory  # type: ignore[arg-type]
    assert inventory is not None
    by_label = {}
    for pattern in inventory.patterns:
        by_label.setdefault(pattern.label, pattern)
    for label, (kind, count, roles) in REFERENCE_EXPECTATIONS.items():
        pattern = by_label[label]
        assert pattern.kind == kind, label
        assert pattern.groups[0].count == count, label
        assert pattern.groups[0].item_zones == roles, label
    layouts = {p.name: p.kind for p in inventory.patterns if p.source == "layout"}
    assert layouts["Couverture"] == "cover"
    assert layouts["Slide chapitre"] == "section"
    assert layouts["2 colonnes de texte"] == "two_columns"
    assert layouts["Bullet Points"] == "comparison"
    assert layouts["Contact"] == "closing"
    assert layouts["Merci"] == "closing"
    excluded = {p.exclusion_reason for p in inventory.patterns if not p.included}
    assert excluded == {"chart", "table", "icon_bank"}


@_reference
def test_reference_template_has_no_title_only_example_with_real_text():
    """Every text shape of an example slide is a slot, so no slide carrying
    text beside its title is reduced to its title."""
    source = open(REFERENCE, "rb").read()  # type: ignore[arg-type]
    inventory = analyze_template(source).inventory
    assert inventory is not None
    shared = set(inventory.shared_texts)
    for slide in Presentation(io.BytesIO(source)).slides:
        pattern = inventory.pattern(f"slide:{slide.slide_id}")
        if pattern is None or not pattern.included:
            continue
        texts = [
            text
            for shape in slide.shapes
            if shape.has_text_frame
            and (text := cast(Any, shape).text_frame.text.strip())
            and text not in shared
        ]
        slots = len([z for z in pattern.zones if z.role != "image"]) + sum(
            g.count for g in pattern.groups
        )
        if len(texts) > 1:
            assert slots > 1, pattern.label
            assert pattern.kind not in ("cover", "section") or not pattern.groups


# --- every text shape is a slot ------------------------------------------------


def _real_text_slide(presentation):
    """Real corporate text on a cover-typed layout: content, not a cover."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_TITLE])
    cast(Any, slide.shapes.title).text = "Revenue grew in every region"
    cast(Any, slide.placeholders[1]).text_frame.text = "Fiscal year 2025"
    for index, text in enumerate(
        (
            "Europe up 12 % on the back of the new rail contracts",
            "Asia up 8 % with two new plants opened in the spring",
            "Americas flat after the end of the legacy programme",
        )
    ):
        box = slide.shapes.add_textbox(
            Inches(0.5 + index * 3.1), Inches(4.5), Inches(2.9), Inches(1.5)
        )
        box.text_frame.text = text
    return slide


def _numbered_slide(
    presentation,
    footer: str = "Group strategy 2026",
    text: str = "Margins recover in the second half",
):
    """A footer repeated on two slides and a slide-number field: chrome."""
    slide = presentation.slides.add_slide(presentation.slide_layouts[L_TITLE_ONLY])
    cast(Any, slide.shapes.title).text = "Outlook"
    body = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9), Inches(4))
    body.text_frame.text = text
    slide.shapes.add_textbox(
        Inches(0.5), Inches(7.0), Inches(4), Inches(0.3)
    ).text_frame.text = footer
    number = slide.shapes.add_textbox(Inches(9), Inches(7.0), Inches(0.5), Inches(0.3))
    paragraph = number.text_frame.paragraphs[0]._p
    field = etree.SubElement(paragraph, qn("a:fld"), id="{1}", type="slidenum")
    etree.SubElement(field, qn("a:t")).text = "2"
    return slide


def test_real_text_slide_is_all_slots_and_never_a_cover():
    inventory = analyze_template(build_slides([_real_text_slide])).inventory
    assert inventory is not None
    pattern = _slide(inventory, "Revenue grew in every region")
    samples = {z.sample for z in pattern.zones}
    assert "Fiscal year 2025" in samples
    assert "Asia up 8 % with two new plants opened in the spring" in samples
    assert pattern.kind not in ("cover", "section")
    assert pattern.reusable


def test_twice_repeated_text_and_number_fields_are_not_slots():
    texts = ("Margins recover in the second half", "Cash stays above target")
    inventory = analyze_template(
        build_slides([lambda p, t=t: _numbered_slide(p, text=t) for t in texts])
    ).inventory
    assert inventory is not None
    assert "Group strategy 2026" in inventory.shared_texts
    slides = [p for p in inventory.patterns if p.source == "slide"]
    assert len(slides) == 2
    for pattern, text in zip(slides, texts):
        samples = [z.sample for z in pattern.zones]
        assert "Group strategy 2026" not in samples and "2" not in samples
        assert text in samples


def test_a_link_to_another_slide_does_not_block_copying():
    def linked(presentation):
        agenda = add_agenda_slide(presentation)
        target = _numbered_slide(presentation, footer="Only once")
        agenda.part.relate_to(target.part, RT.SLIDE)

    inventory = analyze_template(build_slides([linked])).inventory
    assert inventory is not None
    agenda = _slide(inventory, "Agenda")
    assert agenda.included and agenda.exclusion_reason is None


def test_analysis_version_is_stamped():
    inventory = analyze_template(build_layouts_only_template()).inventory
    assert inventory is not None and inventory.analysis_version == ANALYSIS_VERSION


# --- capacity: the room the agent is promised is the room the renderer has ---


def _capacity(**frame) -> tuple[int, int]:
    return estimate_capacity(
        Box(x=0, y=0, w=400, h=300),
        18.0,
        "body",
        Inches(13.333).emu,
        Inches(7.5).emu,
        frame=FrameMetrics(**frame),
    )


def test_capacity_pays_the_paragraph_spacing_the_template_declares():
    """A body style with 114 % line spacing and 16 pt before each bullet holds
    barely half the bullets a bare line height would promise."""
    bare = _capacity(line_spacing=1.0, space_before_pt=0.0)
    spaced = _capacity(line_spacing=1.14, space_before_pt=16.0)
    assert spaced[1] * 2 <= bare[1]
    assert spaced[0] < bare[0]


def test_capacity_takes_the_padding_off_the_box():
    flush = _capacity(lr_inset=0, tb_inset=0)
    padded = _capacity(lr_inset=Inches(1).emu, tb_inset=Inches(1).emu)
    assert padded[0] < flush[0]
    assert padded[1] < flush[1]


def test_capacity_does_not_hand_out_the_room_wrapping_wastes():
    """Characters × lines is not reachable: every line break loses part of a word."""
    per_line, _ = _capacity(lr_inset=0, tb_inset=0, line_spacing=1.0)
    one_line = estimate_capacity(
        Box(x=0, y=0, w=400, h=40),
        18.0,
        "title",
        Inches(13.333).emu,
        Inches(7.5).emu,
        frame=FrameMetrics(lr_inset=0, tb_inset=0),
    )
    chars, lines = _capacity(lr_inset=0, tb_inset=0)
    assert lines > 1
    assert chars < one_line[0] * lines


def test_analysis_reads_the_line_spacing_a_layout_declares():
    """The spacing lives on the layout's placeholder, not on the slide's text."""
    plain = analyze_template(build_spaced_template(space_before_pt=0)).inventory
    spaced = analyze_template(build_spaced_template(space_before_pt=24)).inventory
    assert plain is not None and spaced is not None

    def body_lines(inventory) -> int:
        lines = [
            z.max_lines
            for p in inventory.patterns
            for z in p.zones
            if z.role == "body" and z.max_lines
        ]
        assert lines
        return sum(lines)

    assert body_lines(spaced) < body_lines(plain)


def test_a_box_that_does_not_wrap_is_marked_as_growing():
    """Its width follows its text, so no character limit can be quoted for it."""
    inventory = analyze_template(build_spaced_template(space_before_pt=0)).inventory
    assert inventory is not None
    zones = [z for p in inventory.patterns for z in p.zones]
    assert [z for z in zones if z.grows], "the no-wrap heading should be marked"
    assert all(z.max_chars for z in zones if not z.grows and z.role != "image")
