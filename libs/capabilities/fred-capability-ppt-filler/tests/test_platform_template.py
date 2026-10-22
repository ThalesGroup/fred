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

"""The platform default template: manager-only routes, its row in the analysis
table, and how agents without a template of their own resolve it."""

from __future__ import annotations

import hashlib
import time
from typing import Any, cast

import httpx
import pytest
from analysis_db import age_row, drain
from builder_decks import build_showcase_template
from fastapi import FastAPI, HTTPException
from fred_capability_ppt_filler.builder import analysis_job
from fred_capability_ppt_filler.builder import capability as capability_mod
from fred_capability_ppt_filler.builder.analysis_job import (
    PLATFORM_ID,
    PLATFORM_NEXT_ID,
    get_analysis_store,
    platform_snapshot,
)
from fred_capability_ppt_filler.builder.builtin import builtin_template
from fred_capability_ppt_filler.builder.capability import (
    PptBuilderCapability,
    PptBuilderConfig,
)
from fred_capability_ppt_filler.builder.tools import BUILD_TOOL_NAME
from fred_sdk.contracts.capability import (
    CapabilityContext,
    CapabilityIdentity,
    EmptyModel,
)
from fred_sdk.contracts.runtime import (
    CapabilityModelPort,
    CapabilityTeamAuthorizer,
    RuntimeServices,
    capability_platform_model,
    capability_team_authorizer,
)
from port_fakes import FakeWorkspace

TEMPLATE = build_showcase_template()
SHA = hashlib.sha256(TEMPLATE).hexdigest()
OTHER = builtin_template()[0]
OTHER_SHA = hashlib.sha256(OTHER).hexdigest()
_BASE = "/capabilities/ppt_builder/platform"


class _Port(CapabilityModelPort):
    async def ainvoke(self, messages, *, profile_id=None, require_vision=False):
        raise AssertionError("label_inventory is faked here")


PORT = _Port()


class _Authorizer(CapabilityTeamAuthorizer):
    def __init__(self, manager: bool) -> None:
        self.manager = manager

    async def require_agent_editor(self, team_id: str) -> None:
        return None  # every team: only the platform guard may refuse

    async def require_capability_manager(self) -> None:
        if not self.manager:
            raise HTTPException(status_code=403, detail="Not a capability manager.")


@pytest.fixture(autouse=True)
def offline_conversion(monkeypatch):
    labelled: list[tuple[Any, Any, bool]] = []

    async def _pdf(_bytes: bytes, *, suffix: str, timeout_seconds: float = 0):
        return b"%PDF-thumbs"

    async def _labels(inventory, template, pdf, port, *, profile_id, use_vision):
        labelled.append((port, profile_id, use_vision))
        return inventory

    monkeypatch.setattr(analysis_job, "convert_office_bytes_to_pdf", _pdf)
    monkeypatch.setattr(analysis_job, "label_inventory", _labels)
    return labelled


def _client(*, manager: bool) -> httpx.AsyncClient:
    app = FastAPI()
    router = PptBuilderCapability.manifest.router
    assert router is not None
    app.include_router(router, prefix="/capabilities/ppt_builder")
    app.dependency_overrides[capability_team_authorizer] = lambda: _Authorizer(manager)
    app.dependency_overrides[capability_platform_model] = lambda: PORT
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://pod"
    )


async def _upload(client: httpx.AsyncClient, content: bytes = TEMPLATE, **form):
    return await client.put(
        f"{_BASE}/template",
        files={"file": ("brand.pptx", content)},
        data={k: str(v).lower() if isinstance(v, bool) else v for k, v in form.items()},
    )


async def _uploaded(content: bytes = TEMPLATE) -> None:
    async with _client(manager=True) as client:
        assert (await _upload(client, content)).status_code == 200
    await drain()


async def _pending_replacement(content: bytes = OTHER) -> None:
    """A replacement row with no job running: it stays pending."""
    await get_analysis_store().start(
        instance_id=PLATFORM_NEXT_ID,
        team_id=PLATFORM_ID,
        saved_by=None,
        template_sha256=hashlib.sha256(content).hexdigest(),
        labelling_key="rules",
        template=content,
        template_filename="next.pptx",
    )


async def _rows() -> tuple[Any, Any]:
    store = get_analysis_store()
    return await store.get(PLATFORM_ID), await store.get(PLATFORM_NEXT_ID)


# --- routes ------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_fred_template_is_the_default_until_a_manager_replaces_it(
    analysis_db,
):
    async with _client(manager=False) as client:
        body = (await client.get(_BASE)).json()
        assert body["analysis"] is None and body["template_filename"] is None
        assert (await client.get(f"{_BASE}/patterns.pdf")).status_code == 404


@pytest.mark.asyncio
async def test_a_non_manager_is_refused_every_write(analysis_db):
    await _uploaded()
    await _pending_replacement()
    before = await _rows()
    async with _client(manager=False) as client:
        for response in (
            await _upload(client, OTHER),
            await client.post(f"{_BASE}/analysis", json={"use_vision": False}),
            await client.put(f"{_BASE}/overrides", json={"overrides": []}),
            await client.delete(f"{_BASE}/template"),
        ):
            assert response.status_code == 403
    await drain()
    assert await _rows() == before


@pytest.mark.asyncio
async def test_a_manager_upload_is_analysed_with_the_platform_model(
    analysis_db, offline_conversion
):
    async with _client(manager=True) as client:
        response = await _upload(client)
        assert response.status_code == 200
        pending = response.json()
        assert pending["analysis"] is None  # the Fred template until it succeeds
        assert pending["replacement_filename"] == "brand.pptx"
        await drain()
        body = (await client.get(_BASE)).json()
        assert body["analysis"]["status"] == "succeeded"
        assert body["analysis"]["template_sha256"] == SHA
        assert body["template_filename"] == "brand.pptx"
        assert body["replacement"] is None
        assert body["use_vision"] is True and body["vision_profile_id"] is None
        assert (await client.get(f"{_BASE}/patterns.pdf")).content == b"%PDF-thumbs"
    # The platform's default model: the teamless port with no profile.
    assert offline_conversion == [(PORT, None, True)]
    record = await get_analysis_store().get(PLATFORM_ID)
    assert record is not None and record.team_id == PLATFORM_ID


@pytest.mark.asyncio
async def test_an_invalid_upload_keeps_the_current_default(analysis_db, monkeypatch):
    await _uploaded()
    async with _client(manager=True) as client:
        unreadable = await _upload(client, b"not a pptx")
        assert unreadable.status_code == 400
        monkeypatch.setattr(capability_mod, "MAX_TEMPLATE_UPLOAD_BYTES", 10)
        oversized = await _upload(client)
        assert oversized.status_code == 413 and "MB limit" in oversized.json()["detail"]
    current, replacement = await _rows()
    assert current is not None and current.status == "succeeded"
    assert replacement is None


@pytest.mark.asyncio
async def test_a_rerun_takes_the_vision_choice_and_leaves_agents_alone(
    analysis_db, offline_conversion
):
    store = get_analysis_store()
    await store.start(
        instance_id="inst-7",
        team_id="team-42",
        saved_by="u-1",
        template_sha256=SHA,
        labelling_key="rules",
        template=TEMPLATE,
    )
    agent_before = await store.get("inst-7")
    await _uploaded()
    async with _client(manager=True) as client:
        body = (
            await client.post(
                f"{_BASE}/analysis",
                json={"use_vision": True, "vision_profile_id": "chat.vision"},
            )
        ).json()
        assert body["vision_profile_id"] == "chat.vision"
        # The current analysis stays in use while the re-run is the replacement.
        assert body["analysis"]["status"] == "succeeded"
        assert body["replacement_filename"] == "brand.pptx"  # a re-run keeps the name
        await drain()
        assert (await client.get(_BASE)).json()["template_filename"] == "brand.pptx"
        rules = await client.post(f"{_BASE}/analysis", json={"use_vision": False})
        assert rules.json()["use_vision"] is False
        await drain()
    assert offline_conversion[1] == (PORT, "chat.vision", True)
    assert offline_conversion[2][2] is False
    assert await store.get("inst-7") == agent_before


@pytest.mark.asyncio
async def test_a_rerun_without_a_platform_template_is_404(analysis_db):
    async with _client(manager=True) as client:
        response = await client.post(f"{_BASE}/analysis", json={})
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_failed_replacement_is_rerun_in_place(analysis_db, offline_conversion):
    await _uploaded()
    await _pending_replacement()
    await age_row(analysis_db, PLATFORM_NEXT_ID, status="failed", error="Broken.")
    async with _client(manager=True) as client:
        failed = (await client.get(_BASE)).json()
        assert failed["replacement"]["status"] == "failed"
        assert failed["analysis"]["template_sha256"] == SHA
        await client.post(f"{_BASE}/analysis", json={"use_vision": False})
        await drain()
        body = (await client.get(_BASE)).json()
    assert body["analysis"]["template_sha256"] == OTHER_SHA
    assert body["template_filename"] == "next.pptx" and body["replacement"] is None


@pytest.mark.asyncio
async def test_an_interrupted_replacement_restarts_on_a_read(analysis_db):
    await _uploaded()
    await _pending_replacement()
    await age_row(analysis_db, PLATFORM_NEXT_ID)  # its job died
    async with _client(manager=False) as client:
        await client.get(_BASE)
    await drain()
    current, replacement = await _rows()
    assert current.template_sha256 == OTHER_SHA and replacement is None


@pytest.mark.asyncio
async def test_reset_returns_to_the_fred_template(analysis_db):
    await _uploaded()
    await _pending_replacement()
    async with _client(manager=True) as client:
        response = await client.delete(f"{_BASE}/template")
        assert response.status_code == 200 and response.json()["analysis"] is None
        body = (await client.get(_BASE)).json()
        assert body["analysis"] is None and body["replacement"] is None
    assert await _rows() == (None, None)


@pytest.mark.asyncio
async def test_the_agent_routes_never_serve_the_platform_row(analysis_db):
    await _uploaded()
    await _pending_replacement()
    async with _client(manager=True) as client:
        for row in (PLATFORM_ID, PLATFORM_NEXT_ID):
            for path in ("", "/patterns.pdf"):
                response = await client.get(
                    f"/capabilities/ppt_builder/analysis/{row}{path}"
                )
                assert response.status_code == 404


# --- pattern edits ----------------------------------------------------------------------------


def _first_pattern() -> str:
    from fred_capability_ppt_filler.builder.analysis import analyze_template

    inventory = analyze_template(TEMPLATE).inventory
    assert inventory is not None
    return inventory.patterns[0].id


async def _edit(client: httpx.AsyncClient, *overrides: dict) -> httpx.Response:
    return await client.put(f"{_BASE}/overrides", json={"overrides": list(overrides)})


@pytest.mark.asyncio
async def test_a_manager_edits_the_platform_slides_for_every_agent(
    analysis_db, built_on
):
    async with _client(manager=True) as client:
        assert (await _edit(client)).status_code == 404  # nothing to edit yet
    await _uploaded()
    pattern = _first_pattern()
    async with _client(manager=True) as client:
        response = await _edit(
            client,
            {"pattern_id": pattern, "included": False},
            {"pattern_id": "slide:999", "label": "Gone"},
        )
    assert response.status_code == 200
    assert response.json()["overrides"] == [
        {"pattern_id": pattern, "label": None, "kind": None, "included": False}
    ]
    await _first_model_call(_middleware())
    effective = built_on[-1]
    assert effective.pattern(pattern).included is False


@pytest.mark.asyncio
async def test_a_rerun_keeps_the_edits_and_another_file_drops_them(analysis_db):
    await _uploaded()
    pattern = _first_pattern()
    async with _client(manager=True) as client:
        await _edit(client, {"pattern_id": pattern, "label": "Kept"})
        await client.post(f"{_BASE}/analysis", json={"use_vision": False})
        await drain()
        assert (await client.get(_BASE)).json()["overrides"][0]["label"] == "Kept"
        await _upload(client, OTHER)
        assert (await client.get(_BASE)).json()["overrides"]  # until it succeeds
        await drain()
        assert (await client.get(_BASE)).json()["overrides"] == []


# --- resolution --------------------------------------------------------------------------------


def _middleware(config: PptBuilderConfig | None = None) -> Any:
    ctx = CapabilityContext(
        identity=CapabilityIdentity(
            user_id="u-1", team_id="team-42", agent_instance_id="inst-7"
        ),
        config=config or PptBuilderConfig(),
        turn_options=EmptyModel(),
        services=RuntimeServices(workspace_fs=FakeWorkspace()),
    )
    (middleware,) = PptBuilderCapability().middleware(ctx)
    return cast(Any, middleware)


@pytest.fixture
def built_on(monkeypatch) -> list[Any]:
    """The inventory each set of build tools is made from."""
    seen: list[Any] = []
    real = capability_mod.build_builder_tools

    def _record(ctx, load, inventory, *args, **kwargs):
        seen.append(inventory)
        return real(ctx, load, inventory, *args, **kwargs)

    monkeypatch.setattr(capability_mod, "build_builder_tools", _record)
    return seen


class _Request:
    system_prompt = ""

    def __init__(self, tools: list) -> None:
        self.messages: list = []
        self.tools = tools

    def override(self, **_update: Any) -> "_Request":
        return self


async def _first_model_call(middleware: Any) -> None:
    async def _handler(request):
        return request

    await middleware.awrap_model_call(_Request(middleware.tools), _handler)


@pytest.mark.asyncio
async def test_a_first_replacement_pending_or_failed_leaves_agents_on_the_fred_template(
    analysis_db, built_on
):
    await _pending_replacement(TEMPLATE)
    builtin = builtin_template()[1]
    middleware = _middleware()
    await _first_model_call(middleware)
    assert built_on[-1] is builtin

    await age_row(analysis_db, PLATFORM_NEXT_ID, status="failed")
    analysis_job.forget_platform_default()
    await _first_model_call(_middleware())
    assert built_on[-1] is builtin
    verdict = await PptBuilderCapability().readiness(
        PptBuilderConfig(), CapabilityIdentity(user_id="u", agent_instance_id="i")
    )
    assert verdict.state == "ready"


@pytest.mark.asyncio
async def test_agents_keep_the_previous_platform_template_until_a_replacement_succeeds(
    analysis_db, built_on
):
    await _uploaded()
    await _first_model_call(_middleware())
    previous = built_on[-1]
    await _pending_replacement()
    analysis_job.forget_platform_default()
    await _first_model_call(_middleware())
    assert built_on[-1].model_dump() == previous.model_dump()

    await age_row(analysis_db, PLATFORM_NEXT_ID, status="failed")
    analysis_job.forget_platform_default()
    await _first_model_call(_middleware())
    assert built_on[-1].model_dump() == previous.model_dump()

    await _uploaded(OTHER)  # this pod ran the job: it reads the new one at once
    await _first_model_call(_middleware())
    snapshot = analysis_job.platform_snapshot()[1]
    assert snapshot is not None and snapshot.sha == OTHER_SHA


@pytest.mark.asyncio
async def test_a_succeeded_platform_template_serves_agents_without_their_own(
    analysis_db, built_on
):
    await _uploaded()
    middleware = _middleware()
    await _first_model_call(middleware)
    platform = built_on[-1]
    assert platform is not builtin_template()[1]
    tools = {t.name: t for t in middleware.tools}
    assert BUILD_TOOL_NAME in tools

    # The next turn builds straight from the snapshot: no read.
    calls = 0
    real_get = analysis_job.SqlAnalysisStore.get

    async def _counting_get(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return await real_get(self, *args, **kwargs)

    analysis_job.SqlAnalysisStore.get = _counting_get  # type: ignore[method-assign]
    try:
        _middleware()
    finally:
        analysis_job.SqlAnalysisStore.get = real_get  # type: ignore[method-assign]
    assert calls == 0 and built_on[-1] is platform


@pytest.mark.asyncio
async def test_the_agent_template_wins_over_the_platform_default(analysis_db, built_on):
    await _uploaded()
    await _first_model_call(_middleware())
    platform = built_on[-1]
    own = await get_analysis_store().start(
        instance_id="inst-7",
        team_id="team-42",
        saved_by="u-1",
        template_sha256=SHA,
        labelling_key="rules",
        template=TEMPLATE,
    )
    await analysis_job.run_analysis(
        get_analysis_store(), "inst-7", own, TEMPLATE, None, "rules"
    )
    middleware = _middleware(PptBuilderConfig(template_sha256=SHA, use_vision=False))
    await _first_model_call(middleware)
    assert built_on[-1] is not platform


@pytest.mark.asyncio
async def test_an_expired_snapshot_serves_while_one_read_replaces_it(analysis_db):
    await _uploaded()
    await analysis_job.refresh_platform_default()
    known, value = platform_snapshot()
    assert known and value is not None and value.sha == SHA

    await get_analysis_store().delete(PLATFORM_ID)  # written by another pod
    assert platform_snapshot()[1] == value  # still fresh here
    analysis_job._platform = (time.monotonic() - 1, value)
    assert platform_snapshot()[1] == value  # expired: served, read started
    assert platform_snapshot()[1] == value  # one read in flight, not two
    await drain()
    assert platform_snapshot() == (True, None)


@pytest.mark.asyncio
async def test_a_write_drops_a_read_started_before_it(analysis_db):
    await _uploaded()
    analysis_job.forget_platform_default()
    read = analysis_job._start_platform_read()
    assert read is not None
    analysis_job.forget_platform_default()  # a write lands meanwhile
    await read
    assert platform_snapshot() == (False, None)


@pytest.mark.asyncio
async def test_a_stored_pattern_edit_never_reaches_the_default_template(built_on):
    overridden = PptBuilderConfig.model_validate(
        {
            "overrides": [
                {
                    "pattern_id": builtin_template()[1].patterns[0].id,
                    "included": False,
                }
            ]
        }
    )
    _middleware(overridden)
    assert built_on[-1] is builtin_template()[1]
