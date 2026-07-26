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
Green/cost estimation for LLM token consumption (OBSERV-02 v3,
`KPI-ANALYTICS-RFC.md` §2.7).

A single static, hand-maintained table (`model_impact_factors.yaml`, keyed by
`model_name` — the same key `agent.turn_completed` already emits) drives both
the carbon/electricity estimate (shown everywhere token usage is shown, not
optional) and the $ cost estimate (secondary, collapsible). Figures are
estimates, not billing-grade or measurement-grade — callers must label them
accordingly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

_FACTORS_YAML_PATH = Path(__file__).with_name("model_impact_factors.yaml")

_DEFAULT_KEY = "default"


class ModelImpactFactors(BaseModel):
    cost_per_1k_input_tokens: float = 0.0
    cost_per_1k_output_tokens: float = 0.0
    co2e_grams_per_1k_tokens: float = 0.0
    kwh_per_1k_tokens: float = 0.0


class GreenCostEstimate(BaseModel):
    co2e_grams: float
    kwh: float
    cost_usd: float


@lru_cache(maxsize=1)
def load_model_impact_factors() -> dict[str, ModelImpactFactors]:
    """Load and cache `model_impact_factors.yaml`.

    Cached for process lifetime — this is dev-edited static config (§2.7),
    not something that changes at runtime.
    """
    raw = yaml.safe_load(_FACTORS_YAML_PATH.read_text(encoding="utf-8"))
    models = raw.get("models", {}) if raw else {}
    factors = {name: ModelImpactFactors(**row) for name, row in models.items()}
    factors.setdefault(_DEFAULT_KEY, ModelImpactFactors())
    return factors


def estimate_green_cost(
    model_name: str | None, *, input_tokens: float, output_tokens: float
) -> GreenCostEstimate:
    """Estimate CO2e/kWh/$ for a slice of token usage attributed to one model.

    Falls back to the `default` row for any `model_name` not in the config,
    including turns with no recorded model name at all.
    """
    factors_by_model = load_model_impact_factors()
    factors = factors_by_model.get(model_name or "", factors_by_model[_DEFAULT_KEY])
    total_tokens = input_tokens + output_tokens
    return GreenCostEstimate(
        co2e_grams=total_tokens / 1000 * factors.co2e_grams_per_1k_tokens,
        kwh=total_tokens / 1000 * factors.kwh_per_1k_tokens,
        cost_usd=(
            input_tokens / 1000 * factors.cost_per_1k_input_tokens
            + output_tokens / 1000 * factors.cost_per_1k_output_tokens
        ),
    )
