# Environmental footprint estimation (CO2e / kWh)

**Status:** Draft — open item, 2026-08-26. The estimation *mechanism* is shipped
(see "Current state"); this RFC is scoped only to the **open question of factor
accuracy**: the per-model impact factors are rough estimates and must be refined
before the "IA responsable" footprint figures can be treated as anything better
than order-of-magnitude. Tracked in [GitHub issue #2430](https://github.com/ThalesGroup/fred/issues/2430).

## 1. Problem statement

The home dashboard "IA responsable" section and the analytics token-usage widgets
show an **estimated** CO2e / kWh footprint for a user's (or the platform's) LLM
consumption. The numbers are derived by multiplying token counts by a static,
hand-maintained per-model factor table
([`libs/fred-core/fred_core/kpi/model_impact_factors.yaml`](../../../libs/fred-core/fred_core/kpi/model_impact_factors.yaml),
consumed by `estimate_green_cost`):

```
co2e_g = tokens / 1000 * co2e_grams_per_1k_tokens
kwh    = tokens / 1000 * kwh_per_1k_tokens
```

The table shipped empty (every factor `0.0` = "not populated yet"), so the widget
read `≈ 0` for everyone. It has since been seeded with **estimates** for the
models actually in use, but those estimates carry large, explicitly-acknowledged
uncertainty. The file's own header already warns the figures are "NOT
billing-grade or measurement-grade" and must be labelled "estimated" in the UI.

## 2. Current state (shipped, for context — not the subject of this RFC)

Factors seeded for the `model_name` values actually recorded in `dims.model_name`
(confirmed against the live KPI store):

| Model | Key (`model_name`) | Size | co2e (g/1k tok) | kWh/1k tok | Confidence |
| --- | --- | --- | --- | --- | --- |
| Mistral Small 3.x | `mistral-small-latest` | 24B | 0.6 | 0.003 | co2e fair · kWh weak |
| Mistral Medium 3.x | `mistral-medium-latest` | undisclosed (~60B assumed) | 1.5 | 0.0075 | weak (size unknown) |
| fallback | `default` | — | 0.6 | 0.003 | weak |

Derivation anchor: **Mistral's own life-cycle analysis of Mistral Large 2**
(Carbone 4 / ADEME, 2025) — 1.14 gCO2e per 400-token request ≈ 2.85 gCO2e / 1k
tokens for a ~123B model, with the report's stated ~linear scaling with size.
Small = anchor × 24/123 ≈ 0.6. Medium ≈ 2.5 × Small (undisclosed size). kWh has
**no first-party source** and third-party estimates for a ~24B model span
~0.02–1.4 Wh / 400 tokens (≈ two orders of magnitude), so the kWh figures are the
softest. A **France low-carbon grid** is assumed for the CO2e.

## 3. What must be refined (the open question)

Before these figures are presented as more than order-of-magnitude, we need:

1. **Real infrastructure carbon intensity + PUE.** CO2e is `energy × grid
   intensity + embodied`. Inference runs on the company's own internal
   datacenter (France), for which we do **not yet** have the grid factor or PUE.
   Once known, recompute the CO2e factors from operational energy × that grid
   rather than inheriting Mistral's LCA blend.
2. **Official / estimated parameter counts**, especially **Mistral Medium**
   (undisclosed) — the size-scaling is the biggest lever on the Medium factor.
3. **First-party per-token energy (kWh).** None is published for these models;
   the current kWh values are mid-range guesses. A measured Wh/token on the
   actual serving stack (GPU type, batch size, quantization) would replace them.
4. **Per-region intensity** if inference ever spans locations (currently single
   France assumption).
5. **Cost factors** are left `0.0` (internal infra, no per-token billing); revisit
   if a chargeback model appears.

## 4. Proposed approach

- Keep `model_impact_factors.yaml` as the single source of truth for v1 — it is
  hot-editable config, no code change, one backend restart to reload (factors are
  process-cached via `load_model_impact_factors`).
- Refine the values incrementally as the data in §3 arrives; add a row per new
  `model_name` that appears in the KPI store (unlisted models fall back to
  `default` and silently under/over-count until listed).
- Keep the UI labelling every figure "estimated" (already done — the footprint
  tile shows "≈" and links a methodology dialog).
- **Alternative to evaluate:** replace the hand-maintained table with a
  methodology library such as **EcoLogits / GenAI Impact**, which estimates
  energy + CO2e from model metadata and a configurable grid intensity. Trade-off:
  removes hand-maintenance and gives a defensible methodology, but adds a
  dependency and its own assumptions, and still needs the real grid factor. Not
  adopted yet — flagged for a future decision.

## 5. Impact on existing contracts

None. This is data-only config behind the existing `estimate_green_cost`
contract and the `TimeSeriesResponse.co2e_grams` / `.kwh` fields already exposed
by the token-usage presets. Refining the numbers changes displayed values, not
shapes or endpoints.

## 6. Out of scope

- The estimation mechanism itself (shipped) — durable "what/why" lives with the
  code and the token-usage presets, not here.
- Per-step (per-message) footprint attribution — see
  `TRACE-TOKEN-USAGE-RFC.md` §5, deliberately out of scope there too.
