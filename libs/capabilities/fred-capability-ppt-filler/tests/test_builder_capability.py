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

"""``ppt_builder`` save-time states, the build tool and the routes, fully
offline on the in-memory port fakes."""

from __future__ import annotations

import io
from typing import Any, cast

import pytest
from builder_decks import build_showcase_template
from deck_builders import png_bytes
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_ppt_filler.builder import capability as capability_mod
from fred_capability_ppt_filler.builder import tools as tools_mod
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.capability import (
    PPT_BUILDER_PATTERNS_KEY,
    PPT_BUILDER_TEMPLATE_KEY,
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.models import PatternOverride, TemplateInventory
from fred_capability_ppt_filler.builder.theme import default_theme
from fred_capability_ppt_filler.builder.tools import (
    BUILD_TOOL_NAME,
    LIST_IMAGES_TOOL_NAME,
)
from fred_capability_ppt_filler.capability import TEMPLATE_SLOT
from fred_capability_ppt_filler.fill import PptPreviewPart
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
    UploadedFile,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeAssets, FakeDocs, FakeFolders, FakeWorkspace
from pptx import Presentation

TEMPLATE = build_showcase_template()


def _save_ctx(assets=None) -> SaveContext:
    return SaveContext(
        identity=CapabilityIdentity(
            user_id="u-1",
            session_id="s-1",
            team_id="team-42",
            agent_instance_id="inst-7",
        ),
        services=RuntimeServices(agent_assets=assets),
    )


def _uploads(content: bytes):
    return {TEMPLATE_SLOT: [UploadedFile(filename="template.pptx", content=content)]}


@pytest.fixture
def preview_union():
    """Register ``PptPreviewPart`` in the runtime ``UiPart`` union, as the
    capability registry does at pod boot (see ``test_fill.py``)."""
    from fred_sdk.contracts.ui_part_union import rebuild_ui_part_union

    rebuild_ui_part_union([PptPreviewPart])
    yield
    rebuild_ui_part_union(())


async def _pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return b"%PDF-fake"


async def _no_pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return None


# --- validate_config -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_analyses_stores_template_and_thumbnails_and_keeps_no_bytes(
    monkeypatch,
):
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _pdf)
    assets = FakeAssets()
    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(), _uploads(TEMPLATE), _save_ctx(assets)
    )
    assert stored.inventory is not None and stored.inventory.summary().patterns > 5
    assert set(assets.blobs) == {PPT_BUILDER_TEMPLATE_KEY, PPT_BUILDER_PATTERNS_KEY}
    assert assets.blobs[PPT_BUILDER_TEMPLATE_KEY] == TEMPLATE
    assert (
        stored.patterns_path
        == f"teams/team-42/agents/inst-7/config/{PPT_BUILDER_PATTERNS_KEY}"
    )
    assert TEMPLATE[:4] not in stored.model_dump_json().encode()


@pytest.mark.asyncio
async def test_upload_without_pdf_conversion_still_saves(monkeypatch):
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _no_pdf)
    assets = FakeAssets()
    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(), _uploads(TEMPLATE), _save_ctx(assets)
    )
    assert stored.patterns_path is None
    assert set(assets.blobs) == {PPT_BUILDER_TEMPLATE_KEY}


@pytest.mark.asyncio
async def test_upload_keeps_matching_overrides_and_drops_the_rest(monkeypatch):
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config = PptBuilderConfig(
        overrides=[
            PatternOverride(pattern_id="layout:0", label="Cover"),
            PatternOverride(pattern_id="slide:999", included=False),
        ]
    )
    stored = await PptBuilderCapability().validate_config(
        config, _uploads(TEMPLATE), _save_ctx(FakeAssets())
    )
    assert [o.pattern_id for o in stored.overrides] == ["layout:0"]


@pytest.mark.asyncio
async def test_unreadable_or_oversized_upload_rejects_without_storing(monkeypatch):
    assets = FakeAssets()
    with pytest.raises(ValueError, match="could not be read"):
        await PptBuilderCapability().validate_config(
            PptBuilderConfig(), _uploads(b"nope"), _save_ctx(assets)
        )
    monkeypatch.setattr(capability_mod, "MAX_TEMPLATE_UPLOAD_BYTES", 10)
    with pytest.raises(ValueError, match="exceeds"):
        await PptBuilderCapability().validate_config(
            PptBuilderConfig(), _uploads(TEMPLATE), _save_ctx(assets)
        )
    assert assets.blobs == {}


@pytest.mark.asyncio
async def test_no_upload_is_an_ordinary_edit_or_the_built_in_theme():
    inventory = default_theme()[1]
    config = PptBuilderConfig(
        inventory=inventory,
        overrides=[
            PatternOverride(pattern_id=inventory.patterns[0].id, label="x"),
            PatternOverride(pattern_id="gone"),
        ],
    )
    stored = await PptBuilderCapability().validate_config(config, {}, _save_ctx())
    assert stored.inventory is inventory or stored.inventory == inventory
    assert [o.pattern_id for o in stored.overrides] == [inventory.patterns[0].id]

    themed = await PptBuilderCapability().validate_config(
        PptBuilderConfig(), {}, _save_ctx()
    )
    assert themed.inventory is None


@pytest.mark.asyncio
async def test_an_older_analysis_is_recomputed_from_the_stored_template():
    from fred_capability_ppt_filler.builder.analysis import ANALYSIS_VERSION

    fresh = analyze_template(TEMPLATE).inventory
    assert fresh is not None and fresh.analysis_version == ANALYSIS_VERSION
    stale = fresh.model_copy(
        update={"analysis_version": 0, "patterns": [], "design_system": None}
    )
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})

    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(inventory=stale), {}, _save_ctx(assets)
    )

    assert stored.inventory is not None
    assert stored.inventory.analysis_version == ANALYSIS_VERSION
    assert [p.id for p in stored.inventory.patterns] == [p.id for p in fresh.patterns]
    assert assets.store_calls == []  # the template and its thumbnails are untouched
    # The design system arrives the same way: an inventory saved before it
    # existed gets one back from the template already stored, no re-upload.
    assert stale.design_system is None
    assert stored.inventory.design_system is not None
    assert stored.inventory.design_system.complete


@pytest.mark.asyncio
async def test_an_inventory_saved_without_a_design_system_still_loads():
    """Additive: the field is absent from every config stored before it existed."""
    fresh = analyze_template(TEMPLATE).inventory
    assert fresh is not None
    payload = fresh.model_dump()
    payload.pop("design_system")

    reloaded = TemplateInventory.model_validate(payload)

    assert reloaded.design_system is None
    assert [p.id for p in reloaded.patterns] == [p.id for p in fresh.patterns]


@pytest.mark.asyncio
async def test_a_current_analysis_is_not_recomputed_and_a_failure_keeps_it():
    fresh = analyze_template(TEMPLATE).inventory
    assert fresh is not None
    assets = FakeAssets()  # fetching the template would raise

    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(inventory=fresh), {}, _save_ctx(assets)
    )
    assert stored.inventory == fresh

    stale = fresh.model_copy(update={"analysis_version": 0})
    kept = await PptBuilderCapability().validate_config(
        PptBuilderConfig(inventory=stale), {}, _save_ctx(assets)
    )
    assert kept.inventory == stale


# --- tools --------------------------------------------------------------------------------


def _ctx(
    config: PptBuilderConfig, *, assets=None, docs=None, folders=None, workspace=None
):
    return CapabilityContext(
        identity=CapabilityIdentity(user_id="u-1", session_id="sess-9"),
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
    from fred_capability_ppt_filler.builder.analysis import analyze_template

    inventory = analyze_template(TEMPLATE).inventory
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})
    return PptBuilderConfig(inventory=inventory), assets


def test_tools_and_catalogue_follow_the_effective_inventory():
    config, assets = _configured()
    excluded = PatternOverride(
        pattern_id="layout:0", included=False, label="Hidden cover"
    )
    config = config.model_copy(update={"overrides": [excluded]})
    tools = _tools(_ctx(config, assets=assets))
    assert set(tools) == {BUILD_TOOL_NAME, LIST_IMAGES_TOOL_NAME}
    description = tools[BUILD_TOOL_NAME].description
    assert "layout:1 [content]" in description
    assert "Hidden cover" not in description
    assert "items up to 4 [number, heading]" in description
    schema = tools[BUILD_TOOL_NAME].args_schema.model_json_schema()
    choices = schema["$defs"]["BuildSlide"]["properties"]["pattern"]["enum"]
    assert "layout:1" in choices and "layout:0" not in choices and "content" in choices


@pytest.mark.asyncio
async def test_build_returns_preview_part_and_uploads_deck(monkeypatch, preview_union):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _pdf)
    config, assets = _configured()
    workspace = FakeWorkspace()
    tools = _tools(_ctx(config, assets=assets, workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[
            {"pattern": "title", "title": "Kick-off", "subtitle": "Team"},
            {"pattern": "layout:1", "title": "Plan", "bullets": ["one", "- two"]},
        ],
        file_name="Kick off 2026",
    )
    assert not result.is_error
    (part,) = result.ui_parts
    assert isinstance(part, PptPreviewPart)
    assert part.file_name == "Kick off 2026.pptx"
    # The card opens this capability's pane: an agent may not have ppt_filler.
    assert part.capability_id == "ppt_builder"
    assert "2 slides" in text
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
async def test_build_without_template_uses_the_built_in_theme(monkeypatch):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    workspace = FakeWorkspace()
    tools = _tools(_ctx(PptBuilderConfig(), workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[
            {
                "pattern": "cards",
                "title": "KPIs",
                "items": [{"number": "42%", "label": "Margin"}],
            }
        ]
    )
    assert not result.is_error
    assert "only the download" in text
    assert result.ui_parts[0].kind.value == "download"
    deck = Presentation(io.BytesIO(workspace.writes[0]["content"]))
    assert len(deck.slides) == 1


@pytest.mark.asyncio
async def test_empty_plan_is_an_error_the_user_can_read():
    config, assets = _configured()
    tools = _tools(_ctx(config, assets=assets))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[{"pattern": "content"}]
    )
    assert result.is_error and "no content" in text
    # The text travels in the result so the runtime shows it, not a generic failure.
    assert result.blocks and result.blocks[0].text == text


@pytest.mark.asyncio
async def test_malformed_plan_from_a_small_model_still_builds(monkeypatch):
    """The shape of a real failing call: invented `slide:<n>` ids, a column
    pattern given as a slide number, stray strings in `slides`, bullets as one
    string, numbers as integers, an unknown top-level key."""
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    workspace = FakeWorkspace()
    tools = _tools(_ctx(config, assets=assets, workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
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
                "pattern": "cards",
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
    assert "not a slide object" in text and "slide:999" in text


@pytest.mark.asyncio
async def test_build_places_images_from_documents_and_reports_bad_ones(monkeypatch):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    assert config.inventory is not None
    photo = next(p for p in config.inventory.patterns if p.label == "Photo")
    docs = FakeDocs(
        {"img-1": (png_bytes(20, 10), "image/png"), "txt-1": (b"hello", "text/plain")}
    )
    workspace = FakeWorkspace()
    tools = _tools(_ctx(config, assets=assets, docs=docs, workspace=workspace))
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[{"pattern": photo.id, "title": "Site", "image": "img-1"}]
    )
    assert not result.is_error
    assert docs.fetch_uids == ["img-1"]
    # A bad image reference costs the picture, never the deck.
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[{"pattern": photo.id, "title": "Site", "image": "txt-1"}]
    )
    assert not result.is_error and "'txt-1' is not a usable image" in text
    text, result = await tools[BUILD_TOOL_NAME].coroutine(
        slides=[{"pattern": photo.id, "title": "Site", "image": "missing"}]
    )
    assert not result.is_error and "'missing' is not a usable image" in text


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


# --- routes ---------------------------------------------------------------------------------


def _client() -> TestClient:
    app = FastAPI()
    router = PptBuilderCapability.manifest.router
    assert router is not None
    app.include_router(router, prefix="/capabilities/ppt_builder")
    return TestClient(app)


def test_analyze_route_returns_inventory_and_summary():
    response = _client().post(
        "/capabilities/ppt_builder/analyze", files={"file": ("t.pptx", TEMPLATE)}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == []
    assert body["summary"]["layouts"] == 11
    assert any(p["intent"] == "agenda" for p in body["inventory"]["patterns"])


def test_analyze_route_reports_unreadable_upload():
    body = (
        _client()
        .post("/capabilities/ppt_builder/analyze", files={"file": ("t.pptx", b"nope")})
        .json()
    )
    assert [e["code"] for e in body["errors"]] == ["invalid_upload"]


def test_preview_routes_return_pdf_or_503(monkeypatch):
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _pdf)
    response = _client().post(
        "/capabilities/ppt_builder/preview", files={"file": ("t.pptx", TEMPLATE)}
    )
    assert response.status_code == 200 and response.content == b"%PDF-fake"
    assert (
        _client().get("/capabilities/ppt_builder/theme/preview.pdf").status_code == 200
    )
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _no_pdf)
    assert (
        _client()
        .post("/capabilities/ppt_builder/preview", files={"file": ("t.pptx", TEMPLATE)})
        .status_code
        == 503
    )


def test_theme_preview_is_converted_once_per_process(monkeypatch):
    calls = []

    async def _counting(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
        calls.append(suffix)
        return b"%PDF-theme"

    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _counting)
    monkeypatch.setattr(capability_mod, "_theme_pdf", None)
    client = _client()
    assert (
        client.get("/capabilities/ppt_builder/theme/preview.pdf").content
        == b"%PDF-theme"
    )
    assert (
        client.get("/capabilities/ppt_builder/theme/preview.pdf").content
        == b"%PDF-theme"
    )
    assert calls == [".pptx"]


def test_patterns_preview_keeps_one_page_per_pattern_even_for_uncopyable_slides():
    from fred_capability_ppt_filler.builder.analysis import analyze_template
    from fred_capability_ppt_filler.builder.preview import build_patterns_deck

    inventory = analyze_template(TEMPLATE).inventory
    assert inventory is not None
    chart = next(p for p in inventory.patterns if p.exclusion_reason == "chart")
    chart.exclusion_reason = "unsupported_parts"
    deck = Presentation(io.BytesIO(build_patterns_deck(TEMPLATE, inventory)))
    assert len(deck.slides) == len(inventory.patterns)


@pytest.mark.asyncio
async def test_plan_made_of_fixed_slides_by_id_is_accepted(monkeypatch):
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    config, assets = _configured()
    assert config.inventory is not None
    fixed = next(
        p for p in config.inventory.patterns if p.intent == "fixed" and p.included
    )
    tools = _tools(_ctx(config, assets=assets))
    _, result = await tools[BUILD_TOOL_NAME].coroutine(slides=[{"pattern": fixed.id}])
    assert not result.is_error


def test_theme_route_lists_every_intent():
    body = _client().get("/capabilities/ppt_builder/theme").json()
    intents = {p["intent"] for p in body["inventory"]["patterns"] if p["included"]}
    assert {
        "title",
        "section",
        "agenda",
        "content",
        "two_columns",
        "comparison",
        "image_text",
        "cards",
        "steps",
        "statement",
        "contact",
        "fixed",
    } <= intents


@pytest.mark.asyncio
async def test_several_builds_of_one_answer_land_on_one_preview(
    monkeypatch, preview_union
):
    """A model that splits a deck across calls used to deliver one preview card
    per fragment, each holding a truncated presentation. They share a key, so
    the reader is shown one deck."""
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _pdf)
    config, assets = _configured()
    workspace = FakeWorkspace()
    tools = _tools(_ctx(config, assets=assets, workspace=workspace))
    previews = []
    for title in ("Part one", "Part two", "Part three"):
        _, result = await tools[BUILD_TOOL_NAME].coroutine(
            slides=[{"pattern": "title", "title": title}]
        )
        previews.append(cast(Any, result.ui_parts[0]).preview_id)
    assert len(set(previews)) == 1, previews


def test_the_tool_tells_the_agent_one_call_builds_the_whole_deck():
    """Splitting is what produced several truncated decks in one answer."""
    config, assets = _configured()
    description = _tools(_ctx(config, assets=assets))[BUILD_TOOL_NAME].description
    assert "ONE call builds the WHOLE deck" in description
    assert "Never split a deck across several calls" in description


# -- the catalogue the agent is shown (D3) ------------------------------------


def test_the_catalogue_offers_what_the_template_can_compose_not_only_what_it_drew():
    """The bug this guards: `with_composed_patterns` existed, was tested, and
    had no caller. The agent then saw only the designer's own slides — on a
    template holding just a cover, that meant every slide landed on the cover.
    """
    from fred_capability_ppt_filler.builder.analysis import analyze_presentation
    from fred_capability_ppt_filler.builder.capability import _composable
    from fred_capability_ppt_filler.builder.plan import included_patterns
    from tests.deck_builders import build_cover_only_template

    inventory = analyze_presentation(build_cover_only_template())
    offered = included_patterns(inventory)

    assert not any(p.source == "composed" for p in offered)
    # Nothing in this template can carry a list, a figure or a comparison.
    assert all(p.intent in ("title", "fixed") for p in offered)

    enriched = included_patterns(_composable(inventory))
    composed = [p for p in enriched if p.source == "composed"]

    assert composed, "the agent is still offered nothing to compose with"
    assert {"cards", "steps", "comparison", "statement"} <= {p.intent for p in composed}
    # The template's own come first: order is what a reader reads as preference.
    assert enriched[: len(offered)] == offered


def test_an_author_can_still_exclude_a_composed_pattern():
    """Composed patterns join the catalogue BEFORE overrides are applied, so
    excluding one works exactly as excluding the template's own."""
    from fred_capability_ppt_filler.builder.analysis import analyze_presentation
    from fred_capability_ppt_filler.builder.capability import _composable
    from fred_capability_ppt_filler.builder.models import PatternOverride
    from fred_capability_ppt_filler.builder.overrides import apply_overrides
    from fred_capability_ppt_filler.builder.plan import included_patterns
    from tests.deck_builders import build_cover_only_template

    enriched = _composable(analyze_presentation(build_cover_only_template()))
    target = next(p for p in enriched.patterns if p.id == "composed:card_row:3")

    effective, _ = apply_overrides(
        enriched, [PatternOverride(pattern_id=target.id, included=False)]
    )

    assert target.id not in {p.id for p in included_patterns(effective)}
