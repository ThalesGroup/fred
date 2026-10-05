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

"""``ppt_builder`` save-time states and the routes, fully offline on the
in-memory port fakes (the tools: ``test_build_tool.py``)."""

from __future__ import annotations

import io

import pytest
from builder_decks import build_showcase_template
from fastapi import FastAPI
from fastapi.testclient import TestClient
from fred_capability_ppt_filler.builder import capability as capability_mod
from fred_capability_ppt_filler.builder.analysis import analyze_template
from fred_capability_ppt_filler.builder.capability import (
    PPT_BUILDER_PATTERNS_KEY,
    PPT_BUILDER_TEMPLATE_KEY,
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.models import PatternOverride
from fred_capability_ppt_filler.builder.theme import default_theme
from fred_capability_ppt_filler.capability import TEMPLATE_SLOT
from fred_capability_ppt_filler.fill import PptPreviewPart
from fred_sdk.contracts.capability import (
    CapabilityIdentity,
    SaveContext,
    UploadedFile,
)
from fred_sdk.contracts.runtime import RuntimeServices
from port_fakes import FakeAssets
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
    stale = fresh.model_copy(update={"analysis_version": 0, "patterns": []})
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})

    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(inventory=stale), {}, _save_ctx(assets)
    )

    assert stored.inventory is not None
    assert stored.inventory.analysis_version == ANALYSIS_VERSION
    assert [p.id for p in stored.inventory.patterns] == [p.id for p in fresh.patterns]
    assert assets.store_calls == []  # the template and its thumbnails are untouched


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
    assert any(p["kind"] == "agenda" for p in body["inventory"]["patterns"])


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


def test_theme_route_lists_every_kind():
    body = _client().get("/capabilities/ppt_builder/theme").json()
    kinds = {p["kind"] for p in body["inventory"]["patterns"] if p["included"]}
    assert {
        "cover",
        "section",
        "agenda",
        "bullets",
        "two_columns",
        "comparison",
        "image_text",
        "figures",
        "process",
        "quote",
        "closing",
    } <= kinds
