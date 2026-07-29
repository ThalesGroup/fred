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

"""#2065: control-plane startup reconciliation of the `organization -> team`
structural edge (`main.py::_reconcile_team_organization_relations`).

Per-request paths no longer read or repair this edge at all — it's
established directly at team creation, and this cold-path pass is the only
remaining place a pre-existing (or otherwise missed) team gets it backfilled.
The exact bulk-read/skip-write behavior of `ensure_team_organization_relations`
itself is already covered exhaustively by
`fred_core/tests/security/test_rebac_engine_team_helpers.py`
(`test_ensure_team_organization_relations_skips_already_granted_edges` etc.) —
this file only tests the main.py wrapper: registry gathering, the enabled
short-circuit, the advisory lock, and fail-closed behavior on error.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import MagicMock

import pytest
from control_plane_backend.main import _reconcile_team_organization_relations
from fred_core.common import TeamId
from fred_core.teams.metadata_store import TeamMetadata


class _FakeStore:
    def __init__(self, teams: list[TeamMetadata]) -> None:
        self._teams = teams
        self.advisory_lock_keys: list[str] = []

    async def list_all(self) -> list[TeamMetadata]:
        return self._teams

    @asynccontextmanager
    async def advisory_lock(self, key: str) -> AsyncIterator[None]:
        self.advisory_lock_keys.append(key)
        yield


class _FakeRebac:
    def __init__(
        self, *, enabled: bool = True, raises: Exception | None = None
    ) -> None:
        self.enabled = enabled
        self._raises = raises
        self.ensure_calls: list[list[str]] = []

    async def ensure_team_organization_relations(self, team_ids) -> None:
        ids = list(team_ids)
        self.ensure_calls.append(ids)
        if self._raises is not None:
            raise self._raises


def _container(rebac: _FakeRebac, store: _FakeStore) -> MagicMock:
    container = MagicMock()
    container.get_rebac_engine.return_value = rebac
    container.get_team_metadata_store.return_value = store
    return container


@pytest.mark.asyncio
async def test_empty_registry_makes_zero_openfga_calls() -> None:
    rebac = _FakeRebac()
    store = _FakeStore([])

    await _reconcile_team_organization_relations(_container(rebac, store))

    assert rebac.ensure_calls == []
    # Still serialized against concurrent replicas even for an empty registry
    # — the lock guards the read itself, not just the write.
    assert store.advisory_lock_keys == ["team_organization_relations_reconcile"]


@pytest.mark.asyncio
async def test_reconciles_every_team_in_the_registry_once() -> None:
    rebac = _FakeRebac()
    store = _FakeStore(
        [
            TeamMetadata(id=TeamId("team-a"), name="A"),
            TeamMetadata(id=TeamId("team-b"), name="B"),
        ]
    )

    await _reconcile_team_organization_relations(_container(rebac, store))

    assert rebac.ensure_calls == [["team-a", "team-b"]]


@pytest.mark.asyncio
async def test_disabled_rebac_skips_entirely_without_acquiring_the_lock() -> None:
    rebac = _FakeRebac(enabled=False)
    store = _FakeStore([TeamMetadata(id=TeamId("team-a"), name="A")])

    await _reconcile_team_organization_relations(_container(rebac, store))

    assert rebac.ensure_calls == []
    assert store.advisory_lock_keys == []


@pytest.mark.asyncio
async def test_openfga_error_with_rebac_enabled_aborts_startup() -> None:
    """Fail-closed: an outage here must stop the ASGI lifespan from ever
    reaching `yield` — the pod must not start serving requests against teams
    this invariant may not cover."""
    rebac = _FakeRebac(raises=RuntimeError("openfga unreachable"))
    store = _FakeStore([TeamMetadata(id=TeamId("team-a"), name="A")])

    with pytest.raises(RuntimeError, match="openfga unreachable"):
        await _reconcile_team_organization_relations(_container(rebac, store))
