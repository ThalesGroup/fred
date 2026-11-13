// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Canonical configuration and current rights for saved-instance admission.
//! Execution and credential renewal remain the caller runtime's responsibility.

use anyhow::Context;
use axum::{
    Json,
    extract::State,
    http::{StatusCode, header},
    response::IntoResponse,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents::{self, enablement},
    api::AppState,
    auth::CurrentUser,
    authorization::{self, RuntimeCaller},
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
    model_catalog::instance::{self as models, RuntimeModels},
    onboarding,
};

/// Exact query parameters emitted by the Python OutboundCredentialProvider.
/// Unknown/duplicate parameters are rejected; no placement or configuration input.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeQuery {
    person: Option<String>,
    run: Option<String>,
    agent: Option<String>,
    conversation: Option<String>,
    model_source_id: Option<String>,
    model_upstream_id: Option<String>,
    #[serde(default)]
    reasoning: bool,
    #[serde(default)]
    resume: bool,
}

impl RuntimeQuery {
    fn subject<'a>(
        &'a self,
        state: &AppState,
        caller: &'a CurrentUser,
        instance_id: Uuid,
    ) -> AppResult<&'a str> {
        let assertion = authorization::Delegation {
            person: self.person.clone(),
            run: self.run.clone(),
            agent: self.agent.clone(),
        };
        assertion.subject(state, caller)?;
        if let Some(agent) = &self.agent
            && Uuid::parse_str(agent).ok() != Some(instance_id)
        {
            return Err(AppError::problem(
                StatusCode::FORBIDDEN,
                "delegation_target_mismatch",
                "The delegation does not name the requested instance.",
            ));
        }
        let subject = self.person.as_deref().unwrap_or(&caller.uid);
        Ok(subject)
    }
}

fn valid_grant_identifier(value: &str) -> bool {
    (1..=256).contains(&value.chars().count()) && !value.contains(['*', '#'])
}

fn invalid_grant() -> AppError {
    AppError::problem(
        StatusCode::UNPROCESSABLE_ENTITY,
        "invalid_fields",
        "Expected a complete person/run/agent assertion with plain identifiers.",
    )
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeBinding {
    pub subject_id: String,
    #[schema(required = true)]
    pub run_id: Option<String>,
    #[schema(required = true)]
    pub conversation_id: Option<String>,
    pub space: RuntimeSpace,
    pub agent: RuntimeAgent,
    pub models: RuntimeModels,
    pub mcp_bindings: Vec<crate::mcp_connections::McpBinding>,
    pub skills: Option<crate::skills::SkillCatalog>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skill_files: Option<std::collections::BTreeMap<String, String>>,
    /// Present only for trusted delegated or in-process admission.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub inference: Option<fred_rust_sdk::inference::InferenceAdmission>,
    /// Single server-reserved cosmetic attempt, only on execution admission.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub title: Option<TitleAdmission>,
    pub attachments: Vec<RuntimeAttachment>,
}

#[derive(Serialize, ToSchema)]
pub struct TitleAdmission {
    pub attempt_id: Uuid,
    pub inference: fred_rust_sdk::inference::InferenceAdmission,
}

#[derive(Serialize, sqlx::FromRow, ToSchema)]
pub struct RuntimeAttachment {
    pub document_id: Uuid,
    pub name: String,
    pub mime: String,
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeSpace {
    pub id: Uuid,
    pub kind: SpaceKind,
    /// Canonical organization attachment, not inherited document scope for personal spaces.
    #[schema(required = true)]
    pub organization_id: Option<Uuid>,
    #[schema(required = true)]
    pub team_id: Option<Uuid>,
    #[schema(required = true)]
    pub project_id: Option<Uuid>,
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeAgent {
    pub instance_id: Uuid,
    pub runtime_id: String,
    /// Organization-qualified template identity, distinct from the registry key.
    pub template_id: Uuid,
    pub template_key: String,
    pub configuration_revision: i64,
    pub configuration_updated_at: chrono::DateTime<chrono::Utc>,
    /// Saved tuning, excluding the legacy profile reference exposed in models for diagnostics.
    /// No refresh from the catalog; fields, values and capability envelopes are preserved.
    pub configuration: Value,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(resolve_runtime, admit_runtime))
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime",
    params(
        ("space_id" = Uuid, Path),
        ("agent_instance_id" = Uuid, Path),
        ("person" = Option<String>, Query, description = "Canonical person; only a trusted delegated call may supply this assertion."),
        ("run" = Option<String>, Query, description = "Run identifier; required together with person and agent."),
        ("agent" = Option<String>, Query, description = "Delegated agent instance UUID; must match agent_instance_id."),
        ("conversation" = Option<String>, Query, description = "Registered conversation; checked before loading history."),
        ("model_source_id" = Option<String>, Query, description = "Requested source; never authority."),
        ("model_upstream_id" = Option<String>, Query, description = "Requested model; supply with source."),
        ("reasoning" = Option<bool>, Query, description = "Requested reasoning subject to policy.")
    ),
    responses(
        (status = 200, body = RuntimeBinding),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn resolve_runtime(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space_id, instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<RuntimeQuery>,
) -> AppResult<impl IntoResponse> {
    let private = query.person.is_some() && state.auth.accepts_runtime_delegation(&caller);
    let binding = resolve_runtime_binding(
        &state,
        &caller,
        space_id,
        instance_id,
        &query,
        private,
        None,
    )
    .await?;
    // Current configuration and rights only; this response is no authorization lease.
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(binding)))
}

/// A trusted runtime admits an actual execution; read-only resolution never claims a title.
#[utoipa::path(post, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path),
        ("person" = String, Query), ("run" = String, Query), ("agent" = String, Query),
        ("conversation" = Option<String>, Query), ("model_source_id" = Option<String>, Query),
        ("model_upstream_id" = Option<String>, Query), ("reasoning" = Option<bool>, Query),
        ("resume" = Option<bool>, Query)),
    responses((status = 200, body = RuntimeBinding),
        (status = 400, body = crate::error::ErrorBody), (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody), (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody), (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody), (status = 503, body = crate::error::ErrorBody))) ]
async fn admit_runtime(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space_id, instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<RuntimeQuery>,
) -> AppResult<impl IntoResponse> {
    if query.person.is_none() || !state.auth.accepts_runtime_delegation(&caller) {
        return Err(AppError::Forbidden);
    }
    let binding = resolve_runtime_binding(
        &state,
        &caller,
        space_id,
        instance_id,
        &query,
        true,
        Some(!query.resume),
    )
    .await?;
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(binding)))
}

/// In-process admission for the authenticated person, without HTTP delegation.
pub(crate) async fn resolve_person_runtime_binding(
    state: &AppState,
    caller: &CurrentUser,
    space_id: Uuid,
    instance_id: Uuid,
    session_id: Option<Uuid>,
    choice: Option<&models::ModelOfferKey>,
    reasoning: bool,
) -> AppResult<RuntimeBinding> {
    let query = RuntimeQuery {
        person: None,
        run: None,
        agent: None,
        conversation: session_id.map(|id| id.to_string()),
        model_source_id: choice.map(|k| k.source_id.clone()),
        model_upstream_id: choice.map(|k| k.upstream_model_id.clone()),
        reasoning,
        resume: false,
    };
    resolve_runtime_binding(
        state,
        caller,
        space_id,
        instance_id,
        &query,
        true,
        Some(true),
    )
    .await
}

/// Resolve from an authenticated caller; query assertions still require validation.
async fn resolve_runtime_binding(
    state: &AppState,
    caller: &CurrentUser,
    space_id: Uuid,
    instance_id: Uuid,
    query: &RuntimeQuery,
    private: bool,
    title_attempt: Option<bool>,
) -> AppResult<RuntimeBinding> {
    let subject = query.subject(state, caller, instance_id)?;
    if query
        .conversation
        .as_deref()
        .is_some_and(|id| !valid_grant_identifier(id))
    {
        return Err(invalid_grant());
    }
    tracing::Span::current().record("user_id", subject);
    onboarding::require_accepted(
        &state.pool,
        state.onboarding.gcu_version.as_deref(),
        subject,
    )
    .await?;
    let space = authorization::authorize(&state.pool, subject, space_id, Permission::Read).await?;
    super::http::require_instance_space(space.kind)?;
    let initial = super::get_for_space(&state.pool, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !authorization::can_use_agent(&state.pool, initial.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let mcp_template = if super::tuning::saved_selection(&initial.tuning.0)?
        .iter()
        .any(|id| {
            id.starts_with("managed-mcp:") || id == crate::mcp_connections::TABULAR_CAPABILITY_ID
        }) {
        agents::editable_template(
            &state.pool,
            &state.agent_catalog,
            space.organization,
            &initial.source_runtime_id,
            &initial.source_agent_id,
        )
        .await?
    } else {
        None
    };
    let mut tx = state.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let mut record = super::get_for_space(&mut *tx, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    let attachments = if let Some(conversation) = &query.conversation {
        crate::sessions::require_association(&mut *tx, subject, conversation, &record).await?;
        sqlx::query_as::<_, RuntimeAttachment>(
            "select d.id as document_id, d.name, d.mime from document_current d
             join generation g on g.id = d.published_generation
             where d.session_id = $1 and d.space_id = $2
             and d.deletion_id is null and d.retrievable and not d.retrievable_pending
             order by d.created_at, d.id",
        )
        .bind(Uuid::parse_str(conversation).map_err(|_| invalid_grant())?)
        .bind(space_id)
        .fetch_all(&mut *tx)
        .await?
    } else {
        Vec::new()
    };
    require_executable(state, &space, &record)?;
    // Organization revocation is observed here, at the next turn, never during one.
    let policy = enablement::Policy::load_for_space(&mut *tx, &space).await?;
    enablement::require_usable(
        &policy,
        &space,
        &record.source_runtime_id,
        &super::tuning::saved_selection(&record.tuning.0)?,
    )?;
    let selected = super::tuning::saved_selection(&record.tuning.0)?;
    if selected.iter().any(|id| {
        id.starts_with("managed-mcp:") || id == crate::mcp_connections::TABULAR_CAPABILITY_ID
    }) {
        let template = mcp_template
            .as_ref()
            .filter(|t| t.supports_managed_mcp)
            .ok_or_else(|| enablement::not_enabled("managed_mcp"))?;
        super::tuning::require_inventory(template, &selected)?;
    }
    let mcp_bindings = crate::mcp_connections::bindings(
        &mut tx,
        space.organization,
        &state.agent_catalog.mcp_credentials,
        &selected,
        state.agent_catalog.knowledge_flow_url.as_deref(),
    )
    .await?;
    let snapshot = crate::skills::resolve(&mut tx, subject, &space, private).await?;
    let skills = Some(snapshot.catalog);
    let skill_files = private.then_some(snapshot.files);
    record
        .tuning
        .0
        .as_object()
        .context("invalid saved agent tuning")?;
    crate::capability_preparation::bind_result(&mut tx, &mut record, space.organization).await?;
    let models = models::resolve(&mut tx, space.organization, &record.tuning.0).await?;
    let choice = match (&query.model_source_id, &query.model_upstream_id) {
        (None, None) => None,
        (Some(source_id), Some(upstream_model_id)) => Some(models::ModelOfferKey {
            source_id: source_id.clone(),
            upstream_model_id: upstream_model_id.clone(),
        }),
        _ => {
            return Err(AppError::Unprocessable(
                "Model source and upstream identifiers must be supplied together.".into(),
            ));
        }
    };
    let inference = if private {
        let selection =
            models::decide(&models, choice.as_ref(), query.reasoning).map_err(|error| {
                AppError::problem(StatusCode::CONFLICT, error.code.as_str(), error.message)
            })?;
        Some(models::admit(&mut tx, space.organization, selection).await?)
    } else {
        None
    };
    let title_inference = if title_attempt == Some(true) {
        if let Some(selection) = inference
            .as_ref()
            .and_then(|main| models::decide_title(&models, &main.selection))
        {
            match models::admit(&mut tx, space.organization, selection).await {
                Ok(admission) => Some(admission),
                Err(_) => {
                    tracing::warn!(
                        event = "session_title",
                        outcome = "skipped",
                        reason = "admission_unavailable"
                    );
                    None
                }
            }
        } else {
            None
        }
    } else {
        None
    };
    tx.commit().await?;
    // Recheck authority after reading; the response still grants no continuing lease.
    onboarding::require_accepted(
        &state.pool,
        state.onboarding.gcu_version.as_deref(),
        subject,
    )
    .await?;
    let space = authorization::authorize(&state.pool, subject, space_id, Permission::Read).await?;
    if !authorization::can_use_agent(&state.pool, record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    if let Some(configuration) = record.tuning.0.as_object_mut() {
        configuration.remove("recommended_chat_profile_id");
    }
    let title = if title_attempt.is_some() {
        if let Some(session) = query
            .conversation
            .as_deref()
            .and_then(|id| Uuid::parse_str(id).ok())
        {
            match crate::sessions::title::claim(
                &state.pool,
                subject,
                space.id,
                session,
                instance_id,
                title_inference.is_some(),
            )
            .await
            {
                Ok(attempt) => {
                    attempt
                        .zip(title_inference)
                        .map(|(attempt_id, inference)| TitleAdmission {
                            attempt_id,
                            inference,
                        })
                }
                Err(_) => {
                    tracing::warn!(
                        event = "session_title",
                        outcome = "skipped",
                        reason = "claim_failed"
                    );
                    None
                }
            }
        } else {
            None
        }
    } else {
        None
    };
    Ok(RuntimeBinding {
        mcp_bindings,
        skills,
        skill_files,
        title,
        models,
        inference,
        attachments,
        subject_id: subject.to_owned(),
        run_id: query.run.clone(),
        conversation_id: query.conversation.clone(),
        space: RuntimeSpace {
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
        agent: RuntimeAgent {
            instance_id: record.agent_instance_id,
            runtime_id: record.source_runtime_id,
            template_id: record.template_id,
            template_key: record.source_agent_id,
            configuration_revision: record.configuration_revision,
            configuration_updated_at: record.updated_at,
            configuration: record.tuning.0,
        },
    })
}

/// Shared saved-instance admission facts; no network calls or alternate policy.
pub(crate) fn require_executable(
    state: &AppState,
    space: &crate::domain::Space,
    record: &super::AgentInstance,
) -> AppResult<()> {
    if record.template_id
        != agents::template_id(
            space.organization,
            &record.source_runtime_id,
            &record.source_agent_id,
        )
    {
        return Err(anyhow::anyhow!("inconsistent saved agent template provenance").into());
    }

    if record.source_runtime_id != fred_rust_agent::DEFINITION.provider
        && !state
            .agent_catalog
            .runtime_catalog_sources
            .iter()
            .any(|source| source.runtime_id == record.source_runtime_id && source.enabled)
    {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "agent_runtime_unavailable",
            "The configured agent runtime is unavailable.",
        ));
    }

    if !record.enabled {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "agent_instance_disabled",
            "The agent instance is disabled.",
        ));
    }
    if record.preparation_state != "ready" {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            if record.preparation_state == "failed" {
                "agent_capability_failed"
            } else {
                "agent_capability_pending"
            },
            record
                .preparation_error
                .clone()
                .unwrap_or_else(|| "PowerPoint template preparation is in progress".into()),
        ));
    }
    Ok(())
}
