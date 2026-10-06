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

"""The ``build_presentation`` and image-listing tools, offline on the port
fakes: schema and description, delivery, the needs-revision error and the
repair loop."""

from __future__ import annotations

import io
import json
from typing import Any, cast

import pytest
from builder_decks import build_showcase_template
from deck_builders import png_bytes
from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder import tools as tools_mod
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.capability import (
    PPT_BUILDER_TEMPLATE_KEY,
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.checks import SlideReport
from fred_capability_ppt_filler.builder.models import PatternOverride
from fred_capability_ppt_filler.builder.plan import DeckPlan
from fred_capability_ppt_filler.builder.tools import (
    BUILD_TOOL_NAME,
    LIST_IMAGES_TOOL_NAME,
    _build_notes,
)
from fred_capability_ppt_filler.fill import PptPreviewPart
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeAssets, FakeDocs, FakeFolders, FakeWorkspace
from pptx import Presentation

TEMPLATE = build_showcase_template()
COVER = {"title": "Kick-off", "subtitle": "Team"}


@pytest.fixture
def preview_union():
    """Register ``PptPreviewPart`` in the runtime ``UiPart`` union, as the
    capability registry does at pod boot."""
    from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union

    rebuild_ui_part_union([PptPreviewPart])
    yield
    rebuild_ui_part_union(())


async def _pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return b"%PDF-fake"


async def _no_pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return None


def _ctx(
    config: PptBuilderConfig, *, assets=None, docs=None, folders=None, workspace=None
):
    return CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1", session_id="sess-9", agent_instance_id="inst-7"
        ),
        config=config,
        turn_options=EmptyModel(),
        services=RuntimeServices(
            agent_assets=assets,
            document_content=docs,
            document_folders=folders,
            workspace_fs=workspace if workspace is not None else FakeWorkspace(),
        ),
    )


def _tools(ctx) -> dict[str, Any]:
    (middleware,) = PptBuilderCapability().middleware(ctx)
    return {tool.name: cast(Any, tool) for tool in cast(Any, middleware).tools}


def _configured() -> tuple[PptBuilderConfig, FakeAssets]:
    """A template whose analysis succeeded and is in this pod's cache."""
    inventory = analyze_template(TEMPLATE).inventory
    assert inventory is not None
    config = PptBuilderConfig(template_sha256="sha-test")
    analysis_job.remember_inventory(
        "inst-7", "sha-test", config.labelling_key(), inventory
    )
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})
    return config, assets


async def _build(monkeypatch, *, workspace=None, docs=None, **kwargs):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    tools = _tools(_ctx(config, assets=assets, docs=docs, workspace=workspace))
    return await tools[BUILD_TOOL_NAME].coroutine(**kwargs)


# --- schema and description ---------------------------------------------------------------


def test_schema_and_description_offer_kinds_never_pattern_ids():
    config, assets = _configured()
    excluded = PatternOverride(
        pattern_id="layout:0", included=False, label="Hidden cover"
    )
    config = config.model_copy(update={"overrides": [excluded]})
    tools = _tools(_ctx(config, assets=assets))
    assert set(tools) == {BUILD_TOOL_NAME, LIST_IMAGES_TOOL_NAME}
    description = tools[BUILD_TOOL_NAME].description
    assert "slide:" not in description and "layout:" not in description
    assert "Hidden cover" not in description
    process = next(
        line for line in description.splitlines() if line.startswith("- process: ")
    )
    assert ": title" in process  # variant label first, then its zones
    assert "items max 3 [number, heading, text" in description
    assert "≈chars per line × lines" in description
    # The only cover was excluded: no cover kind, and no cover rule announced.
    assert "- cover:" not in description and "always the template's cover" not in (
        description
    )
    properties = tools[BUILD_TOOL_NAME].args_schema.model_json_schema()["$defs"][
        "BuildSlide"
    ]["properties"]
    assert "pattern" not in properties
    # Content first, `kind` last, listing only what this template offers.
    assert list(properties)[0] == "title" and list(properties)[-1] == "kind"
    # The only enum anywhere in the field: the type's full list stays out.
    kind_schema = properties["kind"]
    assert "enum" not in kind_schema
    (kinds,) = [b["enum"] for b in kind_schema["anyOf"] if "enum" in b]
    assert "process" in kinds and "cover" not in kinds and "cards" not in kinds


def test_the_tool_tells_the_agent_one_call_builds_the_whole_deck():
    config, assets = _configured()
    description = _tools(_ctx(config, assets=assets))[BUILD_TOOL_NAME].description
    assert "ONE call builds the WHOLE deck" in description
    assert "Never split a deck across several calls" in description
    assert "The first slide is always the template's cover" in description


# --- delivery -------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_returns_preview_part_and_uploads_deck(monkeypatch, preview_union):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _pdf)
    config, assets = _configured()
    workspace = FakeWorkspace()
    tools = _tools(_ctx(config, assets=assets, workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[COVER, {"title": "Plan", "bullets": ["one", "- two"]}],
        file_name="Kick off 2026",
    )
    assert not result.is_error, text
    (part,) = result.ui_parts
    assert isinstance(part, PptPreviewPart)
    assert part.file_name == "Kick off 2026.pptx"
    # The card opens this capability's pane: an agent may not have ppt_filler.
    assert part.capability_id == "ppt_builder"
    assert "2 slides" in text
    # Another call is allowed: it rebuilds the whole deck.
    assert "do not call again" not in text and "COMPLETE list" in text
    # Keyed by the deck's name: a model that splits one deck across calls, or
    # retries one, lands on the same key and the reader sees one presentation.
    paths = [w["path"] for w in workspace.writes]
    assert paths == [
        "outputs/sess-9/Kick off 2026.pptx",
        "outputs/sess-9/Kick off 2026.pdf",
    ]
    deck = Presentation(io.BytesIO(workspace.writes[0]["content"]))
    assert [cast(Any, s.shapes.title).text for s in deck.slides] == ["Kick-off", "Plan"]


@pytest.mark.asyncio
async def test_build_without_template_uses_the_built_in_template(monkeypatch):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    workspace = FakeWorkspace()
    tools = _tools(_ctx(PptBuilderConfig(), workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[
            COVER,
            {"title": "KPIs", "bullets": ["Margin up to 42%", "Churn down"]},
            {"title": "Merci"},
        ]
    )
    assert not result.is_error, text
    assert "only the download" in text
    assert result.ui_parts[0].kind.value == "download"
    deck = Presentation(io.BytesIO(workspace.writes[0]["content"]))
    assert len(deck.slides) == 3


@pytest.mark.asyncio
async def test_several_builds_of_one_answer_land_on_one_preview(
    monkeypatch, preview_union
):
    """They share a key, so the reader is shown one deck."""
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _pdf)
    config, assets = _configured()
    tools = _tools(_ctx(config, assets=assets, workspace=FakeWorkspace()))
    previews = []
    for title in ("Part one", "Part two", "Part three"):
        _, result = await tools[BUILD_TOOL_NAME].coroutine(slides=[{"title": title}])
        previews.append(cast(Any, result.ui_parts[0]).preview_id)
    assert len(set(previews)) == 1, previews


# --- malformed plans --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_plan_is_an_error_the_user_can_read(monkeypatch):
    text, result = await _build(monkeypatch, slides=[{"kind": "bullets"}])
    assert result.is_error and "no content" in text
    # The text travels in the result so the runtime shows it, not a generic failure.
    assert result.blocks and result.blocks[0].text == text


@pytest.mark.asyncio
async def test_malformed_plan_from_a_small_model_still_builds(monkeypatch):
    """The shape of a real failing call: the old `pattern` key holding ids or
    legacy names, stray strings in `slides`, bullets as one string, numbers as
    integers, an unknown top-level key."""
    workspace = FakeWorkspace()
    text, result = await _build(
        monkeypatch,
        workspace=workspace,
        notes="stray top-level key",
        slides=[
            {"pattern": "title", "title": "Kick-off", "subtitle": "Team"},
            {
                "pattern": "slide:999",
                "title": "Options",
                "columns": [
                    {"heading": "A", "bullets": "fast\ncheap"},
                    {"heading": "B", "bullets": ["robust"]},
                ],
            },
            {
                "kind": "Figures",
                "title": "KPIs",
                "items": [{"number": 3, "label": "Sites"}, "Loose item"],
            },
            {"title": "Plan", "bullets": "one\ntwo"},
            "notes**: ",
            "A long stray note that is not a slide",
        ],
    )
    assert not result.is_error, text
    deck = Presentation(io.BytesIO(workspace.writes[0]["content"]))
    assert len(deck.slides) == 4
    assert "4 slides" in text
    assert "Entry 5 of 'slides' was not a slide object" in text


# --- no silent fallback, repair loop ----------------------------------------------------------


@pytest.mark.asyncio
async def test_a_slide_that_fits_nothing_builds_nothing_and_says_what_to_change(
    monkeypatch,
):
    """Seven steps where the largest process slide holds three: the old tool
    dropped four of them silently."""
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, _ = _configured()
    # No template in the store: a fetch would turn the answer into a load error.
    tools = _tools(_ctx(config, assets=FakeAssets(), workspace=workspace))
    steps = [{"number": str(i), "heading": f"Step {i}", "text": "x"} for i in range(7)]
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[COVER, {"title": "Method", "kind": "process", "items": steps}]
    )
    assert result.is_error
    assert workspace.writes == []
    payload = json.loads(text[text.index("{") :])
    assert payload["status"] == "needs_revision"
    (problem,) = payload["slides"]
    assert problem["slide"] == 2 and problem["kind"] == "process"
    assert "items: 7 given; the largest slide" in problem["problem"]
    assert any(o.startswith("trim to ") for o in problem["options"])
    assert "split the items over two slides" in problem["options"]
    assert "repeated" not in problem

    # The same plan again is flagged as resent, not answered word for word.
    text, _ = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[COVER, {"title": "Method", "kind": "process", "items": steps}]
    )
    (again,) = json.loads(text[text.index("{") :])["slides"]
    assert again["repeated"].startswith("you resent this slide unchanged")
    text, _ = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[COVER, {"title": "Method v2", "kind": "process", "items": steps}]
    )
    (changed,) = json.loads(text[text.index("{") :])["slides"]
    assert changed["repeated"] == "the slide changed but this problem is still there"


@pytest.mark.asyncio
async def test_the_corrected_plan_is_built_as_a_whole(monkeypatch):
    workspace = FakeWorkspace()
    steps = [{"number": str(i), "heading": f"Step {i}", "text": "x"} for i in range(7)]
    _, first = await _build(
        monkeypatch,
        workspace=workspace,
        slides=[COVER, {"title": "Method", "kind": "process", "items": steps}],
    )
    assert first.is_error and workspace.writes == []
    text, second = await _build(
        monkeypatch,
        workspace=workspace,
        slides=[
            COVER,
            {"title": "Method 1/2", "kind": "process", "items": steps[:3]},
            {"title": "Method 2/2", "kind": "process", "items": steps[3:6]},
        ],
    )
    assert not second.is_error, text
    deck = Presentation(io.BytesIO(workspace.writes[-1]["content"]))
    assert len(deck.slides) == 3


# --- variety, asked once on the first deck --------------------------------------------------


def _steps(n: int) -> dict:
    items = [
        {"number": "1", "heading": "a", "text": "b"},
        {"number": "2", "heading": "c", "text": "d"},
    ]
    return {"title": f"Step {n}", "items": items}


_REPEATED = [COVER] + [_steps(n) for n in range(4)]


@pytest.mark.asyncio
async def test_the_first_deck_is_asked_to_vary_once_and_a_resend_is_built(monkeypatch):
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    text, result = await build.coroutine(slides=_REPEATED)
    assert result.is_error and workspace.writes == []
    payload = json.loads(text[text.index("{") :])
    assert payload["status"] == "needs_revision"
    (repeat,) = payload["variety"]
    assert repeat["slides"] == [2, 3, 4, 5] and repeat["kind"] == "process"
    assert any(
        o.startswith("'figures' for short numeric items") for o in repeat["options"]
    )
    assert "send the same plan again: it will be built as is" in text
    # The same plan again: built, with the passive note only.
    text, result = await build.coroutine(slides=_REPEATED)
    assert not result.is_error, text
    assert "Slides 2, 3, 4, 5 all use the template slide 'Process'" in text


@pytest.mark.asyncio
async def test_a_deck_after_the_first_one_only_gets_the_note(monkeypatch):
    """A later turn (a new tool instance) sees the delivered deck in the
    conversation's outputs folder: the user may have asked for these slides."""
    workspace = FakeWorkspace()
    await _build(monkeypatch, workspace=workspace, slides=[COVER])
    assert workspace.writes
    text, result = await _build(monkeypatch, workspace=workspace, slides=_REPEATED)
    assert not result.is_error, text
    assert "all use the template slide 'Process'" in text


@pytest.mark.asyncio
async def test_structural_repeats_are_never_a_revision(monkeypatch):
    sections = [COVER] + [{"title": f"Part {n}", "kind": "section"} for n in range(4)]
    text, result = await _build(monkeypatch, slides=sections)
    assert not result.is_error, text


@pytest.mark.asyncio
async def test_a_heading2_column_is_returned_for_revision_not_dropped(monkeypatch):
    workspace = FakeWorkspace()
    text, result = await _build(
        monkeypatch,
        workspace=workspace,
        slides=[
            COVER,
            {
                "kind": "two_columns",
                "title": "Implantation",
                "columns": {
                    "bullets": ["2 800 experts"],
                    "heading": "Espagne",
                    "heading2": "Italie",
                },
            },
        ],
    )
    assert result.is_error and workspace.writes == []
    (problem,) = json.loads(text[text.index("{") :])["slides"]
    assert problem["slide"] == 2
    assert "heading2 'Italie' is not a column field" in problem["problem"]


def test_the_success_notes_name_what_was_cut_per_slide():
    """Read from the render's after-check report, one line per slide."""
    plan = DeckPlan.model_validate({"slides": [COVER, "junk"]})
    report = SlideReport(1, removed=["Lorem"], truncated=["title"], lost=["subtitle"])
    notes = _build_notes(plan, [report], [])
    assert "Entry 2 of 'slides' was not a slide object" in notes
    assert (
        "Slide 1: text cut to fit in title; template example text removed: 'Lorem'; "
        "not placed: subtitle." in notes
    )
    assert "call again with the whole corrected deck" in notes
    assert _build_notes(DeckPlan.model_validate({"slides": [COVER]}), [], []) == ""


# --- images -----------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_places_images_from_documents_and_reports_bad_ones(monkeypatch):
    docs = FakeDocs(
        {"img-1": (png_bytes(20, 10), "image/png"), "txt-1": (b"hello", "text/plain")}
    )

    def plan(image: str) -> list:
        return [COVER, {"title": "Site", "image": image}]

    text, result = await _build(monkeypatch, docs=docs, slides=plan("img-1"))
    assert not result.is_error, text
    assert docs.fetch_uids == ["img-1"]
    # A bad image reference costs the picture, never the deck.
    text, result = await _build(monkeypatch, docs=docs, slides=plan("txt-1"))
    assert not result.is_error and "image 'txt-1'" in text
    text, result = await _build(monkeypatch, docs=docs, slides=plan("missing"))
    assert not result.is_error and "image 'missing'" in text


@pytest.mark.asyncio
async def test_list_images_resolves_the_folder_at_call_time():
    folders = FakeFolders(
        {"Images/Sites": "tag-1"},
        {"tag-1": [("d1", "bordeaux.png"), ("d2", "notes.docx")]},
    )
    config, assets = _configured()
    tools = _tools(_ctx(config, assets=assets, folders=folders))
    listed = await tools[LIST_IMAGES_TOOL_NAME].coroutine(folder="/Images/Sites/")
    assert '"d1"' in listed and "d2" not in listed
    missing = await tools[LIST_IMAGES_TOOL_NAME].coroutine(folder="Nope")
    assert "No folder named 'Nope'" in missing
