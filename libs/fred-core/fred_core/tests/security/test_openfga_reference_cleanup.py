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

"""Verify bounded exact-reference cleanup without external services."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openfga_sdk.models.consistency_preference import ConsistencyPreference

import fred_core
from fred_core.security.models import Resource
from fred_core.security.rebac.openfga_engine import (
    _MAX_REFERENCE_CLEANUP_PASSES,
    _MAX_TUPLES_PER_WRITE,
    OpenFgaRebacEngine,
    RebacCleanupIncomplete,
)
from fred_core.security.rebac.rebac_engine import RebacReference
from fred_core.security.structure import OpenFgaRebacConfig

_APP = RebacReference(Resource.APP, "acme-forecast")
_APP_ID = "app:acme-forecast"


class _FakeOpenFgaClient:
    """Mutable tuple store: deletes take effect, so re-reads observe them.

    ``page_size`` forces the Read pagination path, and ``regrow`` models a
    writer that keeps adding tuples while cleanup runs.
    """

    def __init__(
        self,
        tuples: list[tuple[str, str, str]],
        *,
        page_size: int = 1000,
        regrow: bool = False,
    ) -> None:
        self.store: list[tuple[str, str, str]] = list(tuples)
        self._page_size = page_size
        self._regrow = regrow
        self.write_batch_sizes: list[int] = []
        self.read_pages_served = 0
        self.read_consistency_options: list[object] = []

    async def read(self, body, options) -> SimpleNamespace:
        index = int(options.get("continuation_token") or 0)
        page = self.store[index : index + self._page_size]
        self.read_pages_served += 1
        self.read_consistency_options.append(options.get("consistency"))
        next_index = index + self._page_size
        token = str(next_index) if next_index < len(self.store) else ""
        keys = [
            SimpleNamespace(key=SimpleNamespace(user=u, relation=r, object=o))
            for u, r, o in page
        ]
        return SimpleNamespace(tuples=keys, continuation_token=token)  # nosec B106 — pagination token, not a secret

    async def write(self, body, options) -> Any:
        deletes = list(body.deletes or [])
        self.write_batch_sizes.append(len(deletes))
        removed = {(t.user, t.relation, t.object) for t in deletes}
        self.store = [t for t in self.store if t not in removed]
        if self._regrow:
            self.store.append(("team:late", "enabled", _APP_ID))
        return SimpleNamespace()


def _make_engine(client: _FakeOpenFgaClient) -> OpenFgaRebacEngine:
    config = OpenFgaRebacConfig(
        api_url="http://fake-openfga:8080"  # pyright: ignore[reportArgumentType]
    )
    engine = OpenFgaRebacEngine(config, token="test-token")  # nosec B106 — synthetic offline fixture
    engine._cached_client = client  # pyright: ignore[reportAttributeAccessIssue]
    return engine


@pytest.mark.asyncio
async def test_removes_every_tuple_naming_the_reference_on_either_side() -> None:
    client = _FakeOpenFgaClient(
        [
            ("team:alpha", "enabled", _APP_ID),
            ("organization:main", "default_on", _APP_ID),
            (_APP_ID, "parent", "organization:main"),
        ]
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []


@pytest.mark.asyncio
async def test_unrelated_references_survive_the_cleanup() -> None:
    survivor = ("team:alpha", "enabled", "app:other-app")
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID), survivor])

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == [survivor]


@pytest.mark.asyncio
async def test_a_large_reference_is_deleted_within_the_per_write_limit() -> None:
    """One oversized write is rejected by the server, so batches must be bound."""
    count = _MAX_TUPLES_PER_WRITE * 2 + 5
    client = _FakeOpenFgaClient(
        [(f"team:t{i}", "enabled", _APP_ID) for i in range(count)]
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []
    assert max(client.write_batch_sizes) <= _MAX_TUPLES_PER_WRITE
    assert sum(client.write_batch_sizes) == count


@pytest.mark.asyncio
async def test_tuples_beyond_the_first_read_page_are_deleted_too() -> None:
    client = _FakeOpenFgaClient(
        [(f"team:t{i}", "enabled", _APP_ID) for i in range(7)], page_size=2
    )

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store == []


@pytest.mark.asyncio
async def test_cleanup_ends_only_after_a_pass_that_finds_nothing() -> None:
    """A cursor reaching its end is not the same as an empty re-read."""
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID)], page_size=1)

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    # One enumerating pass, then a second that finds nothing and stops.
    assert client.read_pages_served >= 2
    assert client.store == []


@pytest.mark.asyncio
async def test_every_enumeration_asks_for_higher_consistency() -> None:
    """Reject stale empty reads as evidence of completion."""
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID)])

    await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.read_consistency_options
    assert set(client.read_consistency_options) == {
        ConsistencyPreference.HIGHER_CONSISTENCY
    }


@pytest.mark.asyncio
async def test_a_reference_that_keeps_regaining_tuples_fails_loudly() -> None:
    """Cleanup must not return success while tuples it read still exist."""
    client = _FakeOpenFgaClient([("team:alpha", "enabled", _APP_ID)], regrow=True)

    with pytest.raises(RebacCleanupIncomplete):
        await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert client.store != []
    assert len(client.write_batch_sizes) == _MAX_REFERENCE_CLEANUP_PASSES


@pytest.mark.asyncio
async def test_a_reference_with_no_tuples_writes_nothing() -> None:
    client = _FakeOpenFgaClient([("team:alpha", "enabled", "app:other-app")])

    result = await _make_engine(client).delete_all_relations_of_reference(_APP)

    assert result is None
    assert client.write_batch_sizes == []


def test_cleanup_incomplete_is_exported_from_the_package_root() -> None:
    assert fred_core.RebacCleanupIncomplete is RebacCleanupIncomplete
    assert "RebacCleanupIncomplete" in fred_core.__all__
