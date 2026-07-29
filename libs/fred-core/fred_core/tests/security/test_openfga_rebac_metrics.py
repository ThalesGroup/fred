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
Offline unit tests for OpenFgaRebacEngine's rebac.call_latency_ms /
rebac.call_total instrumentation (TURN-01 evidence gap: no metric/counter
existed for OpenFGA calls at all).

The real openfga_sdk client is never invoked — `get_client()` is monkeypatched
to a fake object so these stay offline unit tests, per CLAUDE.md (live OpenFGA
is exercised only by the separate `integration/test_rebac.py` suite).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import (
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.security.structure import OpenFgaRebacConfig


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []
        self.counted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)

    def count(self, name, inc=1, *, dims=None, labels=None, actor) -> None:
        self.counted.append({"name": name, "dims": dims})


class _FakeOpenFgaClient:
    """Duck-typed stand-in for openfga_sdk's OpenFgaClient — no network calls."""

    def __init__(self) -> None:
        self.read_tuples: list[Any] = []
        self.read_calls: list[Any] = []

    async def check(self, body, options) -> SimpleNamespace:
        return SimpleNamespace(allowed=True)

    async def list_objects(self, body, options) -> SimpleNamespace:
        return SimpleNamespace(objects=[])

    async def list_users(self, body, options) -> SimpleNamespace:
        return SimpleNamespace(users=[])

    async def write(self, body, options) -> None:
        return None

    async def read(self, body, options) -> SimpleNamespace:
        self.read_calls.append(body)
        return SimpleNamespace(tuples=self.read_tuples, continuation_token="")  # nosec B106 — not a secret, an OpenFGA pagination token


def _make_engine(kpi_writer=None) -> tuple[OpenFgaRebacEngine, _FakeOpenFgaClient]:
    config = OpenFgaRebacConfig(
        api_url="http://fake-openfga:8080"  # pyright: ignore[reportArgumentType]
    )
    engine = OpenFgaRebacEngine(config, token="test-token", kpi_writer=kpi_writer)  # nosec B106 — fake test credential, no real OpenFGA is contacted
    fake_client = _FakeOpenFgaClient()
    engine._cached_client = fake_client  # pyright: ignore[reportAttributeAccessIssue]
    return engine, fake_client


_SUBJECT = RebacReference(type=Resource.USER, id="alice")
_TEAM = RebacReference(type=Resource.TEAM, id="fredlab")


@pytest.mark.asyncio
async def test_has_permission_emits_check_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)

    allowed = await engine.has_permission(_SUBJECT, TeamPermission.CAN_READ, _TEAM)

    assert allowed is True
    assert writer.emitted[0]["name"] == "rebac.call_latency_ms"
    assert writer.emitted[0]["dims"]["rebac_operation"] == "check"
    assert writer.counted[0]["name"] == "rebac.call_total"
    assert writer.counted[0]["dims"] == {"rebac_operation": "check", "status": "ok"}


@pytest.mark.asyncio
async def test_lookup_resources_emits_list_objects_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)

    await engine.lookup_resources(_SUBJECT, TeamPermission.CAN_READ, Resource.TEAM)

    assert writer.emitted[0]["dims"]["rebac_operation"] == "list_objects"


@pytest.mark.asyncio
async def test_lookup_subjects_emits_list_users_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)

    await engine.lookup_subjects(_TEAM, RelationType.EDITOR, Resource.USER)

    assert writer.emitted[0]["dims"]["rebac_operation"] == "list_users"


@pytest.mark.asyncio
async def test_persist_relation_emits_write_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)
    relation = Relation(subject=_SUBJECT, relation=RelationType.EDITOR, resource=_TEAM)

    await engine._persist_relation(relation)

    assert writer.emitted[0]["dims"]["rebac_operation"] == "write"


@pytest.mark.asyncio
async def test_has_direct_relation_emits_read_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)

    await engine.has_direct_relation(_SUBJECT, RelationType.EDITOR, _TEAM)

    assert writer.emitted[0]["dims"]["rebac_operation"] == "read"


@pytest.mark.asyncio
async def test_list_relations_emits_read_operation() -> None:
    writer = _RecordingKPIWriter()
    engine, _ = _make_engine(writer)

    await engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.TEAM_ADMIN,
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
    )

    assert writer.emitted[0]["dims"]["rebac_operation"] == "read"


@pytest.mark.asyncio
async def test_list_relations_parses_tuples_into_relations() -> None:
    """#2065: `list_relations` backs the bulk organization/public
    existence-check reads (`_teams_with_relation`) — must parse raw OpenFGA
    tuples into `Relation`s."""
    engine, fake_client = _make_engine()
    fake_client.read_tuples = [
        SimpleNamespace(
            key=SimpleNamespace(
                user="organization:fred", relation="organization", object="team:fredlab"
            )
        ),
    ]

    relations = await engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.ORGANIZATION,
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
    )

    assert relations == [
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, "fred"),
            relation=RelationType.ORGANIZATION,
            resource=RebacReference(Resource.TEAM, "fredlab"),
        )
    ]


@pytest.mark.asyncio
async def test_list_relations_sends_exact_user_for_organization_subject() -> None:
    """#2065 regression guard: confirmed live against OpenFGA v1.12.1 and
    v1.15.1, a Read whose `object` is type-only (no id) and whose `user`
    is empty is rejected (HTTP 400, "the 'tuple_key' field was provided
    but the object type field is required and both the object id and
    user cannot be empty"). The `ReadRequestTupleKey` handed to the SDK
    client must always carry the exact `user` — never omit it, never
    send a bare type."""
    engine, fake_client = _make_engine()

    await engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.ORGANIZATION,
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
    )

    assert len(fake_client.read_calls) == 1
    body = fake_client.read_calls[0]
    assert body.user == "organization:fred"
    assert body.relation == "organization"
    assert body.object == "team:"


@pytest.mark.asyncio
async def test_list_relations_sends_exact_user_for_public_subject() -> None:
    """Same OpenFGA v1.12.1/v1.15.1 constraint, for the `public` existence-check read
    (`revoke_team_public_relations`/`ensure_team_public_relations`): the
    wildcard subject `user:*` is itself the exact tuple user to filter on —
    it must reach `body.user` unchanged, never be dropped."""
    engine, fake_client = _make_engine()

    await engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.PUBLIC,
        subject=RebacReference(Resource.USER, "*"),
    )

    assert len(fake_client.read_calls) == 1
    body = fake_client.read_calls[0]
    assert body.user == "user:*"
    assert body.relation == "public"
    assert body.object == "team:"


class _PaginatingFakeOpenFgaClient(_FakeOpenFgaClient):
    """Serves `pages` one per call, chaining via `continuation_token`."""

    def __init__(self, pages: list[list[Any]]) -> None:
        super().__init__()
        self._pages = pages

    async def read(self, body, options) -> SimpleNamespace:
        index = int(options.get("continuation_token") or 0)
        next_index = index + 1
        token = str(next_index) if next_index < len(self._pages) else ""
        return SimpleNamespace(tuples=self._pages[index], continuation_token=token)  # nosec B106 — pagination token, not a secret


@pytest.mark.asyncio
async def test_list_relations_paginates_via_continuation_token() -> None:
    engine, _ = _make_engine()
    page_1 = [
        SimpleNamespace(
            key=SimpleNamespace(
                user="user:alice", relation="team_admin", object="team:a"
            )
        )
    ]
    page_2 = [
        SimpleNamespace(
            key=SimpleNamespace(user="user:bob", relation="team_admin", object="team:b")
        )
    ]
    engine._cached_client = _PaginatingFakeOpenFgaClient(  # pyright: ignore[reportAttributeAccessIssue]
        [page_1, page_2]
    )

    relations = await engine.list_relations(
        resource_type=Resource.TEAM,
        relation=RelationType.TEAM_ADMIN,
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
    )

    assert {(r.subject.id, r.resource.id) for r in relations} == {
        ("alice", "a"),
        ("bob", "b"),
    }


@pytest.mark.asyncio
async def test_openfga_calls_are_silent_without_a_kpi_writer() -> None:
    # kpi_writer=None is the default — must not raise (matches every other
    # KPI-instrumented call site, e.g. persist_* metrics, phase_timer).
    engine, _ = _make_engine(kpi_writer=None)

    allowed = await engine.has_permission(_SUBJECT, TeamPermission.CAN_READ, _TEAM)

    assert allowed is True
