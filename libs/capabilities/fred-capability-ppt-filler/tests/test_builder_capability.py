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

"""``ppt_builder`` save, readiness, analysis routes and turn wiring, fully
offline on the port fakes and an in-memory SQLite analysis table (the tools:
``test_build_tool.py``; the job: ``test_analysis_job.py``)."""

from __future__ import annotations

import hashlib
import io
from typing import Any, cast

import httpx
import pytest
from analysis_db import age_row, drain
from builder_decks import build_showcase_template
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder import capability as capability_mod
from fred_capability_ppt_filler.builder import tools as tools_mod
from fred_capability_ppt_filler.builder.analysis_job import get_analysis_store
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.capability import (
    PPT_BUILDER_TEMPLATE_KEY,
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.models import PatternOverride
from fred_capability_ppt_filler.builder.tools import BUILD_TOOL_NAME
from fred_capability_ppt_filler.capability import TEMPLATE_SLOT
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
    SaveContext,
    UploadedFile,
    asset_keys,
    reset_scope_private,
)
from fred_sdk.contracts.runtime import (
    CapabilityTeamAuthorizer,
    RuntimeServices,
    capability_team_authorizer,
)
from port_fakes import FakeAssets, FakeWorkspace
from pptx import Presentation

TEMPLATE = build_showcase_template()
SHA = hashlib.sha256(TEMPLATE).hexdigest()
IDENTITY = CapabilityIdentity(
    user_id="u-1", session_id="s-1", team_id="team-42", agent_instance_id="inst-7"
)


def _save_ctx(assets=None, identity: CapabilityIdentity = IDENTITY) -> SaveContext:
    return SaveContext(identity=identity, services=RuntimeServices(agent_assets=assets))


def _uploads(content: bytes):
    return {TEMPLATE_SLOT: [UploadedFile(filename="template.pptx", content=content)]}


async def _pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return b"%PDF-fake"


async def _no_pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
    return None


@pytest.fixture(autouse=True)
def offline_conversion(monkeypatch):
    monkeypatch.setattr(analysis_job, "convert_office_bytes_to_pdf", _pdf)


async def _analysed(config: PptBuilderConfig | None = None) -> PptBuilderConfig:
    stored = await PptBuilderCapability().validate_config(
        config or PptBuilderConfig(use_vision=False),
        _uploads(TEMPLATE),
        _save_ctx(FakeAssets()),
    )
    await drain()
    return stored


# --- validate_config -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_stores_the_template_and_keeps_only_its_hash(analysis_db):
    assets = FakeAssets()
    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(), _uploads(TEMPLATE), _save_ctx(assets)
    )
    assert stored.template_sha256 == SHA
    assert set(assets.blobs) == {PPT_BUILDER_TEMPLATE_KEY}
    dumped = stored.model_dump()
    assert "inventory" not in dumped and "patterns_path" not in dumped


@pytest.mark.asyncio
async def test_unreadable_or_oversized_upload_rejects_without_storing(
    analysis_db, monkeypatch
):
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
    assert await get_analysis_store().get("inst-7") is None


@pytest.mark.asyncio
async def test_overrides_are_pruned_once_the_analysis_is_known(analysis_db):
    stored = await _analysed()
    first = (await get_analysis_store().get("inst-7")).inventory()  # type: ignore[union-attr]
    assert first is not None
    config = stored.model_copy(
        update={
            "overrides": [
                PatternOverride(pattern_id=first.patterns[0].id, label="Cover"),
                PatternOverride(pattern_id="slide:999", included=False),
            ]
        }
    )
    kept = await PptBuilderCapability().validate_config(config, {}, _save_ctx())
    assert [o.pattern_id for o in kept.overrides] == [first.patterns[0].id]


@pytest.mark.asyncio
async def test_no_template_prunes_against_the_built_in_template(analysis_db):
    inventory = builtin_template()[1]
    config = PptBuilderConfig(
        overrides=[
            PatternOverride(pattern_id=inventory.patterns[0].id, label="x"),
            PatternOverride(pattern_id="gone"),
        ]
    )
    stored = await PptBuilderCapability().validate_config(config, {}, _save_ctx())
    assert stored.template_sha256 is None
    assert [o.pattern_id for o in stored.overrides] == [inventory.patterns[0].id]


@pytest.mark.asyncio
async def test_a_revalidation_without_an_instance_has_no_side_effect(analysis_db):
    config = PptBuilderConfig(template_sha256=SHA)
    anonymous = CapabilityIdentity(user_id="anonymous", team_id="team-42")
    stored = await PptBuilderCapability().validate_config(
        config, {}, _save_ctx(identity=anonymous)
    )
    assert stored == config
    assert await get_analysis_store().get("inst-7") is None


# --- Copy to another scope ---------------------------------------------------------


def test_the_built_in_template_has_no_file_to_copy():
    """A stale key never survives a return to the built-in template: a copy
    would otherwise re-submit a file the agent no longer uses."""
    config = PptBuilderConfig.model_validate(
        {"template_key": PPT_BUILDER_TEMPLATE_KEY, "template_sha256": None}
    )
    assert config.template_key is None
    assert asset_keys(reset_scope_private(config)) == {}
    assert PptBuilderConfig.model_validate({"template_sha256": SHA}).template_key == (
        PPT_BUILDER_TEMPLATE_KEY
    )


@pytest.mark.asyncio
async def test_copy_to_another_scope_recreates_the_template_and_its_analysis(
    analysis_db,
):
    """What the runtime's copy-config does: reset scope-private settings, fetch the
    AssetKey files in the source, re-submit them to validate_config in the target."""
    source_assets = FakeAssets()
    stored = await PptBuilderCapability().validate_config(
        PptBuilderConfig(use_vision=True, labelling_model="vision-profile"),
        _uploads(TEMPLATE),
        _save_ctx(source_assets),
    )
    await drain()
    reset = reset_scope_private(stored)
    assert reset.labelling_model == "vision-profile"
    assert asset_keys(reset) == {TEMPLATE_SLOT: [PPT_BUILDER_TEMPLATE_KEY]}

    target_assets = FakeAssets()
    target = CapabilityIdentity(
        user_id="u-2", team_id="team-99", agent_instance_id="inst-copy"
    )
    copied = await PptBuilderCapability().validate_config(
        PptBuilderConfig.model_validate(reset.model_dump(mode="json")),
        {
            TEMPLATE_SLOT: [
                UploadedFile(
                    filename=PPT_BUILDER_TEMPLATE_KEY,
                    content=await source_assets.fetch(PPT_BUILDER_TEMPLATE_KEY),
                )
            ]
        },
        _save_ctx(target_assets, identity=target),
    )
    await drain()

    assert target_assets.blobs == {PPT_BUILDER_TEMPLATE_KEY: TEMPLATE}
    assert copied.template_sha256 == SHA
    record = await get_analysis_store().get("inst-copy")
    assert record is not None and record.team_id == "team-99"
    assert record.template_sha256 == SHA


@pytest.mark.asyncio
async def test_readiness_without_a_template_is_ready_at_once():
    verdict = await PptBuilderCapability().readiness(PptBuilderConfig(), IDENTITY)
    assert verdict.state == "ready"


# --- analysis routes -------------------------------------------------------------------------


class _Authorizer(CapabilityTeamAuthorizer):
    def __init__(self, editor_of: set[str]) -> None:
        self.editor_of = editor_of

    async def require_agent_editor(self, team_id: str) -> None:
        if team_id not in self.editor_of:
            raise HTTPException(status_code=403, detail="Not an agent editor.")


def _async_client(editor_of: set[str]) -> httpx.AsyncClient:
    app = FastAPI()
    router = PptBuilderCapability.manifest.router
    assert router is not None
    app.include_router(router, prefix="/capabilities/ppt_builder")
    app.dependency_overrides[capability_team_authorizer] = lambda: _Authorizer(
        editor_of
    )
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pod"
    )


_BASE = "/capabilities/ppt_builder/analysis/inst-7"


@pytest.mark.asyncio
async def test_a_non_editor_is_refused_everywhere(analysis_db):
    await _analysed()
    async with _async_client({"other-team"}) as client:
        for response in (
            await client.get(_BASE),
            await client.get(f"{_BASE}/patterns.pdf"),
            await client.post(f"{_BASE}/rerun"),
        ):
            assert response.status_code == 403


@pytest.mark.asyncio
async def test_an_editor_sees_status_thumbnails_and_inventory(analysis_db):
    await _analysed()
    async with _async_client({"team-42"}) as client:
        body = (await client.get(_BASE)).json()
        assert body["status"] == "succeeded" and body["current"] is True
        assert body["template_sha256"] == SHA and body["labelling_key"] == "rules"
        assert body["has_thumbnails"] is True and body["summary"]["layouts"] == 10
        assert any(p["kind"] == "agenda" for p in body["inventory"]["patterns"])
        pdf = await client.get(f"{_BASE}/patterns.pdf")
        assert pdf.status_code == 200 and pdf.content == b"%PDF-fake"
        assert (
            await client.get("/capabilities/ppt_builder/analysis/x")
        ).status_code == 404


@pytest.mark.asyncio
async def test_rerun_restarts_a_failed_or_interrupted_analysis_only(analysis_db):
    await _analysed()
    async with _async_client({"team-42"}) as client:
        assert (await client.post(f"{_BASE}/rerun")).status_code == 409
        await age_row(analysis_db, "inst-7", status="running")
        body = (await client.post(f"{_BASE}/rerun")).json()
        assert body["status"] == "pending"
        assert (await client.post(f"{_BASE}/rerun")).status_code == 409
        await drain()
        assert (await client.get(_BASE)).json()["status"] == "succeeded"


# --- turn wiring -------------------------------------------------------------------------------


def _turn_ctx(config: PptBuilderConfig, assets=None) -> CapabilityContext:
    return CapabilityContext(
        identity=IDENTITY,
        config=config,
        turn_options=EmptyModel(),
        services=RuntimeServices(agent_assets=assets, workspace_fs=FakeWorkspace()),
    )


def _middleware(ctx: CapabilityContext) -> Any:
    (middleware,) = PptBuilderCapability().middleware(ctx)
    return cast(Any, middleware)


@pytest.mark.asyncio
async def test_the_tool_refuses_while_the_analysis_is_pending(analysis_db):
    stored = PptBuilderConfig(template_sha256=SHA, use_vision=False)
    await get_analysis_store().start(
        instance_id="inst-7",
        team_id="team-42",
        saved_by="u-1",
        template_sha256=SHA,
        labelling_key="rules",
        template=TEMPLATE,
    )
    tools = {t.name: t for t in _middleware(_turn_ctx(stored)).tools}
    text, result = await tools[BUILD_TOOL_NAME].coroutine(slides=[{"title": "Hi"}])
    assert result.is_error and "still being analysed" in text

    await age_row(analysis_db, "inst-7", status="failed")
    tools = {t.name: t for t in _middleware(_turn_ctx(stored)).tools}
    text, result = await tools[BUILD_TOOL_NAME].coroutine(slides=[{"title": "Hi"}])
    assert result.is_error and "re-run the analysis" in text


@pytest.mark.asyncio
async def test_a_succeeded_analysis_gives_the_model_the_templates_catalogue(
    analysis_db, monkeypatch
):
    stored = await _analysed()
    analysis_job.clear_caches()  # a pod that has not read it yet
    assets = FakeAssets({PPT_BUILDER_TEMPLATE_KEY: TEMPLATE})
    middleware = _middleware(_turn_ctx(stored, assets))
    deferred = next(t for t in middleware.tools if t.name == BUILD_TOOL_NAME)
    assert "still being analysed" in deferred.description

    seen: list = []

    class _Request:
        system_prompt = "base"
        tools = middleware.tools

        def override(self, **update):
            seen.append(update)
            return self

    async def _handler(request):
        return request

    await middleware.awrap_model_call(_Request(), _handler)
    (update,) = seen
    shown = next(t for t in update["tools"] if t.name == BUILD_TOOL_NAME)
    assert "- process:" in shown.description
    assert "optionally its kind" in update["system_message"].content
    assert "Build directly" in update["system_message"].content

    # The registered tool executes with the template's tool, from validated args.
    monkeypatch.setattr(tools_mod, "convert_office_bytes_to_pdf", _no_pdf)
    message = await deferred.ainvoke(
        {
            "type": "tool_call",
            "id": "call-1",
            "name": BUILD_TOOL_NAME,
            "args": {
                "slides": [{"title": "Kick-off"}, {"title": "Plan", "bullets": ["a"]}]
            },
        }
    )
    assert "2 slides" in message.content and not message.artifact.is_error

    # The next turn on this pod builds the template's tools without a DB read.
    analysis_job.set_store_provider(lambda: (_ for _ in ()).throw(AssertionError()))
    again = _middleware(_turn_ctx(stored, FakeAssets()))
    built = next(t for t in again.tools if t.name == BUILD_TOOL_NAME)
    assert "- process:" in built.description


# --- routes ---------------------------------------------------------------------------------


def _client() -> TestClient:
    app = FastAPI()
    router = PptBuilderCapability.manifest.router
    assert router is not None
    app.include_router(router, prefix="/capabilities/ppt_builder")
    return TestClient(app)


def test_builtin_patterns_returns_pdf_or_503(monkeypatch):
    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _pdf)
    assert (
        _client().get("/capabilities/ppt_builder/builtin/patterns.pdf").status_code
        == 200
    )


def test_builtin_patterns_are_converted_once_per_process(monkeypatch):
    calls = []

    async def _counting(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
        calls.append(suffix)
        return b"%PDF-builtin"

    monkeypatch.setattr(capability_mod, "convert_office_bytes_to_pdf", _counting)
    monkeypatch.setattr(capability_mod, "_builtin_pdf", None)
    client = _client()
    assert (
        client.get("/capabilities/ppt_builder/builtin/patterns.pdf").content
        == b"%PDF-builtin"
    )
    assert (
        client.get("/capabilities/ppt_builder/builtin/patterns.pdf").content
        == b"%PDF-builtin"
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


def test_builtin_route_lists_the_template_kinds():
    body = _client().get("/capabilities/ppt_builder/builtin").json()
    kinds = {p["kind"] for p in body["inventory"]["patterns"] if p["included"]}
    assert {
        "section",
        "agenda",
        "bullets",
        "two_columns",
        "comparison",
        "figures",
        "process",
        "closing",
    } <= kinds
