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

"""`_evaluate_quota` — the single quota implementation behind both the
pre-receive precheck endpoint (#2360, client-declared sizes) and the
post-receive upload enforcement (`_check_quota_before_upload`). These tests pin
the verdicts (allowed / team denial / personal denial, with the denial's
numbers), the `extra_team_ids` path used when the destination's tags don't
exist yet, and the fail-closed error paths inherited from #2150.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fred_core import KeycloakUser

from knowledge_flow_backend.application_context import ApplicationContext
from knowledge_flow_backend.features.ingestion.ingestion_controller import IngestionController


class _FakeTagStore:
    def __init__(self, tags: dict[str, SimpleNamespace] | None = None) -> None:
        self._tags = tags or {}

    async def get_tag_by_id(self, tag_id: str):
        return self._tags.get(tag_id)


class _FakeRebac:
    async def lookup_subjects(self, reference, relation, resource):
        return []


class _FakeTeamMetadataStore:
    """check_quota returns (allowed, current, max) like the real store."""

    quotas: dict[str, tuple[int, int | None]] = {}

    def __init__(self, engine) -> None:
        del engine

    async def check_quota(self, team_id, upload_size, default_limit=None):
        current, max_size = self.quotas.get(str(team_id), (0, None))
        if max_size is None:
            max_size = default_limit
        allowed = not max_size or current + upload_size <= max_size
        return allowed, current, max_size

    async def get_by_team_id(self, team_id):
        return SimpleNamespace(team_id=str(team_id)) if str(team_id) in self.quotas else None


class _FakeUserStore:
    def __init__(self, usage_by_uid: dict[str, int] | None = None, broken: bool = False) -> None:
        self._usage = usage_by_uid or {}
        self._broken = broken

    async def find_user_by_id(self, user_uuid):
        if self._broken:
            raise RuntimeError("store down")
        usage = self._usage.get(str(user_uuid))
        return SimpleNamespace(current_resources_storage_size=usage) if usage is not None else None


class _FakeConfig:
    def __init__(self, personal_limit: int | None = None, default_team_limit: int | None = None) -> None:
        self.app = SimpleNamespace(
            personal_max_resources_storage_size=personal_limit,
            default_team_max_resources_storage_size=default_team_limit,
        )


class _FakeAppContext:
    def __init__(self, config: _FakeConfig, tags: dict[str, SimpleNamespace] | None = None) -> None:
        self._config = config
        self._tag_store = _FakeTagStore(tags)
        self._rebac = _FakeRebac()

    def get_config(self):
        return self._config

    def get_tag_store(self):
        return self._tag_store

    def get_rebac_engine(self):
        return self._rebac

    def get_pg_async_engine(self):
        return object()


def _setup(monkeypatch, config: _FakeConfig, *, team_quotas: dict[str, tuple[int, int | None]] | None = None, user_store: _FakeUserStore | None = None, tags=None) -> None:
    fake = _FakeAppContext(config, tags)
    monkeypatch.setattr(ApplicationContext, "get_instance", classmethod(lambda cls: fake))
    _FakeTeamMetadataStore.quotas = team_quotas or {}
    monkeypatch.setattr(
        "knowledge_flow_backend.features.ingestion.ingestion_controller.TeamMetadataStore",
        _FakeTeamMetadataStore,
    )
    monkeypatch.setattr("fred_core.get_user_store", lambda: user_store or _FakeUserStore())


def _controller() -> IngestionController:
    return IngestionController.__new__(IngestionController)


def _user(uid: str) -> KeycloakUser:
    return KeycloakUser(uid=uid, username=uid, email=None, roles=[])


@pytest.mark.asyncio
async def test_empty_batch_is_always_allowed(monkeypatch):
    _setup(monkeypatch, _FakeConfig(personal_limit=1))
    verdict = await _controller()._evaluate_quota(0, [], _user(str(uuid4())))
    assert verdict.allowed is True
    assert verdict.scope is None


@pytest.mark.asyncio
async def test_team_denial_carries_the_owners_numbers(monkeypatch):
    # Team resolved via extra_team_ids — the corpus-root drop path, where the
    # destination's library tags don't exist yet at precheck time.
    _setup(monkeypatch, _FakeConfig(), team_quotas={"team-a": (90, 100)})
    verdict = await _controller()._evaluate_quota(20, [], _user(str(uuid4())), extra_team_ids={"team-a"})
    assert verdict.allowed is False
    assert (verdict.scope, verdict.owner_id, verdict.current, verdict.limit) == ("team", "team-a", 90, 100)


@pytest.mark.asyncio
async def test_team_within_quota_is_allowed(monkeypatch):
    _setup(monkeypatch, _FakeConfig(), team_quotas={"team-a": (90, 100)})
    verdict = await _controller()._evaluate_quota(10, [], _user(str(uuid4())), extra_team_ids={"team-a"})
    assert verdict.allowed is True


@pytest.mark.asyncio
async def test_tagless_batch_falls_back_to_personal_quota(monkeypatch):
    uid = str(uuid4())
    _setup(monkeypatch, _FakeConfig(personal_limit=100), user_store=_FakeUserStore({uid: 95}))
    verdict = await _controller()._evaluate_quota(10, [], _user(uid))
    assert verdict.allowed is False
    assert (verdict.scope, verdict.owner_id, verdict.current, verdict.limit) == ("personal", uid, 95, 100)


@pytest.mark.asyncio
async def test_personal_denial_via_owned_tag(monkeypatch):
    uid = str(uuid4())
    tags = {"tag-1": SimpleNamespace(id="tag-1", owner_id=f"personal-{uid}")}
    _setup(monkeypatch, _FakeConfig(personal_limit=100), user_store=_FakeUserStore({uid: 95}), tags=tags)
    verdict = await _controller()._evaluate_quota(10, ["tag-1"], _user(uid))
    assert verdict.allowed is False
    assert verdict.scope == "personal"


@pytest.mark.asyncio
async def test_fails_closed_when_the_user_store_is_down(monkeypatch):
    uid = str(uuid4())
    _setup(monkeypatch, _FakeConfig(personal_limit=100), user_store=_FakeUserStore(broken=True))
    with pytest.raises(HTTPException) as exc:
        await _controller()._evaluate_quota(10, [], _user(uid))
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_fails_closed_on_a_malformed_owner_id(monkeypatch):
    _setup(monkeypatch, _FakeConfig(personal_limit=100))
    with pytest.raises(HTTPException) as exc:
        await _controller()._evaluate_quota(10, [], _user("not-a-uuid"))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_enforcement_raises_400_with_the_historical_message(monkeypatch):
    # _check_quota_before_upload is now a thin wrapper over _evaluate_quota;
    # its externally observable contract (400 + message shape) must not drift.
    _setup(monkeypatch, _FakeConfig(), team_quotas={"team-a": (90, 100)})
    controller = _controller()

    async def _owners(tags, user):
        return {"team-a"}, set()

    monkeypatch.setattr(controller, "_resolve_tag_owners", _owners)

    class _F:
        size = 20

    with pytest.raises(HTTPException) as exc:
        await controller._check_quota_before_upload([_F()], ["tag-a"], _user(str(uuid4())))
    assert exc.value.status_code == 400
    assert exc.value.detail == "Storage quota exceeded for team 'team-a': limit is 100 bytes, current usage is 90 bytes, attempting to upload 20 bytes."
