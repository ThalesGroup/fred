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

import asyncio
import io
import json
from typing import Any, cast

import pytest
from builder_decks import EVIDENCE_SLIDES, build_showcase_template, with_item_slides
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
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
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


def _configured(
    extend=None, variety: str = "template_slide"
) -> tuple[PptBuilderConfig, FakeAssets]:
    """A template whose analysis succeeded and is in this pod's cache."""
    inventory = analyze_template(TEMPLATE).inventory
    assert inventory is not None
    if extend is not None:
        inventory = extend(inventory)
    config = PptBuilderConfig.model_validate(
        {"template_sha256": "sha-test", "variety_check": variety}
    )
    analysis_job.remember_inventory(
        "inst-7", "sha-test", config.labelling_key(), inventory
    )
    analysis_job.remember_template("sha-test", TEMPLATE)
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})
    return config, assets


async def _build(
    monkeypatch,
    *,
    workspace=None,
    docs=None,
    extend=None,
    variety="template_slide",
    **kwargs,
):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured(extend, variety)
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


def test_each_text_field_states_its_room_where_the_model_writes_it():
    """The cover subtitle and figure labels failed most first calls while their
    sizes sat only in the catalogue."""
    inventory = analyze_template(TEMPLATE).inventory
    assert inventory is not None
    schema = tools_mod._args_schema(inventory)
    defs = schema.model_json_schema()["$defs"]
    slide = defs["BuildSlide"]["properties"]
    # The most common room, then each kind that differs; a single kind is named.
    title = slide["title"]["description"]
    assert title.startswith("Slide title. Room: ≈33 chars; cover ≈29 chars × 2 lines")
    assert (
        "Room: section ≈66 chars × 3 lines; cover ≈33 chars × 3 lines."
        in (slide["subtitle"]["description"])
    )
    heading = defs["BuildColumn"]["properties"]["heading"]["description"]
    assert heading.endswith("Room: comparison ≈30 chars.")
    # Hints only: an over-long text must reach the tool, not fail at the provider.
    assert "maxLength" not in json.dumps(schema.model_json_schema())
    # Equal templates share one cached schema, and the plan still coerces.
    assert tools_mod._args_schema(inventory.model_copy(deep=True)) is schema
    plan = tools_mod._to_plan(schema(slides=[{"title": "A", "items": ["x"]}]))
    assert plan.slides[0].items[0].heading == "x"


def test_the_tool_tells_the_agent_one_call_builds_the_whole_deck():
    config, assets = _configured()
    description = _tools(_ctx(config, assets=assets))[BUILD_TOOL_NAME].description
    assert "ONE call builds the WHOLE deck" in description
    assert "Never split a deck across several calls" in description
    assert "The first slide is always the template's cover" in description
    # The choice guide names only kinds this template offers.
    assert (
        "key numbers, each a value + a short label → figures" in description
        and "ordered steps → process" in description
    )
    assert "→ timeline" not in description
    assert "Use any variant below at most 2 times per deck." in description


def test_the_choice_guide_states_the_authors_max():
    config, assets = _configured()

    def guide(**update: Any) -> str:
        ctx = _ctx(config.model_copy(update=update), assets=assets)
        return _tools(ctx)[BUILD_TOOL_NAME].description

    assert "Each slide of the deck must look different." in guide(variety_max_uses=1)
    assert "Use any kind below on at most 3 slides per deck" in guide(
        variety_check="kind", variety_max_uses=3
    )
    off = guide(variety_check="off", variety_max_uses=1)
    assert "at most" not in off.split("Slide kinds of this template")[0]
    assert "look different" not in off


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
    assert tools_mod.deck_delivered(_turn(text))  # a later turn sees it
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
    assert result.is_error and "every slide of the plan is empty" in text
    assert "and call build_presentation again" in text
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
    assert "items: 7 given; the largest 'process' slide holds 3" in problem["problem"]
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
    assert changed["repeated"] == (
        "the slide changed but this problem is still there: apply one of the options"
    )


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


@pytest.mark.asyncio
async def test_a_parallel_copy_of_a_call_is_not_built_twice(monkeypatch):
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    plan = [COVER, {"title": "Agenda", "bullets": ["One", "Two"]}]
    (text_a, a), (text_b, b) = await asyncio.gather(
        build.coroutine(slides=plan), build.coroutine(slides=plan)
    )
    assert not a.is_error and not b.is_error
    ignored = [text_a.startswith("Ignored:"), text_b.startswith("Ignored:")]
    assert sorted(ignored) == [False, True]
    assert len(workspace.writes) == 1
    # A different plan sent in parallel is built too, one after the other.
    (_, c), (_, d) = await asyncio.gather(
        build.coroutine(slides=plan), build.coroutine(slides=[COVER])
    )
    assert not c.is_error and not d.is_error and len(workspace.writes) == 3


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
    assert repeat["at_most"] == 2
    # Two figures variants: two slides suggested, none left to offer as an option.
    assert repeat["suggested"] == [
        "slides 2, 3 (short figures) → figures holds items max 4 [number, label]"
    ]
    assert not any(o.startswith("'figures'") for o in repeat["options"])
    assert any(o.startswith("'two_columns'") for o in repeat["options"])
    assert "send the same plan again: it will be built as is" in text
    # The same plan again: built, with the passive note only.
    text, result = await build.coroutine(slides=_REPEATED)
    assert not result.is_error, text
    assert "Slides 2, 3, 4, 5 all use the template slide 'Process'" in text


_TOO_MANY = {
    "title": "Method",
    "kind": "process",
    "items": [
        {"number": str(i), "heading": f"Step {i}", "text": "x"} for i in range(7)
    ],
}


@pytest.mark.asyncio
async def test_no_variety_ask_after_a_fit_repair(monkeypatch):
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    text, result = await build.coroutine(slides=[COVER, _TOO_MANY])
    assert result.is_error and "variety" not in text
    # The repaired deck repeats a kind: built, the repetition only noted.
    text, result = await build.coroutine(slides=_REPEATED)
    assert not result.is_error, text
    assert "Slides 2, 3, 4, 5 all use the template slide 'Process'" in text


@pytest.mark.asyncio
async def test_a_first_call_with_fit_problems_carries_the_variety_ask(monkeypatch):
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    text, result = await build.coroutine(slides=_REPEATED + [_TOO_MANY])
    assert result.is_error and workspace.writes == []
    payload = json.loads(text[text.index("{") :])
    assert [p["slide"] for p in payload["slides"]] == [6]
    (repeat,) = payload["variety"]
    # The slide to fix counts on its closest fit, the same process slide.
    assert repeat["slides"] == [2, 3, 4, 5, 6]
    assert "the next deck that fits is built as is" in text
    # Fixed, kinds unchanged: one round was enough, the deck is built.
    text, result = await build.coroutine(slides=_REPEATED)
    assert not result.is_error, text


def _labelled_steps(n: int, label: bool = True) -> dict:
    steps = _steps(n)
    if label:
        steps["items"] = [{**i, "label": "note"} for i in steps["items"]]
    return steps


@pytest.mark.asyncio
async def test_slides_to_fix_that_repeat_are_asked_to_vary_in_the_same_round(
    monkeypatch,
):
    """The live call: both repeated slides had a fit problem, so the first
    answer named no repeat and the repaired deck broke the max of 1."""
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    config = config.model_copy(update={"variety_max_uses": 1})
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    text, result = await build.coroutine(
        slides=[COVER, _labelled_steps(1), _labelled_steps(2)]
    )
    assert result.is_error and workspace.writes == []
    payload = json.loads(text[text.index("{") :])
    assert [p["slide"] for p in payload["slides"]] == [2, 3]
    assert all(
        "closest fit, a 'process' slide" in p["problem"] for p in payload["slides"]
    )
    (repeat,) = payload["variety"]
    assert repeat["slides"] == [2, 3] and repeat["at_most"] == 1
    assert "several slides would look the same" in text
    # Fixed, kinds unchanged: built as is, the repeat only noted.
    fixed = [COVER, _labelled_steps(1, False), _labelled_steps(2, False)]
    text, result = await build.coroutine(slides=fixed)
    assert not result.is_error, text
    assert "Slides 2, 3 all use the template slide 'Process'" in text


class _Request:
    system_prompt = ""

    def __init__(self, messages: list, tools: list) -> None:
        self.messages, self.tools = messages, tools

    def override(self, **_update: Any) -> "_Request":
        return self


async def _later_turn(
    monkeypatch, history: list, extend=None, variety="template_slide"
):
    """A new turn's build tool, after the model call that was sent ``history``."""
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured(extend, variety)
    (middleware,) = PptBuilderCapability().middleware(_ctx(config, assets=assets))
    middleware = cast(Any, middleware)

    async def _handler(request):
        return request

    await middleware.awrap_model_call(_Request(history, middleware.tools), _handler)
    return {t.name: cast(Any, t) for t in middleware.tools}[BUILD_TOOL_NAME]


def _turn(text: str, name: str = BUILD_TOOL_NAME) -> list:
    call = {"id": "call-1", "name": name, "args": {}}
    return [
        HumanMessage(content="Make me a deck"),
        AIMessage(content="", tool_calls=[call]),
        ToolMessage(content=text, tool_call_id="call-1", name=name),
    ]


@pytest.mark.asyncio
async def test_a_deck_after_the_first_one_only_gets_the_note(monkeypatch):
    """A delivered deck in the history: the user may have asked for these slides."""
    delivered, result = await _build(monkeypatch, slides=[COVER])
    assert not result.is_error
    build = await _later_turn(monkeypatch, _turn(delivered))
    text, result = await build.coroutine(slides=_REPEATED)
    assert not result.is_error, text
    assert "all use the template slide 'Process'" in text


@pytest.mark.asyncio
async def test_a_history_without_a_delivered_deck_is_still_a_first_deck(monkeypatch):
    asked, _ = await _build(monkeypatch, slides=_REPEATED)
    assert '"variety": [' in asked
    unread, _ = await _build(monkeypatch, slides=[{"kind": "bullets"}])
    # A needs_revision, an error, or another tool's text never delivered a deck.
    history = _turn(asked) + _turn(unread) + _turn("Delivered: 'x.pptx'", "other")
    build = await _later_turn(monkeypatch, history)
    text, result = await build.coroutine(slides=_REPEATED)
    assert result.is_error and '"variety": [' in text


def test_both_success_texts_count_as_a_delivered_deck():
    assert tools_mod.deck_delivered(_turn("Delivered: 'a.pptx', 3 slides."))
    assert tools_mod.deck_delivered(
        _turn("The presentation 'a.pptx' (3 slides) is ready")
    )
    assert not tools_mod.deck_delivered(
        _turn("The presentation template could not be loaded right now.")
    )
    assert not tools_mod.deck_delivered([])


@pytest.mark.asyncio
async def test_one_kind_on_different_slides_is_asked_once_with_content_advice(
    monkeypatch,
):
    """The real first deck: five bullets slides on five template slides."""
    workspace = FakeWorkspace()
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured(with_item_slides, "kind")
    build = _tools(_ctx(config, assets=assets, workspace=workspace))[BUILD_TOOL_NAME]
    text, result = await build.coroutine(slides=EVIDENCE_SLIDES)
    assert result.is_error and workspace.writes == []
    (repeat,) = json.loads(text[text.index("{") :])["variety"]
    assert repeat["kind"] == "bullets" and repeat["slides"] == [3, 5, 7, 9, 10]
    suggested = repeat["suggested"]
    assert any(
        s.startswith("slide 7 (dated items) → timeline holds items max 6 [heading ≈20")
        for s in suggested
    )
    assert any(s.startswith("slide 5 (parallel") for s in suggested)
    text, result = await build.coroutine(slides=EVIDENCE_SLIDES)
    assert not result.is_error, text
    assert "Slides 3, 5, 7, 9, 10 are all 'bullets' slides" in text


@pytest.mark.asyncio
async def test_a_later_deck_repeating_a_kind_only_gets_the_note(monkeypatch):
    delivered, _ = await _build(monkeypatch, slides=[COVER])
    build = await _later_turn(
        monkeypatch, _turn(delivered), extend=with_item_slides, variety="kind"
    )
    text, result = await build.coroutine(slides=EVIDENCE_SLIDES)
    assert not result.is_error, text
    assert "are all 'bullets' slides" in text
    assert "slide 7 (dated items) → timeline holds items max 6" in text


@pytest.mark.asyncio
async def test_each_variety_check_mode_asks_for_its_own_repeat(monkeypatch):
    """Five bullets slides on five template slides: a kind repeat, no template
    slide used three times; the steps reuse one template slide."""
    for variety, plan, asked in [
        ("template_slide", EVIDENCE_SLIDES, False),
        ("kind", EVIDENCE_SLIDES, True),
        ("template_slide", _REPEATED, True),
        ("off", _REPEATED, False),
        ("off", EVIDENCE_SLIDES, False),
    ]:
        # The added item slides are never rendered: only the evidence plan needs them.
        extend = with_item_slides if plan is EVIDENCE_SLIDES else None
        text, result = await _build(
            monkeypatch, extend=extend, variety=variety, slides=plan
        )
        assert result.is_error is asked, (variety, text)
        assert not asked or '"variety": [' in text
        if variety == "off":  # no ask, the passive note stays
            assert "all use the template slide" in text or "are all" in text


def test_the_variety_check_defaults_and_never_triggers_a_re_analysis():
    stored = PptBuilderConfig.model_validate({"template_sha256": "sha"})
    assert stored.variety_check == "template_slide" and stored.variety_max_uses == 2
    keys = {
        PptBuilderConfig(
            template_sha256="sha", variety_check=v, variety_max_uses=m
        ).labelling_key()
        for v in ("template_slide", "kind", "off")
        for m in (1, 5)
    }
    assert keys == {stored.labelling_key()}
    with pytest.raises(ValueError):
        PptBuilderConfig(variety_max_uses=6)
    fields = {f.key: f for f in PptBuilderCapability.manifest.config_fields}
    check, most = fields["variety_check"], fields["variety_max_uses"]
    assert check.enum == ["template_slide", "kind", "off"]
    assert check.default == "template_slide" and most.default == 2
    assert (most.min, most.max) == (1, 5)
    # The plugin widget owns both: one sentence, not two generic fields.
    assert check.ui.widget == most.ui.widget == "ppt_builder_template"


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
        "Slide 1: text cut to fit in title (shorten it to show it whole); template "
        "example text removed: 'Lorem' (nothing to do); not placed: subtitle (move it "
        "to a field this slide shows, or drop it)." in notes
    )
    assert "call again with the whole corrected deck" in notes
    assert _build_notes(DeckPlan.model_validate({"slides": [COVER]}), [], []) == ""


@pytest.mark.asyncio
async def test_a_renderer_finding_reaches_the_model_in_the_review_notes(monkeypatch):
    """An agenda announcing parts the deck never covers was only logged; the
    model now reads it, with its remedy, after the unchanged success prefix."""
    agenda = {
        "title": "Agenda",
        "kind": "agenda",
        "items": [{"heading": f"Part {i}"} for i in range(4)],
    }
    text, result = await _build(monkeypatch, slides=[COVER, agenda])
    assert not result.is_error, text
    assert tools_mod.deck_delivered(_turn(text))
    review = text[text.index("\nTo review") :]
    assert (
        "Slide 2: the agenda announces 4 parts but only 0 slide(s) follow it. Add the "
        "missing slides or remove those parts from the agenda; otherwise nothing to do."
    ) in review


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
