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
    agents,
    api::AppState,
    auth::{CurrentUser, bearer},
    domain::{Permission, SpaceKind, valid_subject},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery},
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
    pub space: RuntimeSpace,
    pub agent: RuntimeAgent,
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
    /// Complete saved AgentTuning JSON: fields, values, selections and envelopes.
    /// No projection, refresh from the catalog or second configuration vocabulary.
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
        ("agent" = Option<String>, Query, description = "Delegated agent instance UUID; must match agent_instance_id.")
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
    let record = super::get_for_space(&state.pool, space_id, instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if record.template_id
        != agents::template_id(
            space.organization,
            &record.source_runtime_id,
            &record.source_agent_id,
        )
    {
        return Err(anyhow::anyhow!("inconsistent saved agent template provenance").into());
    }
    if !state.fga.can_use_agent(record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    if !record.enabled {
        return Err(AppError::problem(
            StatusCode::CONFLICT,
            "agent_instance_disabled",
            "The agent instance is disabled.",
        ));
    }
    record
        .tuning
        .0
        .as_object()
        .context("invalid saved agent tuning")?;
    let binding = RuntimeBinding {
        subject_id: subject.to_owned(),
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
            configuration: record.tuning.0,
        },
    };
    // Current configuration and rights only; this response is no authorization lease.
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(binding)))
}
