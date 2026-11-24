// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Estimation inputs: the catalog generated from EcoLogits by `tools/impact_factors.py`,
//! embedded at build time, and where each model source runs, declared by the instance.
//! `sessions/usage/read.sql` applies both to the journal when a figure is read.
use crate::error::AppResult;
use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashSet};
use std::sync::LazyLock;
use utoipa::ToSchema;

/// Where a model source's inference runs; it scales the energy and carbon estimates.
#[derive(Debug, Clone, PartialEq, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelFootprint {
    /// A configured `platform.model_sources` entry.
    pub source_id: String,
    /// Carbon intensity of the electricity used, in gCO2e per kWh.
    #[schema(minimum = 0.0)]
    pub grid_gco2e_per_kwh: f64,
    /// Power usage effectiveness of the datacenter, at least 1.
    #[schema(minimum = 1.0)]
    pub pue: f64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Footprint {
    grid_gco2e_per_kwh: f64,
    pue: f64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct ModelFactors {
    /// Provenance only: the EcoLogits entry and parameter counts behind the coefficients.
    ecologits: Value,
    cost_per_1k_input_tokens: f64,
    cost_per_1k_output_tokens: f64,
    cost_per_1k_cached_input_tokens: f64,
    first_token_seconds: f64,
    seconds_per_output_token: f64,
    gpu_kwh_per_output_token: f64,
    server_kw: f64,
    embodied_gco2e_per_second: f64,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Catalog {
    ecologits: String,
    usd_per_eur: f64,
    default_footprint: Footprint,
    models: BTreeMap<String, ModelFactors>,
}

fn non_negative(value: f64) -> bool {
    value.is_finite() && value >= 0.0
}

fn valid_footprint(grid: f64, pue: f64) -> bool {
    non_negative(grid) && pue.is_finite() && pue >= 1.0
}

static CATALOG: LazyLock<Result<Catalog>> = LazyLock::new(|| {
    let catalog: Catalog = serde_yaml_ng::from_str(include_str!("model_impact_factors.yaml"))?;
    ensure!(
        catalog.usd_per_eur.is_finite() && catalog.usd_per_eur > 0.0,
        "invalid display currency rate"
    );
    let default = &catalog.default_footprint;
    ensure!(
        valid_footprint(default.grid_gco2e_per_kwh, default.pue),
        "invalid default footprint"
    );
    ensure!(
        catalog.models.contains_key("default"),
        "missing default model factors"
    );
    for row in catalog.models.values() {
        ensure!(
            [
                row.cost_per_1k_input_tokens,
                row.cost_per_1k_output_tokens,
                row.cost_per_1k_cached_input_tokens,
                row.first_token_seconds,
                row.seconds_per_output_token,
                row.gpu_kwh_per_output_token,
                row.server_kw,
                row.embodied_gco2e_per_second,
            ]
            .into_iter()
            .all(non_negative),
            "invalid factor"
        );
    }
    Ok(catalog)
});

/// Every footprint names a configured source, at most once, with physical values.
pub(crate) fn validate_footprints<'a>(
    footprints: &[ModelFootprint],
    source_ids: impl Iterator<Item = &'a str> + Clone,
) -> Result<()> {
    let mut ids = HashSet::new();
    for footprint in footprints {
        ensure!(
            source_ids.clone().any(|id| id == footprint.source_id),
            "model footprint for an unknown model source"
        );
        ensure!(
            ids.insert(&footprint.source_id),
            "duplicate model footprint"
        );
        ensure!(
            valid_footprint(footprint.grid_gco2e_per_kwh, footprint.pue),
            "model footprint needs a non-negative grid intensity and a PUE of at least 1"
        );
    }
    Ok(())
}

/// The `$6` estimation parameter of `read.sql`: the catalog plus the declared footprints.
pub(crate) fn parameters(footprints: &[ModelFootprint]) -> AppResult<Value> {
    let catalog = CATALOG
        .as_ref()
        .map_err(|_| anyhow::anyhow!("invalid model impact catalog"))?;
    let declared: BTreeMap<&str, Footprint> = footprints
        .iter()
        .map(|f| {
            let footprint = Footprint {
                grid_gco2e_per_kwh: f.grid_gco2e_per_kwh,
                pue: f.pue,
            };
            (f.source_id.as_str(), footprint)
        })
        .collect();
    Ok(json!({
        "usd_per_eur": catalog.usd_per_eur,
        "models": catalog.models,
        "default_footprint": catalog.default_footprint,
        "footprints": declared,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_generated_catalog_is_valid() {
        let parameters = parameters(&[]).unwrap();
        assert!(parameters["models"]["default"]["seconds_per_output_token"].is_f64());
        assert_eq!(parameters["footprints"], json!({}));
    }

    #[test]
    fn footprints_name_configured_sources_once_with_physical_values() {
        let sources = || ["s"].into_iter();
        let footprint = |source_id: &str, pue: f64| ModelFootprint {
            source_id: source_id.into(),
            grid_gco2e_per_kwh: 35.0,
            pue,
        };
        assert!(validate_footprints(&[footprint("s", 1.16)], sources()).is_ok());
        for invalid in [
            vec![footprint("other", 1.16)],
            vec![footprint("s", 1.16), footprint("s", 1.2)],
            vec![footprint("s", 0.9)],
            vec![footprint("s", f64::NAN)],
        ] {
            assert!(validate_footprints(&invalid, sources()).is_err());
        }
        let parameters = parameters(&[footprint("s", 1.16)]).unwrap();
        assert_eq!(parameters["footprints"]["s"]["pue"], 1.16);
    }
}
