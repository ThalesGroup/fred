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

"""
Copy an agent to other teams or the personal space, and duplicate it in place:
per-destination authorization, readiness preview, capabilities left out,
naming, partial failure and the audit event.
"""

from __future__ import annotations

from typing import Any
from types import SimpleNamespace

import control_plane_backend.product.agent_copy as agent_copy
import pytest
from control_plane_backend.config.models import ManagedAgentTuning
from fastapi import HTTPException
from fred_core.common import TeamId
from fred_core.security.rebac.rebac_engine import RebacReference
from fred_sdk.contracts.capability import CapabilityConfigCopyRequest
from fred_sdk.contracts.capability import CapabilityCatalogEntry
from fred_sdk.contracts.capability.manifest import AssetSlot
from fred_sdk.contracts.capability.preparation import PreparationSpec
from httpx import ASGITransport, AsyncClient
from test_capability_selection_1974 import (
    RAGS_SAMPLE_ECHO_TEMPLATE_ID,
    _FilterRebacForEnrollment,
    _setup,
)
from test_main import _PERSONAL_TEAM_ID, _make_record

# Offline: copies must not call a pod for capability readiness.
pytestmark = pytest.mark.usefixtures("pods_report_ready")

_SOURCE = "team-a"
_ALL = {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo", "probe_echo"}


def test_copy_uploads_keep_declared_slot_and_bytes() -> None:
    catalog = (
        CapabilityCatalogEntry(
            id="deck_copy",
            version="1",
            name="Deck",
            description="Deck",
            icon="slideshow",
            assets=[AssetSlot(key="template", accepted_types=[".pptx"])],
            preparation=PreparationSpec(asset_slots=("template",), rules_version="v1"),
        ),
    )
    uploads = agent_copy._copy_uploads(
        [
            (
                "deck_copy",
                {
                    "preparation_assets": [
                        {
                            "slot_key": "template",
                            "filename": "deck.pptx",
                            "content_base64": "cHB0eC1ieXRlcw==",
                        }
                    ]
                },
            )
        ],
        catalog,
    )
    assert uploads["deck_copy"][0].content == b"pptx-bytes"
    assert uploads["deck_copy"][0].slot_key == "template"


@pytest.mark.asyncio
async def test_copy_persists_preparation_with_new_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = CapabilityCatalogEntry(
        id="demo_echo",
        version="1",
        name="Demo",
        description="Demo",
        icon="hub",
        assets=[AssetSlot(key="source", accepted_types=[".txt"])],
        preparation=PreparationSpec(asset_slots=("source",), rules_version="v1"),
    )
    original = {
        "slot_key": "source",
        "filename": "source.txt",
        "content_base64": "c291cmNl",
    }

    class MemoryContent:
        def __init__(self) -> None:
            self.objects: dict[str, bytes] = {}

        def put_object(self, key, stream, *, content_type):
            self.objects[key] = stream.read()

        def delete_object(self, key):
            self.objects.pop(key, None)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        def begin(self):
            return self

    session = Session()
    seen: list[tuple[str, object]] = []

    class Store:
        async def list_by_team(self, _team):
            return []

        async def create(self, record, *, session):
            seen.append(("create", session))
            return record

    async def copied(*, request, **_):
        return {
            "schema_version": "1",
            "config": request.config.config,
            "preparation_assets": [original],
        }

    async def source_assets(*_args, **_kwargs):
        return {"demo_echo": [agent_copy.PreparationCopyAsset.model_validate(original)]}

    async def persisted(session_arg, **kwargs):
        seen.append(("persist", session_arg))
        assert len(kwargs["staged"]) == 1

    async def unchanged(_deps, created, **_):
        return created

    async def no_routing(*_args, **_kwargs):
        return {}

    async def no_restrictions(*_args, **_kwargs):
        return None

    monkeypatch.setattr(agent_copy, "usable_capability_ids", no_restrictions)
    monkeypatch.setattr(agent_copy, "_source_preparation_assets", source_assets)
    monkeypatch.setattr(agent_copy, "_copy_capability_config_via_pod", copied)
    monkeypatch.setattr(agent_copy, "persist_agent_preparations", persisted)
    monkeypatch.setattr(agent_copy.product_service, "settle_capability_save", unchanged)
    monkeypatch.setattr(
        agent_copy.product_service, "_capability_save_routing_params", no_routing
    )
    monkeypatch.setattr(agent_copy, "emit_agent_created_kpi", lambda *_a, **_k: None)
    monkeypatch.setattr(agent_copy, "emit_audit_log", lambda *_a, **_k: None)
    content = MemoryContent()
    deps = SimpleNamespace(
        configuration=SimpleNamespace(
            platform=SimpleNamespace(
                runtime_catalog_sources=[
                    SimpleNamespace(
                        runtime_id="runtime-a", enabled=True, preparation_enabled=True
                    )
                ]
            )
        ),
        team_dependencies=SimpleNamespace(rebac=object()),
        get_agent_instance_store=lambda: Store(),
        get_content_store=lambda: content,
        get_sql_session_factory=lambda: lambda: session,
    )
    source = agent_copy.CopySource(
        base_url="http://runtime/pod/v1",
        capability_ids=["demo_echo"],
        names={"demo_echo": "Demo"},
        available=(entry,),
    )
    result = await agent_copy.copy_agent_instance_to_team(
        user=SimpleNamespace(uid="admin"),
        record=_source_record(),
        source=source,
        target_team_id=TeamId("team-b"),
        display_name="Copy",
        deps=deps,
        authorization="Bearer test",
    )
    assert result.agent is not None
    assert seen == [("create", session), ("persist", session)]
    assert list(content.objects.values()) == [b"source"]


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


class _CopyRebac(_FilterRebacForEnrollment):
    """Usable capabilities per team, plus the teams the caller edits."""

    def __init__(self, usable_by_team, edited_teams: list[str]) -> None:
        super().__init__(usable_by_team)
        self._edited_teams = edited_teams

    def _assert_team_check(self, subject, contextual_relations) -> str:
        # The personal space adds its own contextual edge; the subject is what matters.
        return subject.id

    async def lookup_user_resources(self, user, permission, *, consistency_token=None):
        return [RebacReference(type=_team_type(), id=t) for t in self._edited_teams]


def _team_type():
    from fred_core.security.rebac.rebac_engine import Resource

    return Resource.TEAM


async def _require_team_access(user, team_id, deps=None, required_permissions=None):
    """Canonical personal id; team-c is not edited by the caller."""

    if str(team_id) == "team-c":
        raise HTTPException(status_code=403, detail="Not an editor of team-c.")
    if str(team_id) == "personal":
        return _PERSONAL_TEAM_ID
    return TeamId(team_id)


def _source_record(**overrides: Any):
    record = _make_record(agent_instance_id="agent-1", team_id=_SOURCE, **overrides)
    record.tuning = ManagedAgentTuning(
        role="Echo",
        description="Echo agent",
        values={"prompts.system": "Answer politely."},
        selected_capability_ids=["demo_echo", "probe_echo"],
        capability_config={
            "demo_echo": {"schema_version": "0.1.0", "config": {"uppercase": True}},
            "probe_echo": {"schema_version": "1.0.0", "config": {}},
        },
    )
    return record


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    usable_by_team: dict[str, set[str]],
    *,
    records=None,
    edited_teams: list[str] | None = None,
    rejected: frozenset[str] = frozenset(),
):
    fake = _CopyRebac(usable_by_team, edited_teams or [])
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda self: fake,
    )
    app, store = _setup(monkeypatch, records=records or [_source_record()])
    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access", _require_team_access
    )
    pod_calls: list[tuple[str, CapabilityConfigCopyRequest]] = []
    routing_seen: list[dict[str, str] | None] = []

    async def _fake_copy(
        *, base_url, capability_id, request, authorization, routing_params=None
    ):
        pod_calls.append((capability_id, request))
        routing_seen.append(routing_params)
        if request.target_team_id == "team-crash":
            raise RuntimeError("database unavailable")
        if capability_id in rejected:
            return None
        return {
            "schema_version": request.config.schema_version,
            "config": {**request.config.config, "copied_to": request.target_team_id},
            "notices": [f"redo {capability_id}"]
            if capability_id == "demo_echo"
            else [],
        }

    monkeypatch.setattr(agent_copy, "_copy_capability_config_via_pod", _fake_copy)
    app.state.copy_routing_seen = routing_seen
    audits: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        agent_copy,
        "emit_audit_log",
        lambda name, level="info", /, **fields: audits.append((name, fields)),
    )
    return app, store, pod_calls, audits


async def _post_copy(app, body: dict[str, Any]):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            f"/control-plane/v1/teams/{_SOURCE}/agent-instances/agent-1/copy",
            headers={"Authorization": "Bearer user-token"},
            json=body,
        )


@pytest.mark.asyncio
async def test_copy_to_another_team_keeps_usable_capabilities_and_records_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, pod_calls, audits = _wire(
        monkeypatch,
        {_SOURCE: _ALL, "team-b": {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo"}},
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert resp.status_code == 200
    [result] = resp.json()["results"]
    assert result["team_id"] == "team-b"
    assert result["dropped_capabilities"] == [
        {"id": "probe_echo", "name": "capability.probe_echo.name"}
    ]
    assert result["notices"] == [
        {
            "capability": {"id": "demo_echo", "name": "capability.demo_echo.name"},
            "message": "redo demo_echo",
        }
    ]
    copy = next(r for r in store._records if r.team_id == "team-b")
    assert result["agent"]["agent_instance_id"] == copy.agent_instance_id
    assert copy.display_name == "Echo Team Agent"
    assert copy.tuning.values == {"prompts.system": "Answer politely."}
    assert copy.tuning.selected_capability_ids == ["demo_echo"]
    assert copy.tuning.capability_config == {
        "demo_echo": {
            "schema_version": "0.1.0",
            "config": {"uppercase": True, "copied_to": "team-b"},
        }
    }
    [(capability_id, request)] = pod_calls
    assert capability_id == "demo_echo"
    assert (request.source_team_id, request.source_agent_instance_id) == (
        _SOURCE,
        "agent-1",
    )
    assert (request.target_team_id, request.target_agent_instance_id) == (
        "team-b",
        copy.agent_instance_id,
    )
    assert audits == [
        (
            "agent.copied",
            {
                "source_agent_instance_id": "agent-1",
                "source_team_id": _SOURCE,
                "target_team_id": "team-b",
                "agent_instance_id": copy.agent_instance_id,
                "user_id": "admin",
                "dropped_capabilities": "probe_echo",
            },
        )
    ]


@pytest.mark.asyncio
async def test_capability_rejected_by_the_destination_is_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": _ALL}, rejected=frozenset({"demo_echo"})
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert [c["id"] for c in resp.json()["results"][0]["dropped_capabilities"]] == [
        "demo_echo"
    ]
    copy = next(r for r in store._records if r.team_id == "team-b")
    assert copy.tuning.selected_capability_ids == ["probe_echo"]


@pytest.mark.asyncio
async def test_name_conflict_takes_the_first_free_numbered_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taken = [
        _make_record(
            agent_instance_id="b-1", team_id="team-b", display_name="Echo Team Agent"
        ),
        _make_record(
            agent_instance_id="b-2",
            team_id="team-b",
            display_name="Echo Team Agent (copie 1)",
        ),
    ]
    app, store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": _ALL}, records=[_source_record(), *taken]
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"], "locale": "fr"})

    assert (
        resp.json()["results"][0]["agent"]["display_name"]
        == "Echo Team Agent (copie 2)"
    )


@pytest.mark.asyncio
async def test_copy_name_word_follows_the_locale_english_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taken = _make_record(
        agent_instance_id="b-1", team_id="team-b", display_name="Echo Team Agent"
    )
    app, _store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": _ALL}, records=[_source_record(), taken]
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"], "locale": "en"})
    assert (
        resp.json()["results"][0]["agent"]["display_name"] == "Echo Team Agent (copy 1)"
    )
    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})
    assert (
        resp.json()["results"][0]["agent"]["display_name"] == "Echo Team Agent (copy 2)"
    )


@pytest.mark.asyncio
async def test_copy_refuses_a_locale_outside_the_fixed_words(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _store, _calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL, "team-b": _ALL})

    resp = await _post_copy(app, {"target_team_ids": ["team-b"], "locale": "de"})

    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_failed_destination_does_not_stop_the_others(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL, "team-b": _ALL})

    resp = await _post_copy(app, {"target_team_ids": ["team-b", "team-c"]})

    by_team = {r["team_id"]: r for r in resp.json()["results"]}
    assert by_team["team-b"]["agent"]
    assert by_team["team-c"]["error"] == "Not an editor of team-c."
    assert not [r for r in store._records if r.team_id == "team-c"]


@pytest.mark.asyncio
async def test_template_not_enabled_refuses_that_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, pod_calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": {"demo_echo", "probe_echo"}}
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert "template is not enabled" in resp.json()["results"][0]["error"]
    assert pod_calls == []
    assert not [r for r in store._records if r.team_id == "team-b"]


@pytest.mark.asyncio
async def test_personal_space_is_stored_under_its_canonical_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, str(_PERSONAL_TEAM_ID): _ALL}
    )

    resp = await _post_copy(app, {"target_team_ids": ["personal"]})

    assert resp.json()["results"][0]["team_id"] == str(_PERSONAL_TEAM_ID)
    assert [r.team_id for r in store._records if r.agent_instance_id != "agent-1"] == [
        _PERSONAL_TEAM_ID
    ]


@pytest.mark.asyncio
async def test_duplicate_keeps_the_chosen_name_in_the_source_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, pod_calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL})

    resp = await _post_copy(
        app, {"target_team_ids": [_SOURCE], "display_name": "Echo (copy)"}
    )

    agent = resp.json()["results"][0]["agent"]
    assert (agent["team_id"], agent["display_name"]) == (_SOURCE, "Echo (copy)")
    assert {request.target_team_id for _cap, request in pod_calls} == {_SOURCE}


@pytest.mark.asyncio
async def test_name_conflict_ignores_case_and_spaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    taken = _make_record(
        agent_instance_id="b-1", team_id="team-b", display_name=" echo team AGENT "
    )
    app, _store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": _ALL}, records=[_source_record(), taken]
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert (
        resp.json()["results"][0]["agent"]["display_name"] == "Echo Team Agent (copy 1)"
    )


@pytest.mark.asyncio
async def test_duplicate_under_a_taken_name_is_refused_before_the_pod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, pod_calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL})

    resp = await _post_copy(
        app, {"target_team_ids": [_SOURCE], "display_name": "  echo team agent "}
    )

    [result] = resp.json()["results"]
    assert result["error_code"] == "agent_name_conflict"
    assert "agent" not in result
    assert pod_calls == []
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_copy_losing_a_name_race_takes_the_next_free_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL, "team-b": _ALL})
    create = store.create
    raced = False

    async def _create_after_a_concurrent_copy(record):
        nonlocal raced
        if record.team_id == "team-b" and not raced:
            raced = True
            await create(
                _make_record(
                    agent_instance_id="b-race",
                    team_id="team-b",
                    display_name=record.display_name,
                )
            )
            raise agent_copy.AgentNameAlreadyExistsError(
                TeamId("team-b"), record.display_name
            )
        return await create(record)

    monkeypatch.setattr(store, "create", _create_after_a_concurrent_copy)

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert (
        resp.json()["results"][0]["agent"]["display_name"] == "Echo Team Agent (copy 1)"
    )


@pytest.mark.asyncio
async def test_chosen_name_is_refused_for_another_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL, "team-b": _ALL})

    resp = await _post_copy(
        app, {"target_team_ids": ["team-b"], "display_name": "Other"}
    )

    assert resp.status_code == 422
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_copy_targets_report_template_and_missing_capabilities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _store, _calls, _audits = _wire(
        monkeypatch,
        {
            _SOURCE: _ALL,
            str(_PERSONAL_TEAM_ID): _ALL,
            "team-b": {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo"},
            "team-c": {"demo_echo", "probe_echo"},
        },
        edited_teams=[_SOURCE, "team-b", "team-c"],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get(
            f"/control-plane/v1/teams/{_SOURCE}/agent-instances/agent-1/copy-targets"
        )

    assert resp.status_code == 200
    targets = {t["team_id"]: t for t in resp.json()["targets"]}
    assert list(targets) == [str(_PERSONAL_TEAM_ID), _SOURCE, "team-b", "team-c"]
    assert targets["team-b"] == {
        "team_id": "team-b",
        "template_enabled": True,
        "missing_capabilities": [
            {"id": "probe_echo", "name": "capability.probe_echo.name"}
        ],
    }
    assert targets["team-c"]["template_enabled"] is False
    assert targets[_SOURCE]["missing_capabilities"] == []


@pytest.mark.asyncio
async def test_copy_of_an_agent_outside_the_source_team_is_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, _store, _calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL})

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/team-b/agent-instances/agent-1/copy",
            json={"target_team_ids": ["team-b"]},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_non_editor_of_the_source_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(
        monkeypatch,
        {_SOURCE: _ALL},
        records=[_make_record(agent_instance_id="agent-1", team_id="team-c")],
    )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/control-plane/v1/teams/team-c/agent-instances/agent-1/copy",
            json={"target_team_ids": [_SOURCE]},
        )

    assert resp.status_code == 403
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_unexpected_failure_stays_on_its_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, _calls, _audits = _wire(
        monkeypatch, {_SOURCE: _ALL, "team-b": _ALL, "team-crash": _ALL}
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-crash", "team-b"]})

    assert resp.status_code == 200
    by_team = {r["team_id"]: r for r in resp.json()["results"]}
    assert by_team["team-b"]["agent"]
    assert "Unexpected error" in by_team["team-crash"]["error"]


@pytest.mark.asyncio
async def test_internal_template_is_not_copied_by_a_non_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app, store, pod_calls, _audits = _wire(monkeypatch, {_SOURCE: _ALL, "team-b": _ALL})
    visibility: list[bool] = []

    async def _public_templates_only(_base_url: str, include_non_public: bool = False):
        visibility.append(include_non_public)
        return []  # the agent's template is internal: hidden without admin rights

    monkeypatch.setattr(
        "control_plane_backend.product.service._fetch_runtime_templates",
        _public_templates_only,
    )

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert resp.status_code == 404
    assert visibility == [False]
    assert pod_calls == []
    assert len(store._records) == 1


@pytest.mark.asyncio
async def test_unsaved_selection_copies_the_template_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    record = _source_record()
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": None, "capability_config": {}}
    )
    fake = _CopyRebac({_SOURCE: _ALL, "team-b": _ALL}, [])
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda self: fake,
    )
    app, store = _setup(
        monkeypatch, records=[record], default_capability_ids=["demo_echo"]
    )
    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access", _require_team_access
    )

    async def _fake_copy(*, base_url, capability_id, request, authorization, **_):
        return {"schema_version": "0.1.0", "config": {}}

    monkeypatch.setattr(agent_copy, "_copy_capability_config_via_pod", _fake_copy)

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert resp.json()["results"][0]["agent"]["selected_capability_ids"] == [
        "demo_echo"
    ]


@pytest.mark.asyncio
async def test_graph_agent_saved_with_an_empty_selection_copies_its_included_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Older saves of a template without free selection stored `[]`; the runtime
    # still runs the included defaults, so the copy must carry them.
    record = _source_record()
    record.tuning = record.tuning.model_copy(
        update={"selected_capability_ids": [], "capability_config": {}}
    )
    fake = _CopyRebac({_SOURCE: _ALL, "team-b": _ALL}, [])
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext.get_rebac_engine",
        lambda self: fake,
    )
    app, store = _setup(
        monkeypatch,
        records=[record],
        default_capability_ids=["demo_echo"],
        supports_capabilities=False,
    )
    monkeypatch.setattr(
        "control_plane_backend.product.api.require_team_access", _require_team_access
    )
    copied: list[str] = []

    async def _fake_copy(*, base_url, capability_id, request, authorization, **_):
        copied.append(capability_id)
        return {"schema_version": "0.1.0", "config": {}}

    monkeypatch.setattr(agent_copy, "_copy_capability_config_via_pod", _fake_copy)

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert resp.json()["results"][0]["agent"]["selected_capability_ids"] == [
        "demo_echo"
    ]
    assert copied == ["demo_echo"]


@pytest.mark.asyncio
async def test_copy_is_pending_while_its_capability_prepares_in_the_destination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from control_plane_backend.agent_instances.suspension import ReadinessVerdict
    from control_plane_backend.product import service

    app, store, _, _ = _wire(
        monkeypatch,
        {_SOURCE: _ALL, "team-b": {RAGS_SAMPLE_ECHO_TEMPLATE_ID, "demo_echo"}},
    )
    seen: list[str | None] = []

    async def _pending(*, authorization, **_: Any) -> ReadinessVerdict:
        seen.append(authorization)
        return ReadinessVerdict(ready=False, capability_ids=("demo_echo",))

    monkeypatch.setattr(service, "_fetch_capability_readiness", _pending)

    resp = await _post_copy(app, {"target_team_ids": ["team-b"]})

    assert resp.status_code == 200
    [result] = resp.json()["results"]
    assert result["agent"]["suspension_reason"] == "capability_pending"
    copy = next(r for r in store._records if r.team_id == "team-b")
    assert copy.suspension_reason == "capability_pending"
    assert seen == ["Bearer user-token"]
    # The destination's routing travels with the copy, as on a save.
    assert app.state.copy_routing_seen == [{"template_agent_id": copy.source_agent_id}]
