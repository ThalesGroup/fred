// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Swift enrollment and partial edits over the complete saved tuning snapshot.

use std::{collections::BTreeMap, sync::OnceLock, time::Duration};

use anyhow::Context;
use axum::http::{HeaderValue, StatusCode, header};
use regex::Regex;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::{
    agents::{AgentTemplateSummary, PlatformConfig},
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

pub(super) async fn enroll(
    platform: &PlatformConfig,
    authorization: Option<&HeaderValue>,
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
    if !template.supports_capabilities
        && (!selected.is_empty()
            || body
                .capability_ids
                .as_ref()
                .is_some_and(|ids| !ids.is_empty()))
    {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "agent_capabilities_not_connected",
            "Fixed-template capabilities are not connected for agent instance creation yet.",
        ));
    }
    for (index, id) in selected.iter().enumerate() {
        if selected[..index].contains(id) {
            return Err(AppError::Unprocessable(
                "Duplicate capability selection.".into(),
            ));
        }
        if !template
            .available_capabilities
            .iter()
            .any(|entry| entry.get("id").and_then(Value::as_str) == Some(id.as_str()))
        {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capability_unavailable",
                "Selected capability is unknown or unavailable for this template.",
            ));
        }
        if id != "document_access" {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capabilities_not_connected",
                "Only document_access is connected for agent instance creation.",
            ));
        }
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
    let mut capability_config = serde_json::Map::new();
    if !selected.is_empty() {
        let config = body
            .capability_config_values
            .as_ref()
            .and_then(|values| values.get("document_access"))
            .map_or_else(|| json!({}), |values| json!(values));
        let stored = validate_document_access(platform, template, authorization, &config).await?;
        capability_config.insert("document_access".into(), stored);
    }
    object.insert("selected_capability_ids".into(), json!(selected));
    object.insert("capability_config".into(), Value::Object(capability_config));
    Ok(tuning)
}

async fn validate_document_access(
    platform: &PlatformConfig,
    template: &AgentTemplateSummary,
    authorization: Option<&HeaderValue>,
    config: &Value,
) -> AppResult<Value> {
    let unavailable = || AppError::Unavailable("Pod capability validation unavailable.".into());
    let source = platform
        .runtime_catalog_sources
        .iter()
        .find(|source| source.enabled && source.runtime_id == template.source_runtime_id)
        .ok_or_else(unavailable)?;
    static CLIENT: OnceLock<Result<reqwest::Client, reqwest::Error>> = OnceLock::new();
    let client = CLIENT
        .get_or_init(|| {
            reqwest::Client::builder()
                .timeout(Duration::from_secs(10))
                .redirect(reqwest::redirect::Policy::none())
                .build()
        })
        .as_ref()
        .map_err(|_| unavailable())?;
    // No assets or team_id alias: document_access validation only normalizes config.
    let mut request = client
        .post(format!(
            "{}/agents/capabilities/document_access/validate-config",
            source.base_url.trim_end_matches('/')
        ))
        .form(&[("config", config.to_string())]);
    if let Some(authorization) = authorization {
        let mut authorization = authorization.clone();
        authorization.set_sensitive(true);
        request = request.header(header::AUTHORIZATION, authorization);
    }
    let mut response = request.send().await.map_err(|_| unavailable())?;
    match response.status() {
        StatusCode::OK => {}
        StatusCode::UNAUTHORIZED | StatusCode::FORBIDDEN => return Err(AppError::Forbidden),
        StatusCode::NOT_FOUND => {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capability_unavailable",
                "document_access is unavailable on the template's pod.",
            ));
        }
        StatusCode::UNPROCESSABLE_ENTITY => {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capability_config_invalid",
                "The pod rejected the document_access configuration.",
            ));
        }
        _ => return Err(unavailable()),
    }
    // Bound the response and validate only the envelope; Python owns its config schema.
    const MAX_BYTES: usize = 2 * 1024 * 1024;
    if response
        .content_length()
        .is_some_and(|size| size > MAX_BYTES as u64)
    {
        return Err(unavailable());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.map_err(|_| unavailable())? {
        if bytes.len() + chunk.len() > MAX_BYTES {
            return Err(unavailable());
        }
        bytes.extend_from_slice(&chunk);
    }
    let stored: Value = serde_json::from_slice(&bytes).map_err(|_| unavailable())?;
    if !stored
        .get("schema_version")
        .and_then(Value::as_str)
        .is_some_and(|v| !v.is_empty())
        || !stored.get("config").is_some_and(Value::is_object)
    {
        return Err(unavailable());
    }
    let config = &stored["config"];
    if config.get("attachments").and_then(Value::as_bool) != Some(false)
        || config.get("team_documents").and_then(Value::as_bool) != Some(true)
    {
        return Err(AppError::problem(
            StatusCode::UNPROCESSABLE_ENTITY,
            "document_access_corpus_only",
            "document_access creation requires team_documents=true and attachments=false.",
        ));
    }
    Ok(stored)
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
