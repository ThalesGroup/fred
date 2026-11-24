# /// script
# requires-python = ">=3.11"
# dependencies = ["ecologits==0.11.3"]
# ///
# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
"""Generate src/analytics/model_impact_factors.yaml from EcoLogits.

    uv run tools/impact_factors.py > src/analytics/model_impact_factors.yaml

EcoLogits models one request's inference as linear in two quantities: its
output tokens and its generation time ΔT. This tool reads EcoLogits' own
intermediate values for each model and writes the coefficients the Control
Plane's SQL applies to the consumption journal:

    ΔT    = first_token_seconds + output × seconds_per_output_token
    kWh   = (output × gpu_kwh_per_output_token + ΔT × server_kw / 3600) × pue
    gCO2e = kWh × grid_gco2e_per_kwh + ΔT × embodied_gco2e_per_second

`pue` and `grid_gco2e_per_kwh` describe where a source runs: an instance
declares them in `platform.model_footprints`. Input tokens carry no
coefficient, as in EcoLogits. Each coefficient is the central value of
EcoLogits' range; the range of the model's parameters is kept as provenance.
"""

from __future__ import annotations

import json
import math
import sys

import ecologits
from ecologits.electricity_mix_repository import electricity_mixes
from ecologits.impacts.llm import compute_llm_impacts, compute_llm_impacts_dag
from ecologits.model_repository import ParametersMoE, models
from ecologits.utils.range_value import RangeValue

# The maintained inputs: Fred's upstream model id -> its EcoLogits entry, and its
# cost rates (internal inference, no per-token billing yet: 0.0 means unknown).
# `default` estimates any model not listed and is reported as a fallback.
MODELS = {
    "default": ("mistralai", "mistral-small-latest"),
    "mistral-small-latest": ("mistralai", "mistral-small-latest"),
    "mistral-medium-latest": ("mistralai", "mistral-medium-latest"),
    "gpt-4.1-mini": ("openai", "gpt-4.1-mini"),
    "gpt-4.1": ("openai", "gpt-4.1"),
}
COST = {
    "cost_per_1k_input_tokens": 0.0,
    "cost_per_1k_output_tokens": 0.0,
    "cost_per_1k_cached_input_tokens": 0.0,
}
# Static display convention copied from Swift, not a market quote.
USD_PER_EUR = 1.12
# A source without a declared footprint: the world electricity mix and the
# industry's average PUE (Uptime Institute Global Data Center Survey 2025, 1.54).
DEFAULT_ZONE = "WOR"
DEFAULT_PUE = 1.54
# Large enough to stay within EcoLogits' fallback latency at every point used.
_PROBE = 1000.0


def central(value: float | RangeValue) -> float:
    return value.mean if isinstance(value, RangeValue) else float(value)


def parameters(provider: str, name: str) -> tuple[object, object, object]:
    model = models.find_model(provider=provider, model_name=name)
    if model is None:
        sys.exit(f"EcoLogits {ecologits.__version__} has no {provider}/{name}")
    p = model.architecture.parameters
    active, total = (p.active, p.total) if isinstance(p, ParametersMoE) else (p, p)
    deployment = model.deployment
    timing = (deployment.tps, deployment.ttft) if deployment else (None, None)
    return active, total, timing


def dag(active, total, timing, output: float) -> dict[str, object]:
    """EcoLogits' intermediate values for one request whose latency is unknown."""
    tps, ttft = timing
    return compute_llm_impacts_dag(
        model_active_parameter_count=active,
        model_total_parameter_count=total,
        output_token_count=output,
        request_latency=math.inf,
        if_electricity_mix_adpe=0,
        if_electricity_mix_pe=0,
        if_electricity_mix_gwp=0,
        if_electricity_mix_wue=0,
        datacenter_pue=1,
        datacenter_wue=0,
        tps=tps,
        ttft=ttft,
    )


def scenario(active: float, total: float, timing) -> dict[str, float]:
    """The linear coefficients of one EcoLogits scenario (fixed parameter counts)."""
    at_zero, at_probe = (
        dag(active, total, timing, 0),
        dag(active, total, timing, _PROBE),
    )
    first = float(at_zero["generation_latency"])
    latency = float(at_probe["generation_latency"])
    return {
        "first_token_seconds": first,
        "seconds_per_output_token": (latency - first) / _PROBE,
        "gpu_kwh_per_output_token": at_probe["gpu_required_count"]
        * float(at_probe["gpu_energy"])
        / _PROBE,
        "server_kw": float(at_probe["server_energy"]) * 3600 / latency,
        # kgCO2eq -> g.
        "embodied_gco2e_per_second": float(at_probe["request_embodied_gwp"])
        * 1000
        / latency,
    }


def coefficients(provider: str, name: str) -> dict[str, object]:
    """Like EcoLogits, a parameter range is two scenarios whose mean is the central value.

    The mean of each coefficient reproduces EcoLogits' central value exactly, except
    when a measured latency falls between the two scenarios' estimated durations.
    """
    active, total, timing = parameters(provider, name)
    bounds = [
        (v.min, v.max) if isinstance(v, RangeValue) else (v, v) for v in (active, total)
    ]
    scenarios = [scenario(a, t, timing) for a, t in zip(*bounds)]
    row = {
        "ecologits": {
            "provider": provider,
            "model": name,
            "active_parameters_b": _range(active),
            "total_parameters_b": _range(total),
        },
        **COST,
        **{key: sum(s[key] for s in scenarios) / 2 for key in scenarios[0]},
    }
    _check(row, active, total, timing)
    return row


def _range(value: object) -> object:
    return (
        {"min": value.min, "max": value.max} if isinstance(value, RangeValue) else value
    )


def _check(row: dict[str, object], active, total, timing) -> None:
    """The linear form must reproduce EcoLogits itself, with and without latency."""
    mix = electricity_mixes.find_electricity_mix(zone="FRA")
    for output, latency in ((1911, None), (1911, 19.6), (40, 0.5)):
        expected = compute_llm_impacts(
            model_active_parameter_count=active,
            model_total_parameter_count=total,
            output_token_count=output,
            request_latency=latency,
            if_electricity_mix_adpe=mix.adpe,
            if_electricity_mix_pe=mix.pe,
            if_electricity_mix_gwp=mix.gwp,
            if_electricity_mix_wue=mix.wue,
            datacenter_pue=1.4,
            datacenter_wue=0,
            tps=timing[0],
            ttft=timing[1],
        )
        dt = row["first_token_seconds"] + output * row["seconds_per_output_token"]
        dt = dt if latency is None else min(dt, latency)
        kwh = (
            output * row["gpu_kwh_per_output_token"] + dt * row["server_kw"] / 3600
        ) * 1.4
        grams = kwh * mix.gwp * 1000 + dt * row["embodied_gco2e_per_second"]
        for got, want in (
            (kwh, expected.energy.value),
            (grams / 1000, expected.gwp.value),
        ):
            if not math.isclose(got, central(want), rel_tol=1e-9):
                sys.exit(
                    f"{row['ecologits']}: linear form {got} != EcoLogits {central(want)}"
                )


def main() -> None:
    world = electricity_mixes.find_electricity_mix(zone=DEFAULT_ZONE)
    catalog = {
        "ecologits": ecologits.__version__,
        "usd_per_eur": USD_PER_EUR,
        "default_footprint": {
            "grid_gco2e_per_kwh": world.gwp * 1000,
            "pue": DEFAULT_PUE,
        },
        "models": {key: coefficients(*entry) for key, entry in MODELS.items()},
    }
    print(
        "# GENERATED by tools/impact_factors.py from EcoLogits; edit that tool, not this file."
    )
    print(
        "# Estimates, not measurements: the UI labels every figure derived from them."
    )
    # JSON is valid YAML: exact floats, stable order, no YAML dependency.
    print(json.dumps(catalog, indent=2))


if __name__ == "__main__":
    main()
