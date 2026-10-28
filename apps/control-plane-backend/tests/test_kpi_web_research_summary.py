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

"""`web_research_summary` classification; the OpenSearch client is faked."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, cast

import pytest
from control_plane_backend.capabilities import enablement
from control_plane_backend.kpi.presets import web_research_summary as module
from control_plane_backend.kpi.presets.web_research_summary import (
    WEB_RESEARCH_SUMMARY_PRESET,
    query_web_research_summary,
    web_research_enabled,
)
from fred_core import ORGANIZATION_ID, RebacDisabledResult, RelationType
from fred_core.common import TeamId
from fred_core.security.models import Resource
from fred_core.security.rebac.rebac_engine import RebacReference, Relation

SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
UNTIL = SINCE + timedelta(days=7)


class _FakeClient:
    def __init__(self) -> None:
        self.body: dict[str, Any] = {}

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        del index
        self.body = body
        return {
            "hits": {"total": {"value": 120}},
            "aggregations": {
                "unique_users": {"value": 9},
                "p95": {"values": {"95.0": 1834.6}},
                "billable": {"doc_count": 100, "usd": {"value": 0.5}},
                "errors": {"doc_count": 12},
                "by_tool": {
                    "buckets": [
                        {"key": "web_search", "doc_count": 100},
                        {"key": "fetch_url", "doc_count": 20},
                    ]
                },
                "by_reason": {
                    "buckets": [
                        {"key": "unsafe_destination", "doc_count": 4},
                        {"key": "response_too_large", "doc_count": 1},
                        {"key": "busy", "doc_count": 3},
                        {"key": "provider_failed", "doc_count": 4},
                    ]
                },
            },
        }


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> dict[str, bool]:
    state = {"on": True}

    async def _enabled(_request: Any) -> bool:
        return state["on"]

    monkeypatch.setattr(module, "web_research_enabled", _enabled)
    return state


@pytest.mark.asyncio
async def test_summary_splits_blocked_saturated_and_failed_and_scopes_team(
    enabled: dict[str, bool],
) -> None:
    client = _FakeClient()
    store = SimpleNamespace(client=client, index="kpi")
    result = await query_web_research_summary(
        cast(Any, store),
        user=cast(Any, None),
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_ids=(TeamId("team-a"), TeamId("team-b")),
    )
    assert (result.tool_calls, result.searches, result.fetches) == (120, 100, 20)
    assert result.billable_searches == 100
    # 0.5 USD at the shipped rate (1 EUR = 1.12 USD).
    assert result.available is True
    assert result.estimated_cost_eur == pytest.approx(0.4464, abs=1e-4)
    assert (result.blocked, result.saturated, result.failed) == (5, 3, 4)
    assert (result.unique_users, result.p95_ms) == (9, 1835)
    assert {"terms": {"dims.team_id": ["team-a", "team-b"]}} in client.body["query"][
        "bool"
    ]["filter"]
    # Observers see the Technical tab: no admin-only flag is left.
    assert not hasattr(WEB_RESEARCH_SUMMARY_PRESET, "platform_admin_only")


@pytest.mark.asyncio
async def test_summary_is_empty_and_unavailable_when_disabled(
    enabled: dict[str, bool],
) -> None:
    enabled["on"] = False
    client = _FakeClient()
    result = await query_web_research_summary(
        cast(Any, SimpleNamespace(client=client, index="kpi")),
        user=cast(Any, None),
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
    )
    assert result.available is False
    assert (result.tool_calls, result.estimated_cost_eur, result.by_reason) == (
        0,
        0.0,
        [],
    )
    assert client.body == {}  # no KPI search at all


def _relation(relation: RelationType, subject: RebacReference) -> Relation:
    return Relation(
        subject=subject,
        relation=relation,
        resource=RebacReference(Resource.CAPABILITY, "web_research"),
    )


ORG = RebacReference(Resource.ORGANIZATION, ORGANIZATION_ID)
TEAM = RebacReference(Resource.TEAM, "team-a")


@pytest.mark.parametrize(
    ("relations", "expected"),
    [
        ([], False),
        ([_relation(RelationType.ORGANIZATION, ORG)], False),
        ([_relation(RelationType.DISABLED, TEAM)], False),
        ([_relation(RelationType.ENABLED, TEAM)], True),
        ([_relation(RelationType.DEFAULT_ON, ORG)], True),
        ([_relation(RelationType.PERSONAL_ON, ORG)], True),
        (RebacDisabledResult(), True),
    ],
)
@pytest.mark.asyncio
async def test_enabled_when_usable_by_a_team_or_personal_spaces(
    monkeypatch: pytest.MonkeyPatch, relations: Any, expected: bool
) -> None:
    async def _cached(_rebac: Any, capability_id: str) -> Any:
        assert capability_id == "web_research"
        return relations

    monkeypatch.setattr(enablement, "get_capability_relations_cached", _cached)
    monkeypatch.setattr(
        module,
        "get_application_container",
        lambda _r: SimpleNamespace(get_rebac_engine=lambda: object()),
    )
    assert await web_research_enabled(cast(Any, None)) is expected
