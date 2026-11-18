// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Value shape and bounds shared by SDK FieldSpec consumers. Required/default
//! semantics and prompt trust rules belong to each admission boundary.
use crate::error::{AppError, AppResult};
use anyhow::Context;
use regex::Regex;
use serde::Deserialize;
use serde_json::Value;

// Only validation members are read here; the original FieldSpecs remain intact.
#[derive(Deserialize)]
pub(crate) struct FieldSpec {
    pub key: String,
    #[serde(rename = "type")]
    pub kind: String,
    pub r#enum: Option<Vec<String>>,
    pub min: Option<f64>,
    pub max: Option<f64>,
    pub pattern: Option<String>,
    pub item_type: Option<String>,
    #[serde(default)]
    pub required: bool,
    pub default: Option<Value>,
}

pub(crate) fn textual(kind: &str) -> bool {
    matches!(
        kind,
        "string" | "text" | "text-multiline" | "prompt" | "secret" | "url"
    )
}

fn scalar_matches(kind: &str, value: &Value) -> bool {
    match kind {
        "boolean" => value.is_boolean(),
        "integer" => value.is_i64() || value.is_u64(),
        "number" => value.is_number(),
        "select" => value.is_string(),
        kind if textual(kind) => value.is_string(),
        _ => false,
    }
}

fn scalar(value: &Value) -> bool {
    matches!(value, Value::String(_) | Value::Number(_) | Value::Bool(_))
}

pub(crate) fn validate(spec: &FieldSpec, value: &Value) -> AppResult<()> {
    let fail = |reason: &str| {
        AppError::Unprocessable(format!("Invalid value for field {:?}: {reason}.", spec.key))
    };
    let valid_type = match spec.kind.as_str() {
        "array" => value.as_array().is_some_and(|items| {
            items.iter().all(|item| {
                spec.item_type
                    .as_deref()
                    .map_or_else(|| scalar(item), |kind| scalar_matches(kind, item))
            })
        }),
        "object" => value
            .as_object()
            .is_some_and(|entries| entries.values().all(scalar)),
        kind => scalar_matches(kind, value),
    };
    if !valid_type {
        return Err(fail(
            "must match the declared type (including scalar array/object entries)",
        ));
    }
    if let Some(options) = &spec.r#enum
        && !value
            .as_str()
            .is_some_and(|text| options.iter().any(|option| option == text))
    {
        return Err(fail("must be one of the declared enum values"));
    }
    if matches!(spec.kind.as_str(), "integer" | "number") {
        let number = value.as_f64().context("invalid JSON number")?;
        if spec.min.is_some_and(|min| number < min) || spec.max.is_some_and(|max| number > max) {
            return Err(fail("must respect the declared min/max bounds"));
        }
    }
    if textual(&spec.kind) {
        let text = value.as_str().context("invalid textual tuning value")?;
        if let Some(pattern) = &spec.pattern {
            let regex = Regex::new(&format!(r"\A(?:{pattern})\z"))
                .context("invalid or unsupported runtime tuning pattern")?;
            if !regex.is_match(text) {
                return Err(fail("must match the declared pattern"));
            }
        }
    }
    Ok(())
}
