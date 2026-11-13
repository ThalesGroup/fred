// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! The Python and Rust readers consume the same maintained catalog, embedded at build time here.
//! Coefficients and their provenance remain in the YAML; no Python process or second catalog.
use crate::error::AppResult;
use serde_json::Value;
use std::sync::LazyLock;

static CATALOG: LazyLock<anyhow::Result<Value>> = LazyLock::new(|| {
    let catalog: Value = serde_yaml_ng::from_str(include_str!(
        "../../../../libs/fred-core/fred_core/kpi/model_impact_factors.yaml"
    ))?;
    anyhow::ensure!(
        catalog["usd_per_eur"]
            .as_f64()
            .is_some_and(|n| n.is_finite() && n > 0.0),
        "invalid display currency rate"
    );
    let models = catalog["models"]
        .as_object()
        .ok_or_else(|| anyhow::anyhow!("missing model factors"))?;
    anyhow::ensure!(
        models.contains_key("default"),
        "missing default model factors"
    );
    for row in models.values() {
        for value in row
            .as_object()
            .ok_or_else(|| anyhow::anyhow!("invalid factors"))?
            .values()
        {
            anyhow::ensure!(
                value.as_f64().is_some_and(|n| n.is_finite() && n >= 0.0),
                "invalid factor"
            );
        }
    }
    Ok(catalog)
});

pub(crate) fn catalog() -> AppResult<&'static Value> {
    CATALOG
        .as_ref()
        .map_err(|_| anyhow::anyhow!("invalid model impact catalog").into())
}
