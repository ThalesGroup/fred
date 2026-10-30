// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Canonical configuration for the Python pod. This resolves data and current
//! rights only: definitions, runs, credential renewal and execution stay in Python.

use anyhow::Context;
use axum::{
    Json,
    extract::{FromRequestParts, State},
    http::{StatusCode, header, request::Parts},
    response::{IntoResponse, Response},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents::{self, enablement},
    api::AppState,
    auth::{CurrentUser, bearer},
    domain::{Permission, SpaceKind, valid_subject},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
    model_catalog::instance::{self as models, RuntimeModels},
    onboarding, spaces,
};

/// Keep the authenticated caller intact; an asserted person never becomes a
/// CurrentUser carrying the workload's roles. Only this extractor widens audience.
struct RuntimeCaller(CurrentUser);

impl FromRequestParts<AppState> for RuntimeCaller {
    type Rejection = Response;

    async fn from_request_parts(parts: &mut Parts, state: &AppState) -> Result<Self, Response> {
        state
            .auth
            .authenticate_runtime(bearer(parts))
            .await
            .map(Self)
            .map_err(IntoResponse::into_response)
    }
}

/// Exact query parameters emitted by the Python OutboundCredentialProvider.
/// Unknown/duplicate parameters are rejected; no placement or configuration input.
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeQuery {
    person: Option<String>,
    run: Option<String>,
    agent: Option<String>,
    conversation: Option<String>,
}

impl RuntimeQuery {
    fn subject<'a>(
        &'a self,
        state: &AppState,
        caller: &'a CurrentUser,
        instance_id: Uuid,
    ) -> AppResult<&'a str> {
        let has_assertion = self.person.is_some() || self.run.is_some() || self.agent.is_some();
        let subject = if has_assertion {
            if !state.auth.accepts_runtime_delegation(caller) {
                return Err(AppError::problem(
                    StatusCode::FORBIDDEN,
                    "delegation_not_allowed",
                    "The authenticated caller cannot delegate.",
                ));
            }
            let (Some(person), Some(run), Some(agent)) = (&self.person, &self.run, &self.agent)
            else {
                return Err(invalid_grant());
            };
            let (person, run, agent) = (person.trim(), run.trim(), agent.trim());
            if ![person, run, agent].into_iter().all(valid_grant_identifier) {
                return Err(invalid_grant());
            }
            if Uuid::parse_str(agent).ok() != Some(instance_id) {
                return Err(AppError::problem(
                    StatusCode::FORBIDDEN,
                    "delegation_target_mismatch",
                    "The delegation does not name the requested instance.",
                ));
            }
            // Already canonical at the delegating runtime; never remap this with
            // the workload's issuer or use its own terms/roles for this person.
            person
        } else {
            if caller.service_account
                || caller.delegation_caller
                || caller.roles.iter().any(|role| role == "service_agent")
            {
                return Err(AppError::problem(
                    StatusCode::FORBIDDEN,
                    "delegation_required",
                    "A workload must name the person, run and agent it acts for.",
                ));
            }
            caller.uid.as_str()
        };
        // A person is a single FGA user, never a wildcard or a userset.
        if !valid_subject(subject) || subject.contains('*') {
            return Err(invalid_grant());
        }
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
}

#[derive(Serialize, ToSchema)]
pub struct RuntimeSpace {
    pub id: Uuid,
    pub kind: SpaceKind,
    /// Canonical organization ownership, not inherited document scope for personal spaces.
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
    /// Organization-qualified OpenFGA identity, distinct from the registry key.
    pub template_id: Uuid,
    pub template_key: String,
    pub configuration_revision: i64,
    pub configuration_updated_at: chrono::DateTime<chrono::Utc>,
    /// Saved tuning, excluding the legacy profile reference exposed in models for diagnostics.
    /// No refresh from the catalog; fields, values and capability envelopes are preserved.
    pub configuration: Value,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(resolve_runtime))
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}/runtime",
    params(
        ("space_id" = Uuid, Path),
        ("agent_instance_id" = Uuid, Path),
        ("person" = Option<String>, Query, description = "Canonical person; only a trusted delegated call may supply this assertion."),
        ("run" = Option<String>, Query, description = "Run identifier; required together with person and agent."),
        ("agent" = Option<String>, Query, description = "Delegated agent instance UUID; must match agent_instance_id."),
        ("conversation" = Option<String>, Query, description = "Registered conversation; this resolver checks its private canonical association, then the pod checks checkpoint provenance before loading history.")
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
    let subject = query.subject(&state, &caller, instance_id)?;
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
    let space =
        spaces::authorize(&state.pool, &state.fga, subject, space_id, Permission::Read).await?;
    super::http::require_instance_space(space.kind)?;
    let initial = super::get_for_space(&state.pool, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !state.fga.can_use_agent(initial.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let mut tx = state.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let mut record = super::get_for_space(&mut *tx, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if let Some(conversation) = &query.conversation {
        crate::sessions::require_association(&mut *tx, subject, conversation, &record).await?;
    }
    require_executable(&state, &space, &record)?;
    // Organization revocation is observed here, at the next turn, never during one.
    let policy = enablement::Policy::load(&mut *tx, space.organization).await?;
    enablement::require_usable(
        &policy,
        &space,
        &record.source_runtime_id,
        &super::tuning::saved_selection(&record.tuning.0)?,
    )?;
    record
        .tuning
        .0
        .as_object()
        .context("invalid saved agent tuning")?;
    let models = models::resolve(
        &mut tx,
        space.organization,
        &record.tuning.0,
        query.person.is_some() && state.auth.accepts_runtime_delegation(&caller),
    )
    .await?;
    tx.commit().await?;
    // Recheck authority after reading; the response still grants no continuing lease.
    onboarding::require_accepted(
        &state.pool,
        state.onboarding.gcu_version.as_deref(),
        subject,
    )
    .await?;
    let space =
        spaces::authorize(&state.pool, &state.fga, subject, space_id, Permission::Read).await?;
    if !state.fga.can_use_agent(record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    if let Some(configuration) = record.tuning.0.as_object_mut() {
        configuration.remove("recommended_chat_profile_id");
    }
    let binding = RuntimeBinding {
        models,
        subject_id: subject.to_owned(),
        run_id: query.run.clone(),
        conversation_id: query.conversation.clone(),
        space: RuntimeSpace {
            id: space.id,
            kind: space.kind,
            organization_id: Some(space.organization),
            team_id: (space.kind == SpaceKind::Team).then_some(space.id),
            project_id: None,
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
    };
    // Current configuration and rights only; this response is no authorization lease.
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(binding)))
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
    Ok(())
}
