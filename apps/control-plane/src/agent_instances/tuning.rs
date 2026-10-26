// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Swift enrollment and partial edits over the complete saved tuning snapshot.

use std::collections::BTreeMap;

use anyhow::Context;
use axum::http::StatusCode;
use regex::Regex;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::{
    agents::AgentTemplateSummary,
    error::{AppError, AppResult},
};

use super::{
    AgentInstance,
    http::{
        AgentInstanceStatus, CreateAgentInstanceRequest, TuningValue, UpdateAgentInstanceRequest,
    },
};

pub(super) fn validate_request(body: &mut CreateAgentInstanceRequest) -> AppResult<()> {
    validate_metadata(
        Some(&mut body.display_name),
        body.description.as_deref(),
        body.role.as_deref(),
        Some(&body.usage_statement),
    )?;
    if let Some(options) = &body.model_options {
        options.validate()?;
    }
    Ok(())
}

pub(super) fn validate_update_request(body: &mut UpdateAgentInstanceRequest) -> AppResult<()> {
    validate_metadata(
        body.display_name.as_mut(),
        body.description.as_deref(),
        body.role.as_deref(),
        body.usage_statement.as_deref(),
    )?;
    if let Some(Some(options)) = &body.model_options {
        options.validate()?;
    }
    if matches!(&body.recommended_chat_profile_id, Some(Some(_))) {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "legacy_model_reselection_required",
            "Legacy profiles are diagnostic references only; re-select using recommended_model.",
        ));
    }
    Ok(())
}

fn validate_metadata(
    display_name: Option<&mut String>,
    description: Option<&str>,
    role: Option<&str>,
    usage_statement: Option<&str>,
) -> AppResult<()> {
    if let Some(name) = display_name {
        *name = name.trim().to_owned();
        if !(1..=255).contains(&name.chars().count()) {
            return Err(AppError::Unprocessable(
                "display_name must contain 1..255 characters".into(),
            ));
        }
    }
    if description.is_some_and(|s| s.chars().count() > 500) {
        return Err(AppError::Unprocessable(
            "description must contain at most 500 characters".into(),
        ));
    }
    if role.is_some_and(|s| !(1..=255).contains(&s.chars().count())) {
        return Err(AppError::Unprocessable(
            "role must contain 1..255 characters".into(),
        ));
    }
    if usage_statement.is_some_and(str::is_empty) {
        return Err(AppError::Unprocessable(
            "usage_statement must not be empty".into(),
        ));
    }
    Ok(())
}

pub(super) fn enroll(
    mut tuning: Value,
    template: &AgentTemplateSummary,
    body: &CreateAgentInstanceRequest,
) -> AppResult<Value> {
    // Fixed-capability templates always require their defaults, even with [].
    let selected = if template.supports_capabilities {
        body.capability_ids
            .as_deref()
            .unwrap_or(&template.default_capability_ids)
    } else {
        &template.default_capability_ids
    };
    if !selected.is_empty()
        || body
            .capability_ids
            .as_ref()
            .is_some_and(|ids| !ids.is_empty())
    {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "agent_capabilities_not_connected",
            "Active capabilities are not connected for agent instance creation yet.",
        ));
    }
    if body.recommended_chat_profile_id.is_some() {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "legacy_model_reselection_required",
            "Legacy profiles cannot be selected; use recommended_model with an offer key.",
        ));
    }
    let object = tuning
        .as_object_mut()
        .context("runtime default_tuning must be an object")?;
    object.insert(
        "role".into(),
        json!(body.role.as_ref().unwrap_or(&body.display_name)),
    );
    object.insert(
        "description".into(),
        json!(
            body.description
                .as_ref()
                .filter(|value| !value.is_empty())
                .unwrap_or(&body.display_name)
        ),
    );
    object.insert("usage_statement".into(), json!(body.usage_statement));
    object.insert("recommended_chat_profile_id".into(), Value::Null);
    object.insert("recommended_model".into(), json!(body.recommended_model));
    object.insert(
        "model_options".into(),
        json!(body.model_options.clone().unwrap_or_default()),
    );
    if let Some(values) = body.tuning_field_values.as_ref().filter(|v| !v.is_empty()) {
        let fields: Vec<FieldSpec> =
            serde_json::from_value(object.get("fields").cloned().unwrap_or_else(|| json!([])))
                .context("invalid runtime tuning fields")?;
        object.insert("values".into(), json!(validate_values(fields, values)?));
    }
    // Swift materializes the effective selection and discards unselected config.
    object.insert("selected_capability_ids".into(), json!([]));
    object.insert("capability_config".into(), json!({}));
    Ok(tuning)
}

pub(super) fn apply_update(
    record: &mut AgentInstance,
    body: &UpdateAgentInstanceRequest,
    template: Option<&AgentTemplateSummary>,
) -> AppResult<()> {
    let object = record
        .tuning
        .0
        .as_object_mut()
        .context("invalid saved agent tuning")?;
    if let Some(template) = template {
        object.insert("fields".into(), json!(template.default_tuning_fields));
    }
    if let Some(values) = &body.tuning_field_values {
        let values = match values {
            None => BTreeMap::new(),
            Some(values) => {
                let fields: Vec<FieldSpec> = serde_json::from_value(
                    object.get("fields").cloned().unwrap_or_else(|| json!([])),
                )
                .context("invalid agent tuning fields")?;
                validate_values(fields, values)?
            }
        };
        object.insert("values".into(), json!(values));
    }
    if body.capability_ids.is_some() || body.capability_config_values.is_some() {
        let template = template.context("capability edit requires current template")?;
        let saved_selection = object
            .get("selected_capability_ids")
            .cloned()
            .unwrap_or(Value::Null);
        let saved_ids: Option<Vec<String>> = serde_json::from_value(saved_selection.clone())
            .context("invalid saved capability selection")?;
        let requested_ids = body.capability_ids.as_ref().unwrap_or(&saved_ids);
        let selected = if template.supports_capabilities {
            requested_ids
                .as_deref()
                .unwrap_or(&template.default_capability_ids)
        } else {
            &template.default_capability_ids
        };
        if !selected.is_empty() || requested_ids.as_ref().is_some_and(|ids| !ids.is_empty()) {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capabilities_not_connected",
                "Active capabilities are not connected for agent instance editing yet.",
            ));
        }
        let selection_changed = body.capability_ids.is_some() && saved_selection != json!([]);
        if body.capability_ids.is_some() {
            object.insert("selected_capability_ids".into(), json!([]));
        }
        if selection_changed || body.capability_config_values.is_some() {
            // No active capabilities: ignore submitted values for unselected IDs.
            object.insert("capability_config".into(), json!({}));
        }
    }
    if let Some(role) = &body.role {
        object.insert("role".into(), json!(role));
    }
    if let Some(usage_statement) = &body.usage_statement {
        object.insert("usage_statement".into(), json!(usage_statement));
    }
    if matches!(&body.recommended_chat_profile_id, Some(None)) {
        object.insert("recommended_chat_profile_id".into(), Value::Null);
    }
    if let Some(recommendation) = &body.recommended_model {
        object.insert("recommended_model".into(), json!(recommendation));
    }
    if let Some(options) = &body.model_options {
        object.insert(
            "model_options".into(),
            json!(options.clone().unwrap_or_default()),
        );
    }
    if let Some(name) = &body.display_name {
        record.display_name.clone_from(name);
    }
    if let Some(description) = &body.description {
        record.description = Some(description.clone());
    }
    if let Some(status) = &body.status {
        record.enabled = matches!(status, AgentInstanceStatus::Enabled);
    }
    Ok(())
}

// Only validation members are read here; the original FieldSpecs remain intact.
#[derive(Deserialize)]
struct FieldSpec {
    key: String,
    #[serde(rename = "type")]
    kind: String,
    r#enum: Option<Vec<String>>,
    min: Option<f64>,
    max: Option<f64>,
    pattern: Option<String>,
    item_type: Option<String>,
}

fn textual(kind: &str) -> bool {
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

fn validate_values(
    fields: Vec<FieldSpec>,
    submitted: &BTreeMap<String, TuningValue>,
) -> AppResult<BTreeMap<String, Value>> {
    // Mirror prompt_utils.py, including Python's Unicode I-folding and whitespace.
    let reserved = Regex::new(concat!(
        r"(?i)<[\s\x1c-\x1f]*/?[\s\x1c-\x1f]*(",
        r"platform_[i\u0130\u0131]nstruct[i\u0130\u0131]ons|platform_prompt|tools|",
        r"agent_[i\u0130\u0131]nstruct[i\u0130\u0131]ons)(?:[\s\x1c-\x1f/][^>]*|)>"
    ))
    .context("invalid reserved prompt tag expression")?;
    let by_key: BTreeMap<_, _> = fields
        .into_iter()
        .map(|field| (field.key.clone(), field))
        .collect();
    let mut values = BTreeMap::new();
    for (key, spec) in by_key {
        // Required/default/UI hints are form rules, not obligations on a partial save.
        let Some(value) = submitted.get(&key) else {
            continue;
        };
        let value = serde_json::to_value(value).context("invalid tuning field value")?;
        let fail = |reason: &str| {
            AppError::Unprocessable(format!("Invalid value for tuning field {key:?}: {reason}."))
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
            kind => scalar_matches(kind, &value),
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
            if spec.min.is_some_and(|min| number < min) || spec.max.is_some_and(|max| number > max)
            {
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
            if reserved.is_match(text) {
                return Err(fail("reserved system-prompt tags are not allowed"));
            }
        }
        values.insert(key, value);
    }
    Ok(values)
}
