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
Offline unit tests for fred_core.kpi.model_impact_factors — the green/cost
estimation layer behind the token-usage KPI presets (OBSERV-02 v3,
`KPI-ANALYTICS-RFC.md` §2.7). Known input -> known output against a fixed
config, plus the unlisted/missing-model fallback to `default`.
"""

from __future__ import annotations

import pytest
from fred_core.kpi.model_impact_factors import (
    ModelImpactFactors,
    estimate_green_cost,
    load_model_impact_factors,
)

_FACTORS = {
    "gpt-5.1": ModelImpactFactors(
        cost_per_1k_input_tokens=0.002,
        cost_per_1k_output_tokens=0.008,
        co2e_grams_per_1k_tokens=0.5,
        kwh_per_1k_tokens=0.001,
    ),
    "default": ModelImpactFactors(
        co2e_grams_per_1k_tokens=1.0,
        kwh_per_1k_tokens=0.002,
    ),
}


def _use_fixed_factors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "fred_core.kpi.model_impact_factors.load_model_impact_factors",
        lambda: _FACTORS,
    )


def test_known_model_computes_exact_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fixed_factors(monkeypatch)

    estimate = estimate_green_cost("gpt-5.1", input_tokens=2000, output_tokens=1000)

    assert estimate.cost_usd == pytest.approx(2000 / 1000 * 0.002 + 1000 / 1000 * 0.008)
    assert estimate.co2e_grams == pytest.approx(3000 / 1000 * 0.5)
    assert estimate.kwh == pytest.approx(3000 / 1000 * 0.001)


def test_unlisted_model_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fixed_factors(monkeypatch)

    estimate = estimate_green_cost(
        "some-model-not-in-the-table", input_tokens=1000, output_tokens=1000
    )

    assert estimate.co2e_grams == pytest.approx(2000 / 1000 * 1.0)
    assert estimate.kwh == pytest.approx(2000 / 1000 * 0.002)
    assert estimate.cost_usd == 0.0  # default row has no cost rates configured


def test_missing_model_name_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fixed_factors(monkeypatch)

    estimate = estimate_green_cost(None, input_tokens=1000, output_tokens=1000)

    assert estimate.co2e_grams == pytest.approx(2000 / 1000 * 1.0)
    assert estimate.kwh == pytest.approx(2000 / 1000 * 0.002)


def test_zero_tokens_yields_zero_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    _use_fixed_factors(monkeypatch)

    estimate = estimate_green_cost("gpt-5.1", input_tokens=0, output_tokens=0)

    assert estimate.co2e_grams == 0.0
    assert estimate.kwh == 0.0
    assert estimate.cost_usd == 0.0


def test_shipped_config_loads_and_has_a_default_row() -> None:
    factors = load_model_impact_factors()

    assert "default" in factors
    assert isinstance(factors["default"], ModelImpactFactors)
