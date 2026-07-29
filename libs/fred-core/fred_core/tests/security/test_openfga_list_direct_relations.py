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

"""`RebacEngine.list_direct_relations` — every relation literally persisted on
one exact resource, in one `Read` (no relation filter, so a single team's
`team_admin`/`team_editor`/`team_analyst`/`team_member`/`organization`/
`public` tuples all come back together) — the primitive that lets
control-plane project one team's admins/member_count/is_member/my_relations
from a single round-trip instead of a bulk cross-team scan.

An optional exact `subject` narrows the same Read server-side (`body.user`)
so a caller interested in one subject's own relations (e.g.
`_get_user_roles_in_team`) transfers O(that subject's relations), never
O(every relation on the resource) filtered client-side after the fact.

The real `openfga_sdk` client is never invoked — its `read` method is a fake,
so these stay offline unit tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from fred_core.security.models import Resource
from fred_core.security.rebac.noop_engine import NoopRebacEngine
from fred_core.security.rebac.openfga_engine import OpenFgaRebacEngine
from fred_core.security.rebac.rebac_engine import (
    RebacDisabledResult,
    RebacReference,
    RelationType,
)
from fred_core.security.structure import OpenFgaRebacConfig


class _FakeOpenFgaClient:
    def __init__(self, pages: list[list[Any]] | None = None) -> None:
        self.read_calls: list[Any] = []
        self._pages = pages if pages is not None else [[]]

    async def read(self, body, options) -> SimpleNamespace:
        self.read_calls.append(body)
        index = int(options.get("continuation_token") or 0)
        next_index = index + 1
        token = str(next_index) if next_index < len(self._pages) else ""
        return SimpleNamespace(tuples=self._pages[index], continuation_token=token)  # nosec B106 — pagination token, not a secret

    async def list_objects(self, *_a, **_k) -> None:
        raise AssertionError("ListObjects must not be called by list_direct_relations")

    async def list_users(self, *_a, **_k) -> None:
        raise AssertionError("ListUsers must not be called by list_direct_relations")


def _tup(user: str, relation: str, obj: str) -> SimpleNamespace:
    return SimpleNamespace(
        key=SimpleNamespace(user=user, relation=relation, object=obj)
    )


def _make_engine(client: _FakeOpenFgaClient) -> OpenFgaRebacEngine:
    config = OpenFgaRebacConfig(
        api_url="http://fake-openfga:8080"  # pyright: ignore[reportArgumentType]
    )
    engine = OpenFgaRebacEngine(config, token="test-token")  # nosec B106 — fake test credential, no real OpenFGA is contacted
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


_TEAM = RebacReference(Resource.TEAM, "fredlab")


@pytest.mark.asyncio
async def test_reads_the_exact_object_with_no_relation_or_subject_filter() -> None:
    """8: `ReadRequestTupleKey.object` is the exact team id; no `relation` or
    `user` is imposed when `subject` is omitted, so every relation type on
    that team comes back."""
    client = _FakeOpenFgaClient(pages=[[]])
    engine = _make_engine(client)

    await engine.list_direct_relations(_TEAM)

    assert len(client.read_calls) == 1
    body = client.read_calls[0]
    assert body.object == "team:fredlab"
    assert body.relation is None
    assert body.user is None


@pytest.mark.asyncio
async def test_exact_subject_is_pushed_into_the_read_filter() -> None:
    """9: passing `subject` sets `body.user` to that exact `type:id` so
    OpenFGA itself narrows server-side — never a client-side filter applied
    after a full-object transfer."""
    client = _FakeOpenFgaClient(pages=[[]])
    engine = _make_engine(client)

    await engine.list_direct_relations(
        _TEAM, subject=RebacReference(Resource.USER, "alice")
    )

    assert len(client.read_calls) == 1
    body = client.read_calls[0]
    assert body.object == "team:fredlab"
    assert body.relation is None
    assert body.user == "user:alice"


@pytest.mark.asyncio
async def test_converts_every_relation_type_present() -> None:
    """Mixed relation types on the same team all convert to `Relation`."""
    client = _FakeOpenFgaClient(
        pages=[
            [
                _tup("user:alice", "team_admin", "team:fredlab"),
                _tup("user:bob", "team_member", "team:fredlab"),
                _tup("organization:fred", "organization", "team:fredlab"),
                _tup("user:*", "public", "team:fredlab"),
            ]
        ]
    )
    engine = _make_engine(client)

    relations = await engine.list_direct_relations(_TEAM)

    assert set((r.subject.type, r.subject.id, r.relation) for r in relations) == {
        (Resource.USER, "alice", RelationType.TEAM_ADMIN),
        (Resource.USER, "bob", RelationType.TEAM_MEMBER),
        (Resource.ORGANIZATION, "fred", RelationType.ORGANIZATION),
        (Resource.USER, "*", RelationType.PUBLIC),
    }
    assert all(
        r.resource == RebacReference(Resource.TEAM, "fredlab") for r in relations
    )


@pytest.mark.asyncio
async def test_paginates_via_continuation_token() -> None:
    """10: every page is fetched and folded into one result list."""
    client = _FakeOpenFgaClient(
        pages=[
            [_tup("user:alice", "team_admin", "team:fredlab")],
            [_tup("user:bob", "team_member", "team:fredlab")],
        ]
    )
    engine = _make_engine(client)

    relations = await engine.list_direct_relations(_TEAM)

    assert len(client.read_calls) == 2
    assert {r.subject.id for r in relations} == {"alice", "bob"}


@pytest.mark.asyncio
async def test_consistency_token_reaches_the_read_options() -> None:
    """10: the consistency token is forwarded into the `Read` call options."""

    class _OptionCapturingClient(_FakeOpenFgaClient):
        def __init__(self) -> None:
            super().__init__(pages=[[]])
            self.options_seen: list[Any] = []

        async def read(self, body, options) -> SimpleNamespace:
            self.options_seen.append(options)
            return await super().read(body, options)

    client = _OptionCapturingClient()
    engine = _make_engine(client)

    await engine.list_direct_relations(_TEAM, consistency_token="tok-abc")  # nosec B106 — OpenFGA consistency token, not a credential

    assert client.options_seen[0]["consistency"] == "tok-abc"


@pytest.mark.asyncio
async def test_never_calls_list_users_or_list_objects() -> None:
    """`_FakeOpenFgaClient.list_objects`/`list_users` raise unconditionally —
    a normal, non-raising return here already proves `list_direct_relations`
    never reaches for either."""
    client = _FakeOpenFgaClient(pages=[[]])
    engine = _make_engine(client)

    await engine.list_direct_relations(_TEAM)


@pytest.mark.asyncio
async def test_noop_engine_returns_disabled_result() -> None:
    """11: `NoopRebacEngine` returns `RebacDisabledResult`, subject or not."""
    engine = NoopRebacEngine()

    result = await engine.list_direct_relations(_TEAM)
    result_with_subject = await engine.list_direct_relations(
        _TEAM, subject=RebacReference(Resource.USER, "alice")
    )

    assert isinstance(result, RebacDisabledResult)
    assert isinstance(result_with_subject, RebacDisabledResult)
