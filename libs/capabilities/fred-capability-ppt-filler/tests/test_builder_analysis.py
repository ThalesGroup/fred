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

import os

import pytest
from builder_decks import (
    FOOTER,
    build_layouts_only_template,
    build_showcase_template,
)
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.lexicon import (
    is_sample_text,
    role_from_shape_name,
)
from fred_capability_ppt_filler.builder.models import TemplateInventory


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
    intents = {p.name: p.intent for p in inventory.patterns}
    assert intents["Title Slide"] == "title"
    assert intents["Title and Content"] == "content"
    assert intents["Section Header"] == "section"
    assert intents["Two Content"] == "two_columns"
    assert intents["Comparison"] == "comparison"
    assert intents["Picture with Caption"] == "image_text"
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
    assert agenda.intent == "agenda"
    assert [z.role for z in agenda.zones] == ["title"]
    (group,) = agenda.groups
    assert group.count == 4
    assert group.item_zones == ["number", "heading"]
    assert [z.sample for z in group.items[0]] == [
        "01",
        "Titre du chapitre sur une a deux lignes",
    ]
    assert len(group.item_keys) == 4


def test_kpi_groups_are_cards_with_number_and_label(showcase):
    kpi = _slide(showcase, "Key figures")
    assert kpi.intent == "cards"
    (group,) = kpi.groups
    assert group.count == 4
    assert group.item_zones == ["number", "label"]


def test_sequential_numbers_make_steps(showcase):
    steps = _slide(showcase, "Process")
    assert steps.intent == "steps"
    (group,) = steps.groups
    assert group.item_zones == ["number", "heading", "body"]


def test_same_font_pairs_read_heading_then_label(showcase):
    team = _slide(showcase, "Team")
    assert team.intent == "cards"
    (group,) = team.groups
    assert group.count == 6
    assert group.item_zones == ["heading", "label"]


def test_free_sample_text_is_a_zone_and_real_text_is_not(showcase):
    free = _slide(showcase, "Free text")
    roles = {z.sample: z.role for z in free.zones}
    assert roles["Cliquez ici pour ajouter du texte"] == "body"
    assert "Source: annual report 2025" not in roles
    assert free.intent == "content"


def test_shared_footer_is_never_a_zone(showcase):
    assert FOOTER in showcase.shared_texts
    for pattern in showcase.patterns:
        assert all(z.sample != FOOTER for z in pattern.zones)


def test_shape_names_and_intent_note_override_heuristics(showcase):
    declared = _slide(showcase, "Quarterly review")
    roles = {z.role for z in declared.zones}
    assert roles == {"title", "body"}
    assert all(z.sample != "Do not touch me" for z in declared.zones)
    assert declared.intent == "statement"


def test_icon_bank_chart_and_table_are_excluded_by_default(showcase):
    by_reason = {
        p.exclusion_reason: p
        for p in showcase.patterns
        if not p.included and p.source == "slide"
    }
    assert set(by_reason) == {"icon_bank", "chart", "table"}
    assert by_reason["chart"].label == "Chart"
    assert by_reason["table"].label == "Table"


def test_title_only_over_graphics_is_a_fixed_divider(showcase):
    divider = _slide(showcase, "Motif")
    assert divider.intent == "fixed"


def test_pure_layout_instance_is_folded_into_its_layout(showcase):
    labels = [p.label for p in showcase.patterns if p.source == "slide"]
    assert not any(label.startswith("Title and Content (") for label in labels)


def test_large_free_picture_is_a_replaceable_image(showcase):
    photo = _slide(showcase, "Photo")
    assert [z.role for z in photo.zones] == ["title", "image"]
    assert photo.intent == "image_text"


def test_example_slide_of_an_existing_intent_is_preferred(showcase):
    photo = _slide(showcase, "Photo")
    assert photo.preferred  # the default template has a Picture with Caption layout
    agenda = _slide(showcase, "Agenda")
    assert not agenda.preferred


def test_example_slide_placeholders_inherit_their_font_size(showcase):
    agenda = _slide(showcase, "Agenda")
    title = next(z for z in agenda.zones if z.role == "title")
    # Inherited from the master title style (44 pt in the default template),
    # so the capacity the catalogue quotes is the real one.
    assert title.font_pt == 44
    assert title.max_chars and title.max_chars < 40


def test_notes_without_body_placeholder_do_not_abort_the_analysis(showcase):
    silent = _slide(showcase, "Silent notes")
    assert silent.intent == "content"


def test_two_sibling_groups_are_columns_not_a_list(showcase):
    two = _slide(showcase, "Two columns")
    assert two.groups == []
    assert two.intent == "comparison"
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

# label -> (intent, group count, item roles) for the reference corporate deck.
REFERENCE_EXPECTATIONS = {
    "SOMMAIRE": ("agenda", 8, ["number", "heading"]),
    "Indicateurs de performance / chiffres clés": ("cards", 4, ["number", "label"]),
    "3 icônes + texte": ("cards", 3, ["body"]),
    "Planche de processus": ("steps", 3, ["number", "heading", "body"]),
    "Timeline jusqu’à 6 ans": ("steps", 6, ["number", "heading", "body"]),
    "Equipe": ("cards", 22, ["heading", "label"]),
}


@pytest.mark.skipif(
    not REFERENCE or not os.path.exists(REFERENCE or ""),
    reason="reference template not provided",
)
def test_reference_template_free_form_slides():
    inventory = analyze_template(open(REFERENCE, "rb").read()).inventory  # type: ignore[arg-type]
    assert inventory is not None
    by_label = {}
    for pattern in inventory.patterns:
        by_label.setdefault(pattern.label, pattern)
    for label, (intent, count, roles) in REFERENCE_EXPECTATIONS.items():
        pattern = by_label[label]
        assert pattern.intent == intent, label
        assert pattern.groups[0].count == count, label
        assert pattern.groups[0].item_zones == roles, label
    layouts = {p.name: p.intent for p in inventory.patterns if p.source == "layout"}
    assert layouts["Couverture"] == "title"
    assert layouts["Slide chapitre"] == "section"
    assert layouts["2 colonnes de texte"] == "two_columns"
    assert layouts["Bullet Points"] == "comparison"
    assert layouts["Contact"] == "contact"
    assert layouts["Merci"] == "fixed"
    excluded = {p.exclusion_reason for p in inventory.patterns if not p.included}
    assert excluded == {"chart", "table", "icon_bank"}
