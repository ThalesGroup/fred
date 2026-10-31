// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Browser routing and model facts, never a turn grant. Model decisions remain
//! owned by M2/M3; runtime independently admits every turn through the resolver.

use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
    response::IntoResponse,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents::{self, PlatformConfig, enablement},
    api::AppState,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
    model_catalog::{
        ModelMetadata,
        instance::{
            self as models, ModelDiagnostic, ModelOfferKey, ModelOptions, ModelPreparationError,
            RuntimeModels,
        },
    },
    onboarding::{self, AdmittedUser},
    sessions, spaces,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PreparationQuery {
    session_id: Option<String>,
    model_source_id: Option<String>,
    model_upstream_id: Option<String>,
}

impl PreparationQuery {
    fn model_choice(&self) -> AppResult<Option<ModelOfferKey>> {
        match (&self.model_source_id, &self.model_upstream_id) {
            (None, None) => Ok(None),
            (Some(source_id), Some(upstream_model_id)) => Ok(Some(ModelOfferKey {
                source_id: source_id.clone(),
                upstream_model_id: upstream_model_id.clone(),
            })),
            _ => Err(AppError::Unprocessable(
                "Model source and upstream identifiers must be supplied together.".into(),
            )),
        }
    }
}

#[derive(Serialize, ToSchema)]
pub struct PreparationModelOffer {
    pub key: ModelOfferKey,
    pub permitted: bool,
    pub candidate: bool,
    pub selectable: bool,
    pub reasoning_enabled: bool,
    pub diagnostics: Vec<ModelDiagnostic>,
    #[schema(required = true)]
    pub metadata: Option<ModelMetadata>,
}

#[derive(Serialize, ToSchema)]
pub struct PreparationModels {
    #[schema(required = true)]
    pub recommendation: Option<ModelOfferKey>,
    #[schema(required = true)]
    pub default: Option<ModelOfferKey>,
    #[schema(required = true)]
    pub fallback: Option<ModelOfferKey>,
    pub options: ModelOptions,
    /// A retained diagnostic only, never a selectable profile.
    #[schema(required = true)]
    pub legacy_profile_id: Option<String>,
    pub requires_reselection: bool,
    pub offers: Vec<PreparationModelOffer>,
}

impl From<RuntimeModels> for PreparationModels {
    fn from(models: RuntimeModels) -> Self {
        Self {
            recommendation: models.recommendation,
            default: models.policy.default,
            fallback: models.policy.fallback,
            options: models.options,
            legacy_profile_id: models.legacy_profile_id,
            requires_reselection: models.requires_reselection,
            offers: models
                .offers
                .into_iter()
                .map(|offer| PreparationModelOffer {
                    reasoning_enabled: offer.candidate
                        && models.policy.reasoning_enabled.contains(&offer.key)
                        && offer
                            .metadata
                            .as_ref()
                            .is_some_and(|m| m.reasoning == Some(true)),
                    key: offer.key,
                    permitted: offer.permitted,
                    candidate: offer.candidate,
                    selectable: offer.selectable,
                    diagnostics: offer.diagnostics,
                    metadata: offer.metadata,
                })
                .collect(),
        }
    }
}

#[derive(Serialize, ToSchema)]
pub struct ChatControlDescriptor {
    pub capability_id: String,
    pub widget: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<std::collections::BTreeMap<String, serde_json::Value>>,
}

#[derive(Serialize, ToSchema)]
pub struct ExecutionPreparation {
    pub agent_configuration_revision: i64,
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub runtime_id: String,
    pub execution_transport: ExecutionTransport,
    pub execute_url: String,
    pub execute_stream_url: String,
    /// RFC 6570 Level 1 template. Substitute the registered session ID.
    pub messages_url_template: String,
    pub supports_streaming: bool,
    /// False until the managed Weaver HITL journey is connected.
    pub supports_hitl: bool,
    pub supports_ui_parts: bool,
    #[schema(required = true)]
    pub max_chat_input_chars: Option<u64>,
    pub chat_controls: Vec<ChatControlDescriptor>,
    pub models: PreparationModels,
    /// Echo of the requested choice; binds this diagnostic to the current composer selection.
    #[schema(required = true)]
    pub model_choice: Option<ModelOfferKey>,
    /// A readable preparation may be blocked; callers must check before sending a turn.
    #[schema(required = true)]
    pub model_error: Option<ModelPreparationError>,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionTransport {
    Sse,
}

pub(crate) fn public_base<'a>(config: &'a PlatformConfig, runtime_id: &str) -> Option<&'a str> {
    config
        .runtime_catalog_sources
        .iter()
        .find(|source| source.runtime_id == runtime_id && source.enabled)
        .and_then(|source| source.public_base_url.as_deref())
        .map(|base| base.trim_end_matches('/'))
}

// The pod validated the saved envelopes; only the current inventory is rechecked.
fn require_available_capabilities(
    tuning: &Value,
    template: &agents::AgentTemplateSummary,
) -> AppResult<Vec<String>> {
    let selected = super::tuning::saved_selection(tuning)?;
    super::tuning::require_inventory(template, &selected)?;
    Ok(selected)
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(prepare_execution))
}

#[utoipa::path(post, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/prepare-execution",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path),
        ("session_id" = Option<String>, Query, description = "Registered conversation to verify before routing."),
        ("model_source_id" = Option<String>, Query, description = "Requested model source; supply together with model_upstream_id."),
        ("model_upstream_id" = Option<String>, Query, description = "Requested upstream model; never an authorization.")),
    responses((status = 200, body = ExecutionPreparation),
        (status = 401, body = crate::error::ErrorBody), (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody), (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody), (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn prepare_execution(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<PreparationQuery>,
    headers: HeaderMap,
) -> AppResult<impl IntoResponse> {
    let space = spaces::authorize(
        &s.pool,
        &s.authorization,
        &user.uid,
        space_id,
        Permission::Read,
    )
    .await?;
    super::http::require_instance_space(space.kind)?;
    let initial = super::get_for_space(&s.pool, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !s
        .authorization
        .can_use_agent(initial.template_id, &space)
        .await?
    {
        return Err(AppError::NotFound);
    }
    let base = public_base(&s.agent_catalog, &initial.source_runtime_id).ok_or_else(|| {
        AppError::problem(
            StatusCode::CONFLICT,
            "agent_public_route_unavailable",
            "No approved public route is configured for this runtime.",
        )
    })?;
    // Discovery supplies current template support/input policy, never destinations.
    // It runs outside SQL and has the existing timeout and no-redirect policy.
    let template = agents::editable_template(
        &s.agent_catalog,
        space.organization,
        &initial.source_runtime_id,
        &initial.source_agent_id,
    )
    .await?
    .ok_or_else(|| {
        AppError::problem(
            StatusCode::CONFLICT,
            "agent_template_unavailable",
            "The configured runtime no longer advertises this template.",
        )
    })?;
    if !matches!(template.category.as_str(), "react" | "graph") {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "agent_execution_not_connected",
            "This execution family is not connected to managed Weaver chat.",
        ));
    }
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let current = super::get_for_space(&mut *tx, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if let Some(session_id) = &query.session_id {
        sessions::require_association(&mut *tx, &user.uid, session_id, &current).await?;
    }
    super::require_executable(&s, &space, &current)?;
    let selected = require_available_capabilities(&current.tuning.0, &template)?;
    let policy = enablement::Policy::load(&mut *tx, space.organization).await?;
    enablement::require_usable(&policy, &space, &current.source_runtime_id, &selected)?;
    let model_choice = query.model_choice()?;
    let models = models::resolve(&mut tx, space.organization, &current.tuning.0, false).await?;
    let model_error = models::preparation_error(&models, model_choice.as_ref());
    tx.commit().await?;
    onboarding::require_accepted(&s.pool, s.onboarding.gcu_version.as_deref(), &user.uid).await?;
    let space = spaces::authorize(
        &s.pool,
        &s.authorization,
        &user.uid,
        space_id,
        Permission::Read,
    )
    .await?;
    if !s
        .authorization
        .can_use_agent(current.template_id, &space)
        .await?
    {
        return Err(AppError::NotFound);
    }
    let models: PreparationModels = models.into();
    let mut chat_controls = super::chat_controls::resolve(
        &s.agent_catalog,
        &template,
        &current.tuning.0,
        &selected,
        headers.get(header::AUTHORIZATION),
    )
    .await;
    if models.offers.iter().any(|offer| offer.reasoning_enabled) {
        chat_controls.push(ChatControlDescriptor {
            capability_id: "platform".into(),
            widget: "reasoning_toggle".into(),
            params: Some(std::collections::BTreeMap::from([(
                "default".into(),
                serde_json::json!(false),
            )])),
        });
    }
    let result = ExecutionPreparation {
        agent_configuration_revision: current.configuration_revision,
        agent_instance_id: instance_id,
        space_id,
        runtime_id: current.source_runtime_id,
        execution_transport: ExecutionTransport::Sse,
        execute_url: format!("{base}/agents/execute"),
        execute_stream_url: format!("{base}/agents/execute/stream"),
        messages_url_template: format!("{base}/agents/sessions/{{session_id}}/messages"),
        supports_streaming: true,
        supports_hitl: false,
        supports_ui_parts: true,
        max_chat_input_chars: template.max_chat_input_chars,
        chat_controls,
        models,
        model_choice,
        model_error,
    };
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(result)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn admits_only_selections_from_the_template_inventory() {
        let mut template = agents::AgentTemplateSummary {
            template_id: Uuid::nil(),
            source_runtime_id: "pod".into(),
            source_agent_id: "custom".into(),
            display_name: "Custom".into(),
            description: String::new(),
            description_by_lang: None,
            category: "react".into(),
            tags: vec![],
            capabilities: vec![],
            team_instantiable: true,
            status: agents::AgentTemplateStatus::Available,
            public_version: None,
            default_tuning_fields: vec![],
            max_chat_input_chars: None,
            available_capabilities: vec![std::collections::BTreeMap::from([(
                "id".into(),
                json!("search"),
            )])],
            supports_capabilities: true,
            default_capability_ids: vec!["other".into()],
        };
        let saved = |ids: Value| json!({"selected_capability_ids": ids});
        assert!(require_available_capabilities(&saved(json!(["search"])), &template).is_ok());
        assert!(require_available_capabilities(&saved(json!([])), &template).is_ok());
        assert!(matches!(
            require_available_capabilities(&saved(json!(["other"])), &template),
            Err(AppError::Problem {
                code: "agent_capability_unavailable",
                ..
            })
        ));
        // The selection is always materialized; its absence is never the template default.
        assert!(require_available_capabilities(&saved(Value::Null), &template).is_err());
        template.available_capabilities.clear();
        assert!(require_available_capabilities(&saved(json!(["search"])), &template).is_err());
    }
}
