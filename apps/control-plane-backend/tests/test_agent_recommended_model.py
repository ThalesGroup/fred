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

"""An agent instance's recommended chat model: stored in tuning, validated
on create and update against the team's usable, enabled models served by the
instance's pod. Absent on update leaves it alone; null follows the team."""

from __future__ import annotations

import pytest
from control_plane_backend.routing_policy import service as routing_policy_service
from httpx import ASGITransport, AsyncClient
from test_capability_selection_1974 import _fake_pod_validate, _setup, _wire_rebac
from test_main import _FakeRoutingPolicyStore, _make_record

_USAGE = "Test usage statement covering purpose, users, data, and error impact."
_CREATE_URL = "/control-plane/v1/teams/personal/agent-instances"
_UPDATE_URL = "/control-plane/v1/teams/personal/agent-instances/instance-1"


@pytest.fixture(autouse=True)
def _use_test_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONFIG_FILE", "./config/configuration_test.yaml")


@pytest.fixture(autouse=True)
def _models(monkeypatch: pytest.MonkeyPatch) -> dict[str, set[str]]:
    """Pod serves chat.a (model__a), chat.b (model__b) and chat.c (model__c);
    the team cannot use model__c and disabled model__b."""

    state = {"usable": {"model__a", "model__b"}}

    async def _profiles(deps):
        return {"chat.a": "model__a", "chat.b": "model__b", "chat.c": "model__c"}

    async def _universal(deps, *, source_runtime_ids=None):
        assert source_runtime_ids == {"runtime-a"}
        return frozenset({"chat.a", "chat.b", "chat.c"})

    async def _can_use(rebac, team_id, *, capability_id):
        return capability_id in state["usable"]

    monkeypatch.setattr(
        routing_policy_service, "_profile_to_capability_id_map", _profiles
    )
    monkeypatch.setattr(
        routing_policy_service,
        "universally_available_chat_model_profile_ids",
        _universal,
    )
    monkeypatch.setattr(routing_policy_service, "can_team_use_capability", _can_use)
    policy_store = _FakeRoutingPolicyStore(
        {"personal": {"disabled_model_ids": ["model__b"]}}
    )
    monkeypatch.setattr(
        "control_plane_backend.app.context.ApplicationContext."
        "get_team_routing_policy_store",
        lambda _self: policy_store,
    )
    return state


def _app(monkeypatch: pytest.MonkeyPatch, records=None):
    _wire_rebac(monkeypatch, None)
    app, store = _setup(monkeypatch, records=records)
    _fake_pod_validate(monkeypatch)
    return app, store


async def _create(app, recommended: str | None):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            _CREATE_URL,
            json={
                "usage_statement": _USAGE,
                "template_id": "runtime-a:rags.sample.echo",
                "display_name": "Echo",
                "recommended_chat_profile_id": recommended,
            },
        )


async def _patch(app, body: dict):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.patch(_UPDATE_URL, json=body)


def _recommending(profile_id: str | None):
    record = _make_record()
    record.tuning = record.tuning.model_copy(
        update={"recommended_chat_profile_id": profile_id}
    )
    return record


@pytest.mark.asyncio
async def test_create_stores_a_valid_recommendation(monkeypatch) -> None:
    app, store = _app(monkeypatch)
    resp = await _create(app, "chat.a")
    assert resp.status_code == 201
    assert resp.json()["recommended_chat_profile_id"] == "chat.a"
    assert store._records[0].tuning.recommended_chat_profile_id == "chat.a"


@pytest.mark.asyncio
async def test_create_without_a_recommendation_follows_the_team(monkeypatch) -> None:
    app, store = _app(monkeypatch)
    resp = await _create(app, None)
    assert resp.status_code == 201
    assert store._records[0].tuning.recommended_chat_profile_id is None


@pytest.mark.parametrize(
    "profile_id",
    ["chat.b", "chat.c", "chat.ghost"],
    ids=["disabled", "revoked", "unknown"],
)
@pytest.mark.asyncio
async def test_create_rejects_a_recommendation_the_team_cannot_pick(
    monkeypatch, profile_id: str
) -> None:
    app, store = _app(monkeypatch)
    resp = await _create(app, profile_id)
    assert resp.status_code == 422
    assert store._records == []


@pytest.mark.asyncio
async def test_update_rejects_a_team_disabled_model_and_keeps_the_value(
    monkeypatch,
) -> None:
    app, store = _app(monkeypatch, records=[_recommending("chat.a")])
    resp = await _patch(app, {"recommended_chat_profile_id": "chat.b"})
    assert resp.status_code == 422
    assert store._records[0].tuning.recommended_chat_profile_id == "chat.a"


@pytest.mark.asyncio
async def test_update_omitting_the_field_leaves_it_unchanged(monkeypatch) -> None:
    app, store = _app(monkeypatch, records=[_recommending("chat.a")])
    resp = await _patch(app, {"display_name": "Renamed"})
    assert resp.status_code == 200
    assert store._records[0].tuning.recommended_chat_profile_id == "chat.a"


@pytest.mark.asyncio
async def test_update_with_null_follows_the_team_again(monkeypatch) -> None:
    app, store = _app(monkeypatch, records=[_recommending("chat.a")])
    resp = await _patch(app, {"recommended_chat_profile_id": None})
    assert resp.status_code == 200
    assert store._records[0].tuning.recommended_chat_profile_id is None


def test_legacy_tuning_keys_are_read_and_dropped() -> None:
    """A stored row from before this change still loads; its per-agent
    reasoning keys are ignored and gone on the next save."""

    from control_plane_backend.config.models import ManagedAgentTuning

    tuning = ManagedAgentTuning.model_validate_json(
        '{"role": "r", "description": "d", "reasoning_enabled": true,'
        ' "reasoning_default_on": true}'
    )
    assert tuning.recommended_chat_profile_id is None
    assert "reasoning_enabled" not in tuning.model_dump_json()
