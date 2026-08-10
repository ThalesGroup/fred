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
CACHE-01: `token_usage_by_model` must aggregate `quantities.cache_read_tokens`
and pass it into `estimate_green_cost`, so the platform-wide cost figure
reflects provider-side prompt-cache discounts instead of billing every input
token at the full rate.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fred_core.kpi.model_impact_factors import ModelImpactFactors

from control_plane_backend.kpi.presets.token_usage_by_model import (
    query_token_usage_by_model,
)


class _FakeSearchClient:
    def __init__(self, response: dict) -> None:
        self._response = response

    def search(self, index: str, body: dict) -> dict:
        del index, body
        return self._response


class _FakeStore:
    def __init__(self, response: dict) -> None:
        self.client = _FakeSearchClient(response)
        self.index = "kpi-events"


_FACTORS = {
    "gpt-5.1": ModelImpactFactors(
        cost_per_1k_input_tokens=0.002,
        cost_per_1k_cached_input_tokens=0.0002,
        cost_per_1k_output_tokens=0.008,
    ),
    "default": ModelImpactFactors(),
}


@pytest.mark.asyncio
async def test_token_usage_by_model_bills_cache_reads_at_the_reduced_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # `estimate_green_cost` (imported by name into token_usage_by_model.py)
    # calls `load_model_impact_factors()` via its own module globals, so
    # patching the function at its origin module is enough to redirect it —
    # same pattern as fred_core.kpi.tests.test_model_impact_factors.
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: _FACTORS,
    )

    opensearch_response = {
        "aggregations": {
            "by_model": {
                "buckets": [
                    {
                        "key": "gpt-5.1",
                        "sum_input": {"value": 1000.0},
                        "sum_output": {"value": 200.0},
                        "sum_cache_read": {"value": 800.0},
                    }
                ]
            }
        }
    }
    store = _FakeStore(opensearch_response)

    result = await query_token_usage_by_model(
        store,  # type: ignore[arg-type]
        user=None,  # type: ignore[arg-type]
        since=datetime(2026, 1, 1, tzinfo=timezone.utc),
        until=datetime(2026, 1, 2, tzinfo=timezone.utc),
        request=None,  # type: ignore[arg-type]
    )

    assert len(result.rows) == 1
    row = result.rows[0]
    assert row.label == "gpt-5.1"
    # 200 fresh input tokens @ 0.002/1k + 800 cached @ 0.0002/1k + 200 output @ 0.008/1k
    expected_cost = 200 / 1000 * 0.002 + 800 / 1000 * 0.0002 + 200 / 1000 * 0.008
    assert row.cost_usd == pytest.approx(expected_cost)
    # Sanity: cheaper than if every input token were billed at the full rate.
    full_rate_cost = 1000 / 1000 * 0.002 + 200 / 1000 * 0.008
    assert row.cost_usd is not None
    assert row.cost_usd < full_rate_cost
