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
    # Billed at this reduced rate instead of cost_per_1k_input_tokens — a
    # provider cache hit costs less than a fresh input token (CACHE-01).
    # No distinct co2e/kwh-per-cached-token rate yet: not reliably documented
    # by providers (docs/swift/rfc/PROMPT-CACHE-TOKEN-VISIBILITY-RFC.md §5).
    cost_per_1k_cached_input_tokens: float = 0.0
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
    model_name: str | None,
    *,
    input_tokens: float,
    output_tokens: float,
    cache_read_tokens: float = 0.0,
) -> GreenCostEstimate:
    """Estimate CO2e/kWh/$ for a slice of token usage attributed to one model.

    Falls back to the `default` row for any `model_name` not in the config,
    including turns with no recorded model name at all.

    `cache_read_tokens` is the portion of `input_tokens` served from a
    provider-side prompt cache (CACHE-01) — a subset of `input_tokens`, not
    additional tokens on top of it — billed at
    `cost_per_1k_cached_input_tokens` instead of the full input rate.
    Clamped to `input_tokens`: a caller reporting more cache hits than input
    tokens indicates a data bug upstream, not a negative bill. Defaults to
    `0.0`, reproducing the pre-CACHE-01 formula exactly for any caller that
    doesn't pass it.
    """
    factors_by_model = load_model_impact_factors()
    factors = factors_by_model.get(model_name or "", factors_by_model[_DEFAULT_KEY])
    total_tokens = input_tokens + output_tokens
    cached_input_tokens = min(max(cache_read_tokens, 0.0), input_tokens)
    fresh_input_tokens = input_tokens - cached_input_tokens
    return GreenCostEstimate(
        co2e_grams=total_tokens / 1000 * factors.co2e_grams_per_1k_tokens,
        kwh=total_tokens / 1000 * factors.kwh_per_1k_tokens,
        cost_usd=(
            fresh_input_tokens / 1000 * factors.cost_per_1k_input_tokens
            + cached_input_tokens / 1000 * factors.cost_per_1k_cached_input_tokens
            + output_tokens / 1000 * factors.cost_per_1k_output_tokens
        ),
    )
