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
from control_plane_backend.kpi.presets.web_research_summary import (
    WEB_RESEARCH_SUMMARY_PRESET,
    query_web_research_summary,
)

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


@pytest.mark.asyncio
async def test_summary_splits_blocked_saturated_and_failed_and_scopes_team() -> None:
    client = _FakeClient()
    store = SimpleNamespace(client=client, index="kpi")
    result = await query_web_research_summary(
        cast(Any, store),
        user=cast(Any, None),
        since=SINCE,
        until=UNTIL,
        request=cast(Any, None),
        team_id=cast(Any, "team-a"),
    )
    assert (result.tool_calls, result.searches, result.fetches) == (120, 100, 20)
    assert result.billable_searches == 100
    assert result.estimated_cost_usd == 0.5
    assert (result.blocked, result.saturated, result.failed) == (5, 3, 4)
    assert (result.unique_users, result.p95_ms) == (9, 1835)
    assert {"term": {"dims.team_id": "team-a"}} in client.body["query"]["bool"][
        "filter"
    ]
    assert WEB_RESEARCH_SUMMARY_PRESET.platform_admin_only
