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

"""`RebacEngine.has_permissions` — one round-trip for several permissions on
the same subject/resource pair (control-plane's `TeamWithPermissions.
permissions` projection: 14 `TeamPermission`s in one call instead of 14).

`OpenFgaRebacEngine.has_permissions` is backed by the native OpenFGA
`BatchCheck` HTTP endpoint (one call for up to `max_batch_size`, default 50 —
14 fits easily). The real `openfga_sdk` client is never invoked here — its
`batch_check` method is a fake, so these stay offline unit tests.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from fred_core.kpi.noop_kpi_writer import NoOpKPIWriter
from fred_core.security.models import Resource
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import (
    RebacPermission,
    RebacReference,
    Relation,
    RelationType,
    TeamPermission,
)
from fred_core.security.structure import OpenFgaRebacConfig

_SUBJECT = RebacReference(type=Resource.USER, id="alice")
_TEAM = RebacReference(type=Resource.TEAM, id="fredlab")
_ALL_TEAM_PERMISSIONS = list(TeamPermission)


class _RecordingKPIWriter(NoOpKPIWriter):
    def __init__(self) -> None:
        self.emitted: list[dict] = []
        self.counted: list[dict] = []

    def emit(self, **kwargs) -> None:
        self.emitted.append(kwargs)

    def count(self, name, inc=1, *, dims=None, labels=None, actor) -> None:
        self.counted.append({"name": name, "dims": dims})


class _SingleResult:
    def __init__(self, allowed: bool, correlation_id: str, error: Any = None) -> None:
        self.allowed = allowed
        self.correlation_id = correlation_id
        self.error = error


class _FakeBatchCheckClient:
    """Duck-typed stand-in for `OpenFgaClient` — only `batch_check` is used."""

    def __init__(self, results: list[_SingleResult] | None = None) -> None:
        self.calls: list[tuple[Any, Any]] = []
        self._results = results

    async def batch_check(self, body, options) -> SimpleNamespace:
        self.calls.append((body, options))
        if self._results is not None:
            return SimpleNamespace(result=self._results)
        # Default: allow everything, correlation_ids echoed back in order.
        return SimpleNamespace(
            result=[
                _SingleResult(allowed=True, correlation_id=item.correlation_id)
                for item in body.checks
            ]
        )


def _make_engine(client: _FakeBatchCheckClient, kpi_writer=None) -> OpenFgaRebacEngine:
    config = OpenFgaRebacConfig(
        api_url="http://fake-openfga:8080"  # pyright: ignore[reportArgumentType]
    )
    engine = OpenFgaRebacEngine(config, token="test-token", kpi_writer=kpi_writer)  # nosec B106 — fake test credential, no real OpenFGA is contacted
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


@pytest.mark.asyncio
async def test_empty_permissions_makes_no_client_call() -> None:
    """7: an empty sequence returns `[]` without touching the client."""
    client = _FakeBatchCheckClient()
    engine = _make_engine(client)

    allowed = await engine.has_permissions(_SUBJECT, [], _TEAM)

    assert allowed == []
    assert client.calls == []


@pytest.mark.asyncio
async def test_one_call_for_fourteen_permissions_with_exact_body() -> None:
    """2 + 3 + 4: one `batch_check` call, body has exactly 14 checks, each
    with the correct user/relation/object."""
    client = _FakeBatchCheckClient()
    engine = _make_engine(client)

    allowed = await engine.has_permissions(_SUBJECT, _ALL_TEAM_PERMISSIONS, _TEAM)

    assert len(client.calls) == 1
    assert allowed == [True] * len(_ALL_TEAM_PERMISSIONS)

    body, _options = client.calls[0]
    assert len(body.checks) == len(_ALL_TEAM_PERMISSIONS)
    for item, permission in zip(body.checks, _ALL_TEAM_PERMISSIONS):
        assert item.user == "user:alice"
        assert item.object == "team:fredlab"
        assert item.relation == permission.value


@pytest.mark.asyncio
async def test_result_order_survives_a_shuffled_server_response() -> None:
    """1: `OpenFgaClient.batch_check` folds results through a dict keyed by
    correlation_id (see `client.py::batch_check`'s `res.result.items()`) —
    nothing guarantees response order matches request order. Feed results
    back scrambled and assert the returned list still matches input order."""
    permissions = [
        TeamPermission.CAN_READ,
        TeamPermission.CAN_UPDATE_INFO,
        TeamPermission.CAN_UPDATE_RESOURCES,
    ]
    # Correlation ids are "0", "1", "2" (index-based) — return them out of
    # order, with only index 1 allowed.
    scrambled = [
        _SingleResult(allowed=False, correlation_id="2"),
        _SingleResult(allowed=True, correlation_id="1"),
        _SingleResult(allowed=False, correlation_id="0"),
    ]
    client = _FakeBatchCheckClient(results=scrambled)
    engine = _make_engine(client)

    allowed = await engine.has_permissions(_SUBJECT, permissions, _TEAM)

    assert allowed == [False, True, False]


@pytest.mark.asyncio
async def test_consistency_token_is_transmitted() -> None:
    """5"""
    client = _FakeBatchCheckClient()
    engine = _make_engine(client)

    await engine.has_permissions(
        _SUBJECT,
        [TeamPermission.CAN_READ],
        _TEAM,
        consistency_token="tok-123",  # nosec B106 — OpenFGA consistency token, not a credential
    )

    _body, options = client.calls[0]
    assert options["consistency"] == "tok-123"


@pytest.mark.asyncio
async def test_contextual_tuples_are_transmitted_identically_to_every_check() -> None:
    """6: the same contextual tuple list applies to every check item."""
    client = _FakeBatchCheckClient()
    engine = _make_engine(client)
    contextual = [
        Relation(
            subject=RebacReference(Resource.ORGANIZATION, "fred"),
            relation=RelationType.ORGANIZATION,
            resource=_TEAM,
        )
    ]

    await engine.has_permissions(
        _SUBJECT,
        [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO],
        _TEAM,
        contextual_relations=contextual,
    )

    body, _options = client.calls[0]
    for item in body.checks:
        assert item.contextual_tuples is not None
        assert len(item.contextual_tuples) == 1
        assert item.contextual_tuples[0].user == "organization:fred"
        assert item.contextual_tuples[0].relation == "organization"
        assert item.contextual_tuples[0].object == "team:fredlab"


@pytest.mark.parametrize(
    ("case", "results"),
    [
        (
            "per_check_error",
            [
                _SingleResult(allowed=True, correlation_id="0"),
                _SingleResult(
                    allowed=False, correlation_id="1", error="internal error"
                ),
            ],
        ),
        (
            "missing_correlation_id",
            [_SingleResult(allowed=True, correlation_id="0")],
        ),
        (
            "unknown_correlation_id",
            [
                _SingleResult(allowed=True, correlation_id="0"),
                _SingleResult(allowed=True, correlation_id="1"),
                _SingleResult(allowed=True, correlation_id="99"),
            ],
        ),
        (
            "duplicate_correlation_id",
            [
                _SingleResult(allowed=True, correlation_id="0"),
                _SingleResult(allowed=False, correlation_id="0"),
                _SingleResult(allowed=True, correlation_id="1"),
            ],
        ),
    ],
)
@pytest.mark.asyncio
async def test_malformed_batch_check_response_raises_instead_of_downgrading(
    case: str, results: list[_SingleResult]
) -> None:
    """8: a malformed BatchCheck response — a per-check `error`, a missing
    correlation_id, an unrecognized one, or a duplicate — must fail the whole
    operation loudly, never silently downgraded to "not authorized" nor
    silently dropped/overwritten."""
    client = _FakeBatchCheckClient(results=results)
    engine = _make_engine(client)

    with pytest.raises(RuntimeError):
        await engine.has_permissions(
            _SUBJECT,
            [TeamPermission.CAN_READ, TeamPermission.CAN_UPDATE_INFO],
            _TEAM,
        )


@pytest.mark.asyncio
async def test_batch_check_emits_one_logical_check_operation() -> None:
    """9: one `rebac.call_total{rebac_operation=check}` for the whole batch —
    not one per permission, and no new dimension/label introduced."""
    writer = _RecordingKPIWriter()
    client = _FakeBatchCheckClient()
    engine = _make_engine(client, kpi_writer=writer)

    await engine.has_permissions(_SUBJECT, _ALL_TEAM_PERMISSIONS, _TEAM)

    check_emits = [
        e for e in writer.emitted if e["dims"].get("rebac_operation") == "check"
    ]
    check_counts = [
        c for c in writer.counted if c["dims"].get("rebac_operation") == "check"
    ]
    assert len(check_emits) == 1
    assert len(check_counts) == 1


class _ConcurrentFallbackRebacEngine(NoopRebacEngine):
    """Exercises the base-class default `has_permissions` (no OpenFGA
    override) — asserts it runs every `has_permission` concurrently rather
    than sequentially, and preserves input order. Subclasses `NoopRebacEngine`
    and overrides only `has_permission`, the one method this test cares
    about."""

    def __init__(self) -> None:
        self.in_flight = 0
        self.max_in_flight = 0
        self.checked_permissions: list[RebacPermission] = []

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Any = None,
        consistency_token: str | None = None,
    ) -> bool:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        await asyncio.sleep(0)  # yield so overlapping calls can interleave
        self.checked_permissions.append(permission)
        self.in_flight -= 1
        return permission == TeamPermission.CAN_UPDATE_INFO


@pytest.mark.asyncio
async def test_base_class_fallback_runs_has_permission_concurrently() -> None:
    """10: without a native BatchCheck, the default falls back to concurrent
    `has_permission`s (not sequential) and still returns results in order."""
    engine = _ConcurrentFallbackRebacEngine()

    allowed = await engine.has_permissions(_SUBJECT, _ALL_TEAM_PERMISSIONS, _TEAM)

    assert engine.max_in_flight > 1, "has_permission calls must overlap, not serialize"
    assert allowed == [
        p == TeamPermission.CAN_UPDATE_INFO for p in _ALL_TEAM_PERMISSIONS
    ]


class _RecordingContextualRelationsEngine(NoopRebacEngine):
    """Records the `contextual_relations` sequence each concurrent
    `has_permission` call actually observed."""

    def __init__(self) -> None:
        self.seen: list[tuple[Relation, ...]] = []

    async def has_permission(
        self,
        subject: RebacReference,
        permission: RebacPermission,
        resource: RebacReference,
        *,
        contextual_relations: Any = None,
        consistency_token: str | None = None,
    ) -> bool:
        await asyncio.sleep(0)  # yield so calls interleave, like the real fallback
        self.seen.append(tuple(contextual_relations or ()))
        return True


@pytest.mark.asyncio
async def test_base_class_fallback_materializes_contextual_relations_once() -> None:
    """4: a `contextual_relations` generator must not be exhausted by the
    first concurrent `has_permission` call — the base-class fallback
    materializes it once, up front, so every call sees the identical,
    fully-populated sequence rather than an empty one after the first."""
    engine = _RecordingContextualRelationsEngine()
    contextual_relation = Relation(
        subject=RebacReference(Resource.ORGANIZATION, "fred"),
        relation=RelationType.ORGANIZATION,
        resource=_TEAM,
    )

    def _contextual_relations_once():
        yield contextual_relation

    await engine.has_permissions(
        _SUBJECT,
        [
            TeamPermission.CAN_READ,
            TeamPermission.CAN_UPDATE_INFO,
            TeamPermission.CAN_READ_MEMEBERS,
        ],
        _TEAM,
        contextual_relations=_contextual_relations_once(),
    )

    assert len(engine.seen) == 3
    assert all(seen == (contextual_relation,) for seen in engine.seen)
