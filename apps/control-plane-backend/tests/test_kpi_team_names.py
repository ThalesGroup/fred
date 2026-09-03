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

"""`resolve_team_names` fallbacks.

Two KPI presets label a team with this, and both degrade to raw ids rather
than failing the chart. That degradation is the contract worth pinning: it is
invisible in the response, so a regression here ships looking healthy.
"""

from __future__ import annotations

from typing import Any

import pytest
from control_plane_backend.kpi.presets import team_names as module
from control_plane_backend.kpi.presets.team_names import resolve_team_names


class _FakeStore:
    def __init__(self, rows: dict[str, str] | Exception) -> None:
        self._rows = rows

    async def get_by_team_ids(self, team_ids: list[Any]) -> dict[Any, Any]:
        if isinstance(self._rows, Exception):
            raise self._rows
        return {
            tid: type("Row", (), {"name": self._rows[str(tid)]})()
            for tid in team_ids
            if str(tid) in self._rows
        }


def _patch_store(monkeypatch: pytest.MonkeyPatch, store: _FakeStore) -> None:
    container = type(
        "Container", (), {"get_team_metadata_store": lambda _self: store}
    )()
    monkeypatch.setattr(module, "get_application_container", lambda _request: container)


@pytest.mark.asyncio
async def test_no_ids_short_circuits_before_touching_the_container() -> None:
    # No _patch_store: reaching the container at all would raise here.
    assert await resolve_team_names(None, []) == {}  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_known_ids_resolve_to_their_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_store(monkeypatch, _FakeStore({"team-a": "Swiftpost"}))

    result = await resolve_team_names(None, ["team-a"])  # pyright: ignore[reportArgumentType]

    assert result == {"team-a": "Swiftpost"}


@pytest.mark.asyncio
async def test_a_team_with_no_registry_row_falls_back_to_its_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_store(monkeypatch, _FakeStore({"team-a": "Swiftpost"}))

    result = await resolve_team_names(None, ["team-a", "team-gone"])  # pyright: ignore[reportArgumentType]

    assert result == {"team-a": "Swiftpost", "team-gone": "team-gone"}


@pytest.mark.asyncio
async def test_an_unreachable_store_degrades_to_ids_and_says_so(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The silent version of this is indistinguishable from deleted teams."""
    _patch_store(monkeypatch, _FakeStore(RuntimeError("postgres is down")))

    with caplog.at_level("WARNING"):
        result = await resolve_team_names(None, ["team-a", "team-b"])  # pyright: ignore[reportArgumentType]

    assert result == {"team-a": "team-a", "team-b": "team-b"}
    assert any("raw team ids" in record.message for record in caplog.records)
