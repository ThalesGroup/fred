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

"""Built-in deck: a section slide's number zone and filled picture zones."""

from __future__ import annotations

import io
from typing import Any, Dict, List, cast

import pytest
from builder_decks import _blank_titled, _placeholder, build_slides
from deck_builders import png_bytes
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.assign import assign
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.plan import DeckPlan
from fred_capability_ppt_filler.builder.render import RenderResult, render_deck
from fred_capability_ppt_filler.images import prepare_picture
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.shapes.picture import Picture
from pptx.util import Pt

COVER = {"title": "Quarterly review", "subtitle": "Sales"}


@pytest.fixture(scope="module")
def builtin():
    return builtin_template()


# Twice as wide as high: a frame of another shape must crop it, never letterbox it.
WIDE = {f"img-{n}": prepare_picture(png_bytes(400, 200, "blue")) for n in range(4)}


def _render(builtin, *slides: Dict[str, Any], cover=COVER) -> RenderResult:
    template, inventory = builtin
    plan = DeckPlan.model_validate({"slides": [cover, *slides]})
    assignment = assign(inventory, plan, "off")
    assert not assignment.problems, [p.as_dict() for p in assignment.problems]
    return render_deck(template, inventory, plan, assignment.patterns, images=WIDE)


def _numbers(result: RenderResult) -> List[str]:
    """The text of each section slide's number zone, in deck order."""
    deck = Presentation(io.BytesIO(result.pptx))
    found = []
    for slide in deck.slides:
        if not slide.slide_layout.name.startswith("Fred Section"):
            continue
        texts = [
            cast(Any, s).text_frame.text
            for s in slide.placeholders
            if s.placeholder_format.idx == 103 and s.has_text_frame
        ]
        found.append(texts[0] if texts else "")
    return found


def test_section_slides_are_numbered_in_deck_order(builtin):
    body = {"title": "Pipeline", "bullets": ["Two new accounts", "One renewal"]}
    result = _render(
        builtin,
        {"title": "Market", "kind": "section"},
        body,
        {"title": "Team", "kind": "section", "number": "07"},
        body,
        {"title": "Next steps", "kind": "section"},
    )
    # Zero-padded as the example's "01"; a number the plan gives is kept.
    assert _numbers(result) == ["01", "07", "03"]


def _photos(result: RenderResult) -> List[Picture]:
    deck = Presentation(io.BytesIO(result.pptx))
    return [s for slide in deck.slides for s in slide.shapes if isinstance(s, Picture)]


def _crop(picture: Picture) -> tuple:
    return tuple(
        round(v, 3)
        for v in (
            picture.crop_left,
            picture.crop_right,
            picture.crop_top,
            picture.crop_bottom,
        )
    )


def _cropped_to_fill(picture: Picture) -> bool:
    """The picture's visible part has its frame's proportions: no bars."""
    left, right, top, bottom = _crop(picture)
    shown = (400 * (1 - left - right)) / (200 * (1 - top - bottom))
    return abs(shown - picture.width / picture.height) < 0.02


def test_team_photos_fill_their_round_frames(builtin):
    members = [
        {"heading": name, "text": "Lead", "image": f"img-{n}"}
        for n, name in enumerate(("Ana", "Ben", "Chloé", "Dev"))
    ]
    result = _render(builtin, {"title": "Team", "kind": "team", "items": members})
    photos = _photos(result)
    assert len(photos) == 4
    for photo in photos:
        # Square frame, wide picture: a quarter cut off each side.
        assert _crop(photo) == (0.25, 0.25, 0.0, 0.0)
        # No geometry of its own: the layout's ellipse shows; the alt text stays.
        assert photo._element.spPr.find(qn("a:prstGeom")) is None
        assert cast(Any, photo._element.nvPicPr).cNvPr.get("descr")


def test_cover_and_image_text_pictures_are_cropped_to_fill(builtin):
    result = _render(
        builtin,
        {"title": "Our site", "bullets": ["Opened in 2024"], "image": "img-1"},
        cover={**COVER, "image": "img-0"},
    )
    photos = _photos(result)
    assert len(photos) == 2
    assert all(_cropped_to_fill(p) for p in photos)
    assert all(p.crop_top > 0 or p.crop_left > 0 for p in photos)


def test_three_team_photos_move_with_their_names(builtin):
    members = [
        {"heading": name, "text": "Lead", "image": f"img-{n}"}
        for n, name in enumerate(("Ana", "Ben", "Chloé"))
    ]
    result = _render(builtin, {"title": "Team", "kind": "team", "items": members})
    slide = Presentation(io.BytesIO(result.pptx)).slides[1]
    photos = [s for s in slide.shapes if isinstance(s, Picture)]
    names = [
        s
        for s in slide.placeholders
        if s.has_text_frame and cast(Any, s).text_frame.text in ("Ana", "Ben", "Chloé")
    ]
    assert len(photos) == len(names) == 3
    for photo, name in zip(photos, names):
        assert (
            abs((photo.left + photo.width // 2) - (name.left + name.width // 2)) < 9525
        )


def _shared_idx_slide(presentation):
    """Three (picture, text) columns whose first two picture slots share one
    placeholder idx, as a copied slot leaves them."""
    slide = _blank_titled(presentation, "Our three sites")
    for n, x in enumerate((0.3, 3.5, 6.7)):
        _placeholder(slide, "pic", 30 if n < 2 else 32, x, 1.5, 2.8, 2.4, "", Pt(12))
        _placeholder(slide, "body", 40 + n, x, 4.1, 2.8, 1.2, "Some text", Pt(14))


def test_two_picture_slots_sharing_an_idx_are_each_filled():
    template = build_slides([_shared_idx_slide])
    inventory = analyze_template(template).inventory
    assert inventory is not None
    pattern = next(p for p in inventory.patterns if p.source == "slide")
    assert len(set(pattern.groups[0].item_keys)) == 3
    sites = [
        {"text": site, "image": f"img-{n}"}
        for n, site in enumerate(("Lyon", "Lille", "Nantes"))
    ]
    plan = DeckPlan.model_validate(
        {"slides": [{"title": "Our three sites", "kind": "cards", "items": sites}]}
    )
    # Failed before: both items sent their picture to the first slot, and the
    # second insert hit a placeholder the first had already replaced.
    result = render_deck(template, inventory, plan, [pattern], images=WIDE)
    slide = Presentation(io.BytesIO(result.pptx)).slides[0]
    assert len([s for s in slide.shapes if isinstance(s, Picture)]) == 3
