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
Regression guard for the §2.4 "Personal presets (Page 3)" gate: the three
`user_token_usage_*` presets must be `self_scoped` (so `resolve_kpi_scope`
skips OpenFGA — see `test_kpi_scope.py`) and never `team_scopable` (a
personal-usage preset accepting a `team_id` would defeat its own "my own
data" contract). Before this fix, none of the three declared `self_scoped`,
so the router's authorization chokepoint required `can_observe_platform` —
403ing any user who wasn't a platform admin/observer out of their own token
usage.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from control_plane_backend.kpi.presets.user_token_usage_by_agent import (
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_by_model import (
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
)
from control_plane_backend.kpi.presets.user_token_usage_over_time import (
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
    query_user_token_usage_over_time,
)
from fred_core.kpi.model_impact_factors import ModelImpactFactors

_PRESETS = [
    USER_TOKEN_USAGE_OVER_TIME_PRESET,
    USER_TOKEN_USAGE_BY_AGENT_PRESET,
    USER_TOKEN_USAGE_BY_MODEL_PRESET,
]


def test_user_token_usage_presets_are_self_scoped() -> None:
    for preset in _PRESETS:
        assert preset.self_scoped is True, preset.name


def test_user_token_usage_presets_are_not_team_scopable() -> None:
    for preset in _PRESETS:
        assert preset.team_scopable is False, preset.name


def test_personal_time_series_accepts_calendar_bucket() -> None:
    assert USER_TOKEN_USAGE_OVER_TIME_PRESET.bucketable


class _FakeStore:
    index = "kpi-events"

    def __init__(self, response: dict[str, Any]) -> None:
        self.client = SimpleNamespace(search=lambda index, body: response)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("bucket", "interval", "starts"),
    [
        ("day", "1d", ["2026-10-25", "2026-10-26"]),
        ("week", "1w", ["2026-10-19", "2026-10-26"]),
        ("month", "1M", ["2026-10-01", "2026-11-01"]),
    ],
)
async def test_personal_token_calendar_buckets_keep_totals_and_local_starts(
    bucket: str, interval: str, starts: list[str]
) -> None:
    response = {
        "aggregations": {
            "by_time": {
                "buckets": [
                    {
                        "key_as_string": start,
                        "sum_input": {"value": value},
                        "sum_output": {"value": 2},
                        "by_model": {"buckets": {}},
                    }
                    for start, value in zip(starts, [10, 20], strict=True)
                ]
            }
        }
    }
    captured: list[dict[str, Any]] = []
    store = _FakeStore(response)
    store.client = SimpleNamespace(
        search=lambda index, body: (captured.append(body), response)[1]
    )
    result = await query_user_token_usage_over_time(
        store,  # type: ignore[arg-type]
        user=SimpleNamespace(uid="u1"),  # type: ignore[arg-type]
        since=datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc),
        until=datetime(2026, 11, 2, tzinfo=timezone.utc),
        request=None,  # type: ignore[arg-type]
        bucket=bucket,  # type: ignore[arg-type]
        tz="Europe/Paris",
    )
    histogram = captured[0]["aggs"]["by_time"]["date_histogram"]
    assert histogram["calendar_interval"] == interval
    assert histogram["time_zone"] == "Europe/Paris"
    assert histogram["extended_bounds"]["min"] == int(
        datetime(2026, 10, 25, 0, 30, tzinfo=timezone.utc).timestamp() * 1000
    )
    assert histogram["extended_bounds"]["max"] == int(
        (datetime(2026, 11, 2, tzinfo=timezone.utc).timestamp() * 1000) - 1
    )
    assert captured[0]["query"]["bool"]["filter"][0]["range"]["@timestamp"]["lt"] == (
        "2026-11-02T00:00:00+00:00"
    )
    assert captured[0]["query"]["bool"]["filter"][2] == {"term": {"dims.user_id": "u1"}}
    assert result.interval == interval
    assert [row.date for row in result.rows] == starts
    assert sum(row.value for row in result.rows) == 34


@pytest.mark.asyncio
async def test_personal_token_cost_is_in_euros(monkeypatch: pytest.MonkeyPatch) -> None:
    factors = {
        "m": ModelImpactFactors(cost_per_1k_input_tokens=1.12),
        "default": ModelImpactFactors(),
    }
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: factors,
    )
    monkeypatch.setattr(
        "control_plane_backend.kpi.presets.user_token_usage_over_time.load_model_impact_factors",
        lambda: factors,
    )
    store = _FakeStore(
        {
            "aggregations": {
                "by_time": {
                    "buckets": [
                        {
                            "key_as_string": "2026-10-01T00:00:00Z",
                            "sum_input": {"value": 1000.0},
                            "sum_output": {"value": 0.0},
                            "by_model": {
                                "buckets": {
                                    "m": {
                                        "sum_input": {"value": 1000.0},
                                        "sum_output": {"value": 0.0},
                                    }
                                }
                            },
                        }
                    ]
                }
            }
        }
    )
    result = await query_user_token_usage_over_time(
        store,  # type: ignore[arg-type]
        user=SimpleNamespace(uid="u1"),  # type: ignore[arg-type]
        since=datetime(2026, 10, 1, tzinfo=timezone.utc),
        until=datetime(2026, 10, 2, tzinfo=timezone.utc),
        request=None,  # type: ignore[arg-type]
    )
    # 1.12 USD at the default rate of 1.12 USD per euro.
    assert result.rows[0].cost_eur == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_personal_token_impact_includes_models_outside_top_fifty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "control_plane_backend.kpi.presets.user_token_usage_over_time.load_model_impact_factors",
        lambda: {"m": ModelImpactFactors(), "default": ModelImpactFactors()},
    )
    buckets = {
        "m": {"sum_input": {"value": 5}, "sum_output": {"value": 0}},
        "__unmodeled__": {"sum_input": {"value": 51}, "sum_output": {"value": 0}},
    }
    captured: list[dict[str, Any]] = []
    response = {
        "aggregations": {
            "by_time": {
                "buckets": [
                    {
                        "key_as_string": "2026-10-01",
                        "sum_input": {"value": 56},
                        "sum_output": {"value": 0},
                        "by_model": {"buckets": buckets},
                    }
                ]
            }
        }
    }
    store = _FakeStore(response)
    store.client = SimpleNamespace(
        search=lambda index, body: (captured.append(body), response)[1]
    )
    result = await query_user_token_usage_over_time(
        store,  # type: ignore[arg-type]
        user=SimpleNamespace(uid="u1"),  # type: ignore[arg-type]
        since=datetime(2026, 10, 1, tzinfo=timezone.utc),
        until=datetime(2026, 11, 1, tzinfo=timezone.utc),
        request=None,  # type: ignore[arg-type]
        bucket="month",
    )
    assert captured[0]["aggs"]["by_time"]["aggs"]["by_model"]["filters"] == {
        "filters": {"m": {"term": {"dims.model_name": "m"}}},
        "other_bucket": True,
        "other_bucket_key": "__unmodeled__",
    }
    assert result.rows[0].value == 56
    assert result.rows[0].co2e_grams == pytest.approx(56 / 1000 * 0.6)
