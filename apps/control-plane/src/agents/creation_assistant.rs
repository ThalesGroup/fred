// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Drafts use the template's pod and the common model policy, without an instance.

use std::{collections::BTreeMap, time::Duration};

use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agent_instances::{
        require_instance_space,
        tuning::{pod_request, read_limited},
    },
    agents::{self, AgentTemplateSummary, enablement},
    api::AppState,
    authorization::{self, Delegation, RuntimeCaller},
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    model_catalog::instance as models,
    onboarding::{self, AdmittedUser},
    organization_prompt_settings,
};

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentDraftCapabilityCandidate {
    #[schema(min_length = 1, max_length = 200)]
    id: String,
    #[schema(min_length = 1, max_length = 200)]
    name: String,
    #[serde(default)]
    #[schema(max_length = 1000)]
    description: String,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentDraftRequest {
    #[schema(min_length = 1, max_length = 4000)]
    description: String,
    #[serde(default = "default_language")]
    #[schema(
        default = "en",
        min_length = 2,
        max_length = 35,
        pattern = "^[A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*$"
    )]
    language: String,
    #[schema(max_length = 200)]
    agent_name: Option<String>,
    #[schema(max_length = 500)]
    agent_role: Option<String>,
    #[serde(default)]
    #[schema(max_items = 500)]
    capabilities: Vec<AgentDraftCapabilityCandidate>,
}
fn default_language() -> String {
    "en".into()
}

impl AgentDraftRequest {
    fn validate(&mut self) -> AppResult<()> {
        fn text(value: &mut String, min: usize, max: usize) -> AppResult<()> {
            *value = value.trim().to_owned();
            if !(min..=max).contains(&value.chars().count()) || value.contains('\0') {
                return Err(AppError::Unprocessable(
                    "Invalid creation assistant input length.".into(),
                ));
            }
            Ok(())
        }
        text(&mut self.description, 1, 4000)?;
        text(&mut self.language, 2, 35)?;
        let mut language = self.language.split(['-', '_']);
        if !language.next().is_some_and(|v| {
            (2..=3).contains(&v.len()) && v.bytes().all(|c| c.is_ascii_alphabetic())
        }) || !language
            .all(|v| (2..=8).contains(&v.len()) && v.bytes().all(|c| c.is_ascii_alphanumeric()))
        {
            return Err(AppError::Unprocessable(
                "Invalid creation assistant language.".into(),
            ));
        }
        if let Some(name) = &mut self.agent_name {
            text(name, 0, 200)?;
        }
        if let Some(role) = &mut self.agent_role {
            text(role, 0, 500)?;
        }
        if self.capabilities.len() > 500 {
            return Err(AppError::Unprocessable(
                "Too many draft capabilities.".into(),
            ));
        }
        for candidate in &mut self.capabilities {
            text(&mut candidate.id, 1, 200)?;
            text(&mut candidate.name, 1, 200)?;
            text(&mut candidate.description, 0, 1000)?;
        }
        Ok(())
    }
}

#[derive(Deserialize, Serialize, ToSchema)]
pub struct AgentDraftResult {
    #[schema(max_length = 60)]
    name: Option<String>,
    #[schema(max_length = 120)]
    role: Option<String>,
    #[schema(max_length = 300)]
    description: Option<String>,
    system_prompt: String,
    capability_ids: Vec<String>,
}

/// Same picker used for the catalogue and admission. A hidden field is not a draft destination.
pub(super) fn prompt_key(fields: &[BTreeMap<String, Value>]) -> Option<String> {
    let editable = |field: &&BTreeMap<String, Value>| {
        field.get("type").and_then(Value::as_str) == Some("prompt")
            && field
                .get("key")
                .and_then(Value::as_str)
                .is_some_and(|key| !key.trim().is_empty())
            && !field
                .get("ui")
                .and_then(|ui| ui.get("hide"))
                .and_then(Value::as_bool)
                .unwrap_or(false)
    };
    fields
        .iter()
        .filter(editable)
        .find(|field| field.get("key").and_then(Value::as_str) == Some("prompts.system"))
        .or_else(|| fields.iter().find(editable))
        .and_then(|field| field.get("key"))
        .and_then(Value::as_str)
        .map(str::to_owned)
}

async fn target(
    s: &AppState,
    subject: &str,
    space_id: Uuid,
    template_id: Uuid,
) -> AppResult<(Space, AgentTemplateSummary)> {
    let space = authorization::authorize(&s.pool, subject, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    if !authorization::can_use_agent(&s.pool, template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let (template, _) =
        agents::enrollable_template(&s.pool, &s.agent_catalog, space.organization, template_id)
            .await?;
    if template.creation_assistant_prompt_key.is_none()
        || !s
            .agent_catalog
            .runtime_catalog_sources
            .iter()
            .any(|source| source.enabled && source.runtime_id == template.source_runtime_id)
    {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "creation_assistant_unavailable",
            "This template has no editable instructions for the creation assistant.",
        ));
    }
    Ok((space, template))
}

fn offered(
    template: &AgentTemplateSummary,
    policy: &enablement::Policy,
    space: &Space,
) -> Vec<String> {
    template
        .available_capabilities
        .iter()
        .filter_map(|entry| entry.get("id").and_then(Value::as_str))
        .filter(|id| {
            enablement::usable(
                policy,
                space,
                enablement::selection_source(&template.source_runtime_id, id),
                id,
            )
        })
        .map(str::to_owned)
        .collect()
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(draft))
        .routes(utoipa_axum::routes!(admit))
}

#[utoipa::path(operation_id="draft_agent", post, path="/spaces/{space_id}/agent-templates/{template_id}/creation-assistant/draft",
    params(("space_id"=Uuid,Path),("template_id"=Uuid,Path)), request_body=AgentDraftRequest,
    responses((status=200,body=AgentDraftResult),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
        (status=502,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody),(status=504,body=crate::error::ErrorBody)))]
async fn draft(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, template_id)): ApiPath<(Uuid, Uuid)>,
    headers: HeaderMap,
    ApiJson(mut input): ApiJson<AgentDraftRequest>,
) -> AppResult<Json<AgentDraftResult>> {
    input.validate()?;
    let (space, template) = target(&s, &user.uid, space_id, template_id).await?;
    let policy = enablement::Policy::load_for_space(&s.pool, &space).await?;
    let allowed = offered(&template, &policy, &space);
    input
        .capabilities
        .retain(|candidate| allowed.contains(&candidate.id));
    let mut body = serde_json::to_value(&input).map_err(anyhow::Error::from)?;
    body["space_id"] = serde_json::json!(space.id);
    body["template_id"] = serde_json::json!(template.template_id);
    let request = pod_request(
        &s.agent_catalog,
        &template.source_runtime_id,
        headers.get(header::AUTHORIZATION),
        "creation-assistant/draft",
    )?
    .timeout(Duration::from_secs(55))
    .json(&body);
    let unavailable = || {
        AppError::problem(
            StatusCode::BAD_GATEWAY,
            "creation_assistant_failed",
            "The agent runtime could not draft the agent. Please try again.",
        )
    };
    let mut response = request.send().await.map_err(|error| {
        AppError::problem(
            if error.is_timeout() {
                StatusCode::GATEWAY_TIMEOUT
            } else {
                StatusCode::SERVICE_UNAVAILABLE
            },
            "creation_assistant_unavailable",
            "The agent runtime is unavailable. Please try again.",
        )
    })?;
    if response.status() != StatusCode::OK {
        let status = match response.status().as_u16() {
            403 => StatusCode::FORBIDDEN,
            409 => StatusCode::CONFLICT,
            422 => StatusCode::UNPROCESSABLE_ENTITY,
            503 => StatusCode::SERVICE_UNAVAILABLE,
            504 => StatusCode::GATEWAY_TIMEOUT,
            _ => StatusCode::BAD_GATEWAY,
        };
        return Err(AppError::problem(
            status,
            "creation_assistant_failed",
            "The agent could not be drafted. Your input is unchanged; please try again.",
        ));
    }
    let bytes = read_limited(&mut response, 128 * 1024)
        .await
        .ok_or_else(unavailable)?;
    let mut result: AgentDraftResult = serde_json::from_slice(&bytes).map_err(|_| unavailable())?;
    if result.system_prompt.trim().is_empty()
        || [&result.name, &result.role, &result.description]
            .into_iter()
            .zip([60, 120, 300])
            .any(|(value, max)| value.as_ref().is_some_and(|v| v.chars().count() > max))
    {
        return Err(unavailable());
    }
    result.capability_ids.retain(|id| {
        input
            .capabilities
            .iter()
            .any(|candidate| &candidate.id == id)
    });
    result.capability_ids.sort();
    result.capability_ids.dedup();
    Ok(Json(result))
}

#[derive(Serialize, ToSchema)]
struct AgentDraftAdmission {
    subject_id: String,
    run_id: String,
    space: crate::agent_instances::RuntimeSpace,
    template_id: Uuid,
    runtime_id: String,
    template_key: String,
    prompt_key: String,
    capability_ids: Vec<String>,
    creation_prompt: Option<String>,
    inference: fred_rust_sdk::inference::InferenceAdmission,
}

#[utoipa::path(operation_id="admit_agent_draft", post, path="/spaces/{space_id}/agent-templates/{template_id}/creation-assistant/runtime",
    params(("space_id"=Uuid,Path),("template_id"=Uuid,Path),("person"=String,Query),("run"=String,Query),("agent"=String,Query)),
    responses((status=200,body=AgentDraftAdmission),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
        (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn admit(
    State(s): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space_id, template_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<Delegation>,
) -> AppResult<impl axum::response::IntoResponse> {
    if query.person.is_none() || !s.auth.accepts_runtime_delegation(&caller) {
        return Err(AppError::Forbidden);
    }
    let subject = query.subject(&s, &caller)?;
    if query
        .agent
        .as_deref()
        .and_then(|value| Uuid::parse_str(value).ok())
        != Some(template_id)
    {
        return Err(AppError::Forbidden);
    }
    onboarding::require_accepted(&s.pool, s.onboarding.gcu_version.as_deref(), subject).await?;
    // Discovery is outside SQL. Every policy fact used below belongs to one fresh snapshot.
    let (_, template) = target(&s, subject, space_id, template_id).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    onboarding::require_accepted(&mut *tx, s.onboarding.gcu_version.as_deref(), subject).await?;
    let space = authorization::authorize(&mut *tx, subject, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    if !authorization::can_use_agent(&mut *tx, template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let policy = enablement::Policy::load_for_space(&mut *tx, &space).await?;
    let settings = organization_prompt_settings::read(&mut *tx, space.organization).await?;
    let models = models::resolve_for_space(&mut tx, &space, &serde_json::json!({})).await?;
    let selection = models::decide(
        &models,
        settings
            .creation_model
            .as_ref()
            .map(|value| &value.0)
            .or(models.policy.creation_assistant.as_ref()),
        settings.creation_reasoning,
    )
    .map_err(|error| AppError::problem(StatusCode::CONFLICT, error.code.as_str(), error.message))?;
    let inference = models::admit(&mut tx, space.organization, selection).await?;
    tx.commit().await?;
    let binding = AgentDraftAdmission {
        subject_id: subject.to_owned(),
        run_id: query.run.ok_or(AppError::Forbidden)?,
        space: crate::agent_instances::RuntimeSpace {
            id: space.id,
            kind: space.kind,
            organization_id: Some(space.organization),
            team_id: match space.kind {
                SpaceKind::Team => Some(space.id),
                SpaceKind::Project => space.parent_id,
                _ => None,
            },
            project_id: (space.kind == SpaceKind::Project).then_some(space.id),
        },
        template_id,
        runtime_id: template.source_runtime_id.clone(),
        template_key: template.source_agent_id.clone(),
        prompt_key: template
            .creation_assistant_prompt_key
            .clone()
            .ok_or(AppError::NotFound)?,
        capability_ids: offered(&template, &policy, &space),
        creation_prompt: settings.creation_text,
        inference,
    };
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(binding)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn only_visible_prompt_fields_can_receive_a_draft() {
        let fields: Vec<BTreeMap<String, Value>> = serde_json::from_value(json!([
            {"key":"prompts.system","type":"prompt","ui":{"hide":true}},
            {"key":"description","type":"text-multiline"},
            {"key":"instructions","type":"prompt"}
        ]))
        .unwrap();
        assert_eq!(prompt_key(&fields).as_deref(), Some("instructions"));
        assert_eq!(prompt_key(&fields[..2]), None);
        assert_eq!(prompt_key(&[]), None);
        let fields: Vec<BTreeMap<String, Value>> = serde_json::from_value(json!([
            {"key":"instructions","type":"prompt"},
            {"key":"prompts.system","type":"prompt"}
        ]))
        .unwrap();
        assert_eq!(prompt_key(&fields).as_deref(), Some("prompts.system"));
    }

    #[test]
    fn public_body_cannot_supply_private_settings_or_model_authority() {
        for key in [
            "model",
            "reasoning",
            "creation_prompt",
            "inference",
            "space_id",
            "template_id",
        ] {
            let mut value = json!({"description":"Draft"});
            value[key] = json!("injected");
            assert!(serde_json::from_value::<AgentDraftRequest>(value).is_err());
        }
        for (description, language) in [(" ", "en"), ("ok", "en. injected"), ("ok", "en-x")] {
            let mut input: AgentDraftRequest =
                serde_json::from_value(json!({"description":description,"language":language}))
                    .unwrap();
            assert!(input.validate().is_err());
        }
    }
}
