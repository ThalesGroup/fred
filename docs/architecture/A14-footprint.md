# A14. Footprint estimation reference

The [footprint chapter](07-footprint.md) explains the principle. This appendix
gives the exact calculation, its constants and their sources, and how to set and
maintain them. Values are those of EcoLogits 0.11.3.

| Element | Location |
| --- | --- |
| Generator and its inputs | [`tools/impact_factors.py`](../../apps/control-plane/tools/impact_factors.py) |
| Generated catalogue, built into Control Plane | [`src/analytics/model_impact_factors.yaml`](../../apps/control-plane/src/analytics/model_impact_factors.yaml) |
| Catalogue validation and hosting declarations | [`src/analytics/factors.rs`](../../apps/control-plane/src/analytics/factors.rs) |
| Calculation on the journal | [`src/sessions/usage/read.sql`](../../apps/control-plane/src/sessions/usage/read.sql) |
| Response fields `estimates`, `coverage`, `fallback` | [Consumption analytics](A12-control-plane-api.md#consumption-analytics) |

## A14.1. Calculation

Each journal row is one report of one run for one model. For a row of `output`
tokens:

```text
ΔT    = first_token_seconds + output × seconds_per_output_token              (s)
kWh   = (output × gpu_kwh_per_output_token + ΔT × server_kw / 3600) × pue
gCO2e = kWh × grid_gco2e_per_kwh + ΔT × embodied_gco2e_per_second
```

A figure is the sum of its rows, in PostgreSQL numeric arithmetic, over every
report of the period, before rankings are truncated. Input tokens, cached or not,
take no part. A row without any token is a calculated zero. A row whose model has
a missing or zero required coefficient is unavailable: the sum then reports
`coverage: partial` or `unavailable`, never a zero for the missing part.

The five model coefficients come from the catalogue, looked up by
`upstream_model_id`, or from its `default` entry, flagged `fallback`. `pue` and
`grid_gco2e_per_kwh` come from the row's `model_source_id` in
`platform.model_footprints`, or from the catalogue's `default_footprint`, also
flagged `fallback`.

## A14.2. Where the coefficients come from

EcoLogits models one request from the model's active and total parameter counts
(in billions) and a few fixed assumptions. The generator reads EcoLogits'
intermediate values and writes them as five linear coefficients. It then checks
that the linear form reproduces EcoLogits to 10⁻⁹, with and without a latency.

| EcoLogits element | Value | Becomes |
| --- | --- | --- |
| GPU energy per output token | `(1.1665e-6 × e^(−0.0112 × 64) × P_active + 4.053e-5) / 1000` kWh, per GPU | `gpu_kwh_per_output_token`, times the GPU count |
| Generation time per output token | `6.785e-4 × P_active + 3.119e-4 × 64 + 0.01947` s, or `1 / tps` when the model's throughput is published | `seconds_per_output_token` |
| Time to first token | the model's published `ttft`, otherwise 0 | `first_token_seconds` |
| GPU count | memory `1.2 × P_total × 16 / 8` GB over 80 GB H100s, rounded up to a power of two | used in the three coefficients below |
| Server power without GPUs | 1.2 kW for 8 GPUs, shared by a batch of 64 | `server_kw = 1.2 × GPUs / 8 / 64` |
| Manufacturing | 5,700 kgCO2e per server without GPUs, 273 kgCO2e per H100, over 3 years, shared by a batch of 64 | `embodied_gco2e_per_second` |

A parameter range, for a model whose size is not published, is two EcoLogits
scenarios: the minimum and the maximum. Each coefficient is their mean, as
EcoLogits' central value.

## A14.3. Generated coefficients

| Fred model | EcoLogits entry | Parameters (B) active / total | s per output token | First token (s) | GPU kWh per output token | Server kW | Embodied gCO2e per s |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `default` | mistralai/mistral-small-latest | 8 / 119 | 0.0449 | 0 | 1.80e-7 | 0.0094 | 0.00065 |
| `mistral-small-latest` | mistralai/mistral-small-latest | 8 / 119 | 0.0449 | 0 | 1.80e-7 | 0.0094 | 0.00065 |
| `mistral-medium-latest` | mistralai/mistral-medium-latest | 70–120 | 0.1039 | 0 | 3.78e-7 | 0.0094 | 0.00065 |
| `gpt-4.1-mini` | openai/gpt-4.1-mini | 40–112 | 0.0127 | 0.93 | 2.72e-7 | 0.0070 | 0.00049 |
| `gpt-4.1` | openai/gpt-4.1 | 35–106 / 352 | 0.0123 | 1.02 | 1.29e-6 | 0.0375 | 0.0026 |

The catalogue file holds the exact values and their provenance.

**Worked example.** A RAG turn on `mistral-medium-latest` generated 1,911 output
tokens. Its source, Mistral's API, is declared with 35.26 gCO2e/kWh and a PUE of
1.16.

```text
ΔT    = 0 + 1,911 × 0.1039                                   = 198.5 s
kWh   = (1,911 × 3.785e-7 + 198.5 × 0.009375 / 3600) × 1.16  = 0.00144 kWh
gCO2e = 0.00144 × 35.26 + 198.5 × 0.000651                   = 0.051 + 0.129 = 0.180 g
```

The same turn had 161,949 input tokens; they do not change the result. Its
measured generation time was 19.6 s, ten times less than the estimate: see the
limits in the [chapter](07-footprint.md#76-limits).

## A14.4. Hosting a model source

An instance declares the hosting of each model source it configures:

```yaml
platform:
  model_footprints:
  - source_id: mistral          # a platform.model_sources entry
    grid_gco2e_per_kwh: 35.26   # carbon intensity of the electricity, ≥ 0
    pue: 1.16                   # datacenter power usage effectiveness, ≥ 1
```

Control Plane refuses a footprint for an unknown source, a duplicate, a negative
intensity or a PUE below 1. A change applies to every past figure of that source.
A source must keep its footprint as long as its history matters. Removing a source
from `model_sources` requires removing its footprint too, and its history is then
estimated with the default.

| Deployment | `grid_gco2e_per_kwh` | `pue` |
| --- | --- | --- |
| Provider API (Mistral, OpenAI, Google, Anthropic) | The provider's assumed country in EcoLogits: Sweden for Mistral, the USA for the others | EcoLogits' provider value: Mistral 1.16, OpenAI 1.20, Google 1.09, Anthropic 1.09–1.14 |
| Model deployed in a cloud project (Google Cloud, another cloud) | The intensity the provider publishes for the region, or the country's mix | The PUE the provider publishes for its fleet or region |
| Model hosted on premises | The country's mix, or the supplier's contract figure. In France, ADEME's Base Empreinte gives the national factor | The datacenter's measured annual PUE, from the infrastructure team |
| Unknown | Do not declare: the default applies and is flagged | Do not declare |

Country mixes in EcoLogits 0.11.3, in gCO2e/kWh: Sweden 35.26, France 41.44,
Finland 57.47, Belgium 149.82, Netherlands 253.56, Ireland 256.54, Germany 329.65,
USA 384.4, world 458.29. The default footprint is the world mix with a PUE of 1.54,
the industry average of the Uptime Institute Global Data Center Survey 2025.

The hosting covers electricity and the building only. GPU type, quantization and
load stay those of EcoLogits, even for a self-hosted model.

## A14.5. Maintaining the catalogue

| Change | Procedure |
| --- | --- |
| Add a model, or map one to another EcoLogits entry | Edit `MODELS` in the generator |
| Move to a new EcoLogits release | Change the pinned version in the generator's header |
| Change the default hosting | Edit `DEFAULT_ZONE` or `DEFAULT_PUE` in the generator |

Then regenerate the catalogue and release Control Plane:

```sh
cd apps/control-plane
uv run tools/impact_factors.py > src/analytics/model_impact_factors.yaml
```

The generator stops if EcoLogits does not know a model, or if its coefficients
no longer reproduce EcoLogits. Running it again without a change produces the same
file. An alias such as `-latest` follows whatever EcoLogits maps it to in that
release; a regeneration can change it.

Cost coefficients (`cost_per_*`) are maintained in the same generator and are
currently unpopulated, so no cost estimate is shown. USD cost uses the static
`usd_per_eur: 1.12`, a display convention copied from Swift, not a market quote.

## A14.6. Evidence

| Check | Where |
| --- | --- |
| Linear form equals EcoLogits, for every model | The generator's own check, run at each generation |
| Catalogue validation and hosting rules | `analytics::factors` unit tests |
| Output and time only, declared and default hosting, fallback, zero-carbon grid, unavailable coefficients | `analytics_impact_follows_output_generation_time_and_declared_footprints` (integration) |
| Cost and partial coverage | `analytics_estimation_sql_exercises_cache_currency_and_partial_factors` (integration) |
| Same estimate across organizations, whatever the input | `personal_analytics_never_combines_acme_and_globex_and_requires_current_organization_access` (integration) |
