# A14. Footprint estimation reference

The [footprint chapter](07-footprint.md) explains the principle. This appendix
gives the exact calculation, its constants and their sources, and how an operator
sets the hosting of a model source. Values are those of EcoLogits 0.11.3. The
response fields that carry the estimates are described with the
[consumption analytics](A12-control-plane-api.md#consumption-analytics).

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
(in billions) and a few fixed assumptions. Fred takes EcoLogits' intermediate
values for each model and keeps them as five linear coefficients. The catalogue is
only accepted if this linear form reproduces EcoLogits to 10⁻⁹, with and without a
latency.

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

## A14.3. Coefficients per model

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

## A14.5. Catalogue changes and cost

The catalogue is part of a Control Plane release; an instance cannot change it.
Adding a model or moving to another EcoLogits release produces a new catalogue in
a new release, and every past figure follows it. An alias such as `-latest`
follows whatever EcoLogits maps it to in the release used; a new catalogue can
therefore change the model behind an alias.

Cost coefficients (`cost_per_*`) belong to the same catalogue and are currently
unpopulated, so no cost estimate is shown. USD cost uses the static
`usd_per_eur: 1.12`, a display convention copied from Swift, not a market quote.
