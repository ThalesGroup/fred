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

"""Analytics cost per model: cache reads are billed at the reduced rate, in euros."""

from __future__ import annotations

import pytest
from control_plane_backend.kpi.presets.analytics_common import model_totals
from fred_core.kpi import usd_to_eur
from fred_core.kpi.model_impact_factors import ModelImpactFactors


def test_cache_reads_are_billed_at_the_reduced_rate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: {
            "gpt-5.1": ModelImpactFactors(
                cost_per_1k_input_tokens=0.002,
                cost_per_1k_cached_input_tokens=0.0002,
                cost_per_1k_output_tokens=0.008,
            ),
            "default": ModelImpactFactors(),
        },
    )
    totals = model_totals(
        {
            "key": "gpt-5.1",
            "input": {"value": 1000.0},
            "output": {"value": 200.0},
            "cached": {"value": 800.0},
        }
    )
    # 200 fresh input tokens + 800 cached at the cache rate + 200 output tokens.
    usd = 200 / 1000 * 0.002 + 800 / 1000 * 0.0002 + 200 / 1000 * 0.008
    assert totals.cost_eur == pytest.approx(usd_to_eur(usd))
    assert totals.cached_input_tokens == 800
