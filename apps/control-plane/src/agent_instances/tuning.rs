// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Swift enrollment and partial edits over the complete saved tuning snapshot.

use std::{
    borrow::Cow,
    collections::{BTreeMap, BTreeSet},
    sync::OnceLock,
    time::Duration,
};

use anyhow::Context;
use axum::http::{HeaderValue, StatusCode, header};
use regex::Regex;
use serde::Deserialize;
use serde_json::{Value, json};

use crate::{
    agents::{AgentTemplateSummary, PlatformConfig, enablement},
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
    usable: &BTreeSet<String>,
    body: &CreateAgentInstanceRequest,
) -> AppResult<Value> {
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
    let (selected, capability_config) = select_capabilities(
        platform,
        authorization,
        template,
        usable,
        body.capability_ids.as_deref(),
        |id| {
            body.capability_config_values
                .as_ref()
                .and_then(|values| values.get(id))
                .map_or_else(|| json!({}), |values| json!(values))
        },
    )
    .await?;
    object.insert("selected_capability_ids".into(), json!(selected));
    object.insert("capability_config".into(), Value::Object(capability_config));
    Ok(tuning)
}

/// A capability edit validated by the pod before the lock, with the saved
/// selection and config it was derived from.
pub(super) struct CapabilityUpdate {
    basis: [Option<Value>; 2],
    selected: Vec<String>,
    config: serde_json::Map<String, Value>,
}

fn capability_basis(tuning: &Value) -> [Option<Value>; 2] {
    ["selected_capability_ids", "capability_config"].map(|key| tuning.get(key).cloned())
}

pub(super) async fn validate_capability_update(
    platform: &PlatformConfig,
    authorization: Option<&HeaderValue>,
    template: &AgentTemplateSummary,
    usable: &BTreeSet<String>,
    saved: &Value,
    body: &UpdateAgentInstanceRequest,
) -> AppResult<CapabilityUpdate> {
    let saved_ids: Option<Vec<String>> = serde_json::from_value(
        saved
            .get("selected_capability_ids")
            .cloned()
            .unwrap_or(Value::Null),
    )
    .context("invalid saved capability selection")?;
    let requested = match &body.capability_ids {
        Some(ids) => ids.as_deref(),
        None => saved_ids.as_deref(),
    };
    // Swift: submitted values, else defaults on reset, else the saved config.
    let (selected, config) = select_capabilities(
        platform,
        authorization,
        template,
        usable,
        requested,
        |id| match &body.capability_config_values {
            Some(Some(values)) if values.contains_key(id) => json!(values[id]),
            Some(None) => json!({}),
            _ => saved["capability_config"][id]
                .get("config")
                .cloned()
                .unwrap_or_else(|| json!({})),
        },
    )
    .await?;
    Ok(CapabilityUpdate {
        basis: capability_basis(saved),
        selected,
        config,
    })
}

/// Swift materializes the effective selection, stores each pod-returned
/// envelope and discards configuration of unselected capabilities.
async fn select_capabilities(
    platform: &PlatformConfig,
    authorization: Option<&HeaderValue>,
    template: &AgentTemplateSummary,
    usable: &BTreeSet<String>,
    requested: Option<&[String]>,
    config_for: impl Fn(&str) -> Value,
) -> AppResult<(Vec<String>, serde_json::Map<String, Value>)> {
    // A fixed template ignores the submitted selection; its defaults are validated alike.
    let selected = match requested {
        Some(ids) if template.supports_capabilities => ids,
        _ => &template.default_capability_ids,
    };
    for (index, id) in selected.iter().enumerate() {
        if selected[..index].contains(id) {
            return Err(AppError::Unprocessable(
                "Duplicate capability selection.".into(),
            ));
        }
    }
    require_inventory(template, selected)?;
    // Organization authorization, checked before any pod validation.
    if let Some(id) = selected.iter().find(|id| !usable.contains(*id)) {
        return Err(enablement::not_enabled(id));
    }
    let envelopes = futures::future::try_join_all(selected.iter().map(|id| {
        let config = config_for(id);
        validate_capability(platform, template, authorization, id, config)
    }))
    .await?;
    Ok((
        selected.to_vec(),
        selected.iter().cloned().zip(envelopes).collect(),
    ))
}

/// The effective selection: enrollment always stores it, so absence is corrupt data.
pub(super) fn saved_selection(tuning: &Value) -> AppResult<Vec<String>> {
    Ok(Vec::<String>::deserialize(
        tuning
            .get("selected_capability_ids")
            .unwrap_or(&Value::Null),
    )
    .context("invalid saved capability selection")?)
}

/// Every selected capability must belong to the template's pod inventory.
pub(super) fn require_inventory(
    template: &AgentTemplateSummary,
    selected: &[String],
) -> AppResult<()> {
    for id in selected {
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
    }
    Ok(())
}

async fn validate_capability(
    platform: &PlatformConfig,
    template: &AgentTemplateSummary,
    authorization: Option<&HeaderValue>,
    id: &str,
    config: Value,
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
    // Weaver sends neither assets nor a team_id alias: the pod validates config alone.
    let mut request = client
        .post(format!(
            "{}/agents/capabilities/{id}/validate-config",
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
                "The capability is unavailable on the template's pod.",
            ));
        }
        StatusCode::UNPROCESSABLE_ENTITY => {
            // The capability owns the rule, so its reason is what the person can act on.
            let detail = read_limited(&mut response, 16 * 1024)
                .await
                .and_then(|bytes| rejection_detail(&bytes))
                .map_or(
                    Cow::Borrowed("The pod rejected the capability configuration."),
                    Cow::Owned,
                );
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "agent_capability_config_invalid",
                detail,
            ));
        }
        _ => return Err(unavailable()),
    }
    // Bound the response and validate only the envelope; the pod owns the config schema.
    let bytes = read_limited(&mut response, 2 * 1024 * 1024)
        .await
        .ok_or_else(unavailable)?;
    let stored: Value = serde_json::from_slice(&bytes).map_err(|_| unavailable())?;
    if !stored
        .get("schema_version")
        .and_then(Value::as_str)
        .is_some_and(|v| !v.is_empty())
        || !stored.get("config").is_some_and(Value::is_object)
    {
        return Err(unavailable());
    }
    Ok(stored)
}

/// The body, or `None` when it exceeds `max` bytes or the stream fails.
async fn read_limited(response: &mut reqwest::Response, max: usize) -> Option<Vec<u8>> {
    if response
        .content_length()
        .is_some_and(|size| size > max as u64)
    {
        return None;
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await.ok()? {
        if bytes.len() + chunk.len() > max {
            return None;
        }
        bytes.extend_from_slice(&chunk);
    }
    Some(bytes)
}

/// Only the textual `detail` of a pod refusal, bounded in characters.
fn rejection_detail(bytes: &[u8]) -> Option<String> {
    const MAX_CHARS: usize = 500;
    let body: Value = serde_json::from_slice(bytes).ok()?;
    let detail = body.get("detail")?.as_str()?.trim();
    if detail.is_empty() {
        return None;
    }
    let mut bounded: String = detail.chars().take(MAX_CHARS).collect();
    if bounded.len() < detail.len() {
        bounded.push_str("...");
    }
    Some(bounded)
}

pub(super) fn apply_update(
    record: &mut AgentInstance,
    body: &UpdateAgentInstanceRequest,
    template: Option<&AgentTemplateSummary>,
    capabilities: Option<CapabilityUpdate>,
) -> AppResult<()> {
    // Envelopes validated for another selection must not replace a concurrent edit.
    if capabilities
        .as_ref()
        .is_some_and(|update| capability_basis(&record.tuning.0) != update.basis)
    {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "agent_capabilities_changed",
            "Capability settings changed concurrently; reload and retry.",
        ));
    }
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
    if let Some(update) = capabilities {
        object.insert("selected_capability_ids".into(), json!(update.selected));
        object.insert("capability_config".into(), Value::Object(update.config));
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

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agents::{AgentTemplateStatus, RuntimeCatalogSource};
    use axum::{Router, routing::post};

    const GENERIC: &str = "The pod rejected the capability configuration.";

    async fn pod_refusing(body: String) -> (PlatformConfig, AgentTemplateSummary) {
        let app = Router::new().route(
            "/agents/capabilities/{id}/validate-config",
            post(move || async move { (StatusCode::UNPROCESSABLE_ENTITY, body) }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base_url = format!("http://{}", listener.local_addr().unwrap());
        tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let platform = PlatformConfig {
            runtime_catalog_sources: vec![RuntimeCatalogSource {
                runtime_id: "pod".into(),
                base_url,
                public_base_url: None,
                enabled: true,
            }],
            ..Default::default()
        };
        let template = AgentTemplateSummary {
            template_id: uuid::Uuid::nil(),
            source_runtime_id: "pod".into(),
            source_agent_id: "custom".into(),
            display_name: "Custom".into(),
            description: String::new(),
            description_by_lang: None,
            category: "react".into(),
            tags: vec![],
            capabilities: vec![],
            team_instantiable: true,
            status: AgentTemplateStatus::Available,
            public_version: None,
            default_tuning_fields: vec![],
            max_chat_input_chars: None,
            available_capabilities: vec![],
            supports_capabilities: true,
            default_capability_ids: vec![],
        };
        (platform, template)
    }

    async fn refusal(body: String) -> String {
        let (platform, template) = pod_refusing(body).await;
        match validate_capability(&platform, &template, None, "document_access", json!({})).await {
            Err(AppError::Problem {
                status: StatusCode::UNPROCESSABLE_ENTITY,
                code: "agent_capability_config_invalid",
                detail,
            }) => detail.into_owned(),
            other => panic!("unexpected result: {other:?}"),
        }
    }

    #[tokio::test]
    async fn pod_refusal_relays_only_its_bounded_detail() {
        let reason = "Capability 'document_access' rejected the configuration: \
                      Session attachments are not available on this platform.";
        let body = json!({"detail": reason, "secret": "never relayed"}).to_string();
        assert_eq!(refusal(body).await, reason);

        // Multibyte text is cut on a character boundary.
        let long = "é".repeat(600);
        let detail = refusal(json!({"detail": long}).to_string()).await;
        assert_eq!(detail, format!("{}...", "é".repeat(500)));
    }

    #[tokio::test]
    async fn unusable_pod_refusal_keeps_the_generic_message() {
        for body in [
            String::new(),
            "not json".into(),
            json!({"detail": [{"msg": "structured"}]}).to_string(),
            json!({"detail": "  "}).to_string(),
            json!({"message": "no detail"}).to_string(),
            json!({"detail": "x".repeat(20 * 1024)}).to_string(),
        ] {
            assert_eq!(refusal(body).await, GENERIC);
        }
    }
}
