// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped instance management, without execution admission.

use std::collections::{BTreeMap, BTreeSet};

use anyhow::Context;
use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
};
use chrono::{DateTime, Utc};
use futures::{StreamExt, TryStreamExt};
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents,
    api::AppState,
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    model_catalog::instance::{self as models, ModelOfferKey, ModelOptions, SavedModelSettings},
    onboarding::AdmittedUser,
    spaces,
};

use super::{AgentInstance, NewAgentInstance, tuning};

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateAgentInstanceRequest {
    /// Canonical UUID returned by this space's template catalog.
    pub template_id: Uuid,
    #[schema(min_length = 1, max_length = 255)]
    pub display_name: String,
    #[schema(max_length = 500)]
    pub description: Option<String>,
    #[schema(min_length = 1, max_length = 255)]
    pub role: Option<String>,
    #[schema(min_length = 1)]
    pub usage_statement: String,
    /// All values must match TuningValue before unknown keys are ignored.
    /// Known values must also match the pod's FieldSpecs.
    pub tuning_field_values: Option<BTreeMap<String, TuningValue>>,
    /// Omitted/null inherits template defaults; [] selects no optional capabilities.
    pub capability_ids: Option<Vec<String>>,
    /// Values for unselected capabilities are ignored.
    pub capability_config_values: Option<BTreeMap<String, BTreeMap<String, Value>>>,
    /// Legacy diagnostic reference only; non-null creation is refused. Re-select by offer key.
    pub recommended_chat_profile_id: Option<String>,
    pub recommended_model: Option<ModelOfferKey>,
    /// Omitted/null means no invocation overrides; only the three typed fields are accepted.
    pub model_options: Option<ModelOptions>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateAgentInstanceRequest {
    /// Omitted/null metadata leaves the saved value unchanged.
    #[schema(min_length = 1, max_length = 255)]
    pub display_name: Option<String>,
    /// An empty string is an explicit description.
    #[schema(max_length = 500)]
    pub description: Option<String>,
    #[schema(min_length = 1, max_length = 255)]
    pub role: Option<String>,
    #[schema(min_length = 1)]
    pub usage_statement: Option<String>,
    pub status: Option<AgentInstanceStatus>,
    /// Omitted keeps values; null/{} clears them; an object replaces known values.
    #[serde(default, deserialize_with = "present")]
    pub tuning_field_values: Option<Option<BTreeMap<String, TuningValue>>>,
    /// Omitted keeps selection; null resolves current defaults; [] selects none.
    #[serde(default, deserialize_with = "present")]
    pub capability_ids: Option<Option<Vec<String>>>,
    /// Omitted keeps config for an unchanged selection; null resets selected config.
    #[serde(default, deserialize_with = "present")]
    pub capability_config_values: Option<Option<BTreeMap<String, BTreeMap<String, Value>>>>,
    /// Omitted keeps the recommendation; null clears it; other values return 422.
    #[serde(default, deserialize_with = "present")]
    pub recommended_chat_profile_id: Option<Option<String>>,
    /// Omitted keeps; null clears; a key sets a current M2-admissible recommendation.
    #[serde(default, deserialize_with = "present")]
    pub recommended_model: Option<Option<ModelOfferKey>>,
    /// Omitted keeps; null/{} resets; an object replaces all three overrides.
    #[serde(default, deserialize_with = "present")]
    pub model_options: Option<Option<ModelOptions>>,
}

// Serde calls this only for present keys, so explicit null remains Some(None).
fn present<'de, D, T>(deserializer: D) -> Result<Option<Option<T>>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer).map(Some)
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(untagged)]
pub enum TuningScalar {
    String(String),
    #[schema(value_type = f64)]
    Number(serde_json::Number),
    Boolean(bool),
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(untagged)]
pub enum TuningValue {
    Scalar(TuningScalar),
    Array(Vec<TuningScalar>),
    Object(BTreeMap<String, TuningScalar>),
}

#[derive(Serialize, ToSchema)]
pub struct ManagedAgentInstanceSummary {
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub template_id: Uuid,
    pub source_runtime_id: String,
    pub source_agent_id: String,
    pub display_name: String,
    pub description: Option<String>,
    pub role: String,
    pub usage_statement: String,
    /// Diagnostic only; requires explicit re-selection if no recommended_model is saved.
    pub recommended_chat_profile_id: Option<String>,
    pub recommended_model: Option<ModelOfferKey>,
    /// Absent on pre-M3 records means no overrides, just like {}.
    pub model_options: Option<ModelOptions>,
    /// Operator state only, not runtime availability.
    pub status: AgentInstanceStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub created_by: Option<String>,
    pub updated_by: Option<String>,
    pub tuning_field_values: BTreeMap<String, Value>,
    pub selected_capability_ids: Option<Vec<String>>,
    pub capability_config: BTreeMap<String, BTreeMap<String, Value>>,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AgentInstanceStatus {
    Enabled,
    Disabled,
}

fn record_to_summary(record: AgentInstance) -> AppResult<ManagedAgentInstanceSummary> {
    #[derive(Deserialize)]
    struct SavedTuning {
        role: String,
        #[serde(default)]
        usage_statement: String,
        recommended_chat_profile_id: Option<String>,
        recommended_model: Option<ModelOfferKey>,
        model_options: Option<ModelOptions>,
        #[serde(default)]
        values: BTreeMap<String, Value>,
        selected_capability_ids: Option<Vec<String>>,
        #[serde(default)]
        capability_config: BTreeMap<String, BTreeMap<String, Value>>,
    }
    let tuning: SavedTuning =
        serde_json::from_value(record.tuning.0).context("invalid saved agent tuning")?;
    Ok(ManagedAgentInstanceSummary {
        agent_instance_id: record.agent_instance_id,
        space_id: record.space_id,
        template_id: record.template_id,
        source_runtime_id: record.source_runtime_id,
        source_agent_id: record.source_agent_id,
        display_name: record.display_name,
        description: record.description,
        role: tuning.role,
        usage_statement: tuning.usage_statement,
        recommended_chat_profile_id: tuning.recommended_chat_profile_id,
        recommended_model: tuning.recommended_model,
        model_options: tuning.model_options,
        status: if record.enabled {
            AgentInstanceStatus::Enabled
        } else {
            AgentInstanceStatus::Disabled
        },
        created_at: record.created_at,
        updated_at: record.updated_at,
        created_by: record.created_by,
        updated_by: record.updated_by,
        tuning_field_values: tuning.values,
        selected_capability_ids: tuning.selected_capability_ids,
        capability_config: tuning.capability_config,
    })
}

pub(crate) fn require_instance_space(kind: SpaceKind) -> AppResult<()> {
    if matches!(kind, SpaceKind::Team | SpaceKind::Personal) {
        Ok(())
    } else {
        Err(AppError::BadRequest(
            "agent instances require a team or personal space".into(),
        ))
    }
}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(create_agent_instance))
        .routes(utoipa_axum::routes!(list_agent_instances))
        .routes(utoipa_axum::routes!(get_agent_instance))
        .routes(utoipa_axum::routes!(update_agent_instance))
        .routes(utoipa_axum::routes!(delete_agent_instance))
        .merge(super::runtime::routes())
        .merge(super::preparation::routes())
}

#[utoipa::path(
    post, path = "/spaces/{space_id}/agent-instances",
    params(("space_id" = Uuid, Path)),
    request_body = CreateAgentInstanceRequest,
    responses(
        (status = 201, body = ManagedAgentInstanceSummary),
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
async fn create_agent_instance(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
    headers: HeaderMap,
    ApiJson(mut body): ApiJson<CreateAgentInstanceRequest>,
) -> AppResult<(StatusCode, Json<ManagedAgentInstanceSummary>)> {
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    if !s.fga.can_use_agent(body.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    tuning::validate_request(&mut body)?;
    // Discovery and pod validation never retain a SQL connection or transaction.
    let (template, default_tuning) =
        agents::enrollable_template(&s.agent_catalog, space.organization, body.template_id).await?;
    let tuning = tuning::enroll(
        &s.agent_catalog,
        headers.get(header::AUTHORIZATION),
        default_tuning,
        &template,
        &body,
    )
    .await?;
    let instance = NewAgentInstance {
        agent_instance_id: Uuid::new_v4(),
        space_id,
        template_id: template.template_id,
        source_runtime_id: template.source_runtime_id,
        source_agent_id: template.source_agent_id,
        display_name: body.display_name,
        description: body.description,
        enabled: true,
        created_by: Some(user.uid.clone()),
        updated_by: None,
        tuning,
    };
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &space).await?;
    let space =
        spaces::authorize_locked(&mut tx, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    if !s.fga.can_use_agent(instance.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    models::validate_write(&mut tx, space.organization, &instance.tuning, true).await?;
    s.fga.fence(&mut guard).await?;
    let record = super::create(&mut *tx, &instance)
        .await
        .map_err(instance_write_error)?;
    let summary = record_to_summary(record)?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, Json(summary)))
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/agent-instances",
    params(("space_id" = Uuid, Path)),
    responses(
        (status = 200, body = [ManagedAgentInstanceSummary]),
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
async fn list_agent_instances(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space_id): ApiPath<Uuid>,
) -> AppResult<Json<Vec<ManagedAgentInstanceSummary>>> {
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    require_instance_space(space.kind)?;
    let records = super::list_by_space(&s.pool, space_id).await?;
    let template_ids: BTreeSet<_> = records.iter().map(|record| record.template_id).collect();
    let fga = &s.fga;
    let space = &space;
    let template_use: BTreeMap<_, _> = futures::stream::iter(template_ids)
        .map(|template_id| async move {
            fga.can_use_agent(template_id, space)
                .await
                .map(|allowed| (template_id, allowed))
        })
        .buffered(crate::fga::READ_CONCURRENCY)
        .try_collect()
        .await?;
    let instances = records
        .into_iter()
        .filter(|record| template_use.get(&record.template_id) == Some(&true))
        .map(record_to_summary)
        .collect::<AppResult<Vec<_>>>()?;
    Ok(Json(instances))
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path)),
    responses(
        (status = 200, body = ManagedAgentInstanceSummary),
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
async fn get_agent_instance(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, agent_instance_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<ManagedAgentInstanceSummary>> {
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Read).await?;
    require_instance_space(space.kind)?;
    let record = super::get_for_space(&s.pool, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !s.fga.can_use_agent(record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    Ok(Json(record_to_summary(record)?))
}

fn instance_write_error(error: sqlx::Error) -> AppError {
    if error.as_database_error().is_some_and(|db| {
        db.is_unique_violation() && db.constraint() == Some("uq_agent_instance_space_name")
    }) {
        AppError::problem(
            StatusCode::CONFLICT,
            "agent_name_conflict",
            "An agent with this name already exists in this space.",
        )
    } else {
        error.into()
    }
}

#[utoipa::path(
    patch, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path)),
    request_body = UpdateAgentInstanceRequest,
    responses(
        (status = 200, body = ManagedAgentInstanceSummary),
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
async fn update_agent_instance(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, agent_instance_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(mut body): ApiJson<UpdateAgentInstanceRequest>,
) -> AppResult<Json<ManagedAgentInstanceSummary>> {
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    let record = super::get_for_space(&s.pool, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !s.fga.can_use_agent(record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    tuning::validate_update_request(&mut body)?;
    let changes_capabilities =
        body.capability_ids.is_some() || body.capability_config_values.is_some();
    // Only the saved source's contract is fetched, without retaining a SQL connection.
    let template = if body.tuning_field_values.is_some() || changes_capabilities {
        match agents::editable_template(
            &s.agent_catalog,
            space.organization,
            &record.source_runtime_id,
            &record.source_agent_id,
        )
        .await
        {
            Ok(template) => template,
            Err(AppError::Unavailable(_)) if !changes_capabilities => {
                tracing::warn!("agent edit uses saved tuning fields: catalog unavailable");
                None
            }
            Err(error) => return Err(error),
        }
    } else {
        None
    };
    if changes_capabilities && template.is_none() {
        return Err(AppError::Unavailable(
            "Current template catalog is required to change capability settings.".into(),
        ));
    }
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &space).await?;
    let space =
        spaces::authorize_locked(&mut tx, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    // Apply omissions to the current row, not the snapshot read before discovery.
    let mut current = super::get_for_space(&mut *tx, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !s.fga.can_use_agent(current.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let previous = SavedModelSettings::read(&current.tuning.0)?;
    let new_recommendation = body
        .recommended_model
        .as_ref()
        .and_then(Option::as_ref)
        .is_some_and(|key| previous.recommended_model.as_ref() != Some(key));
    tuning::apply_update(&mut current, &body, template.as_ref())?;
    // Descriptive edits and explicit clears never depend on discovery health.
    if new_recommendation || matches!(body.model_options, Some(Some(_))) {
        models::validate_write(
            &mut tx,
            space.organization,
            &current.tuning.0,
            new_recommendation,
        )
        .await?;
    }
    s.fga.fence(&mut guard).await?;
    let record = super::update(&mut *tx, &current, &user.uid)
        .await
        .map_err(instance_write_error)?;
    let summary = record_to_summary(record)?;
    tx.commit().await?;
    Ok(Json(summary))
}

#[utoipa::path(
    delete, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path)),
    responses(
        (status = 204, description = "Agent instance deleted"),
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
async fn delete_agent_instance(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, agent_instance_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    let space = spaces::authorize(&s.pool, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &space).await?;
    let space =
        spaces::authorize_locked(&mut tx, &s.fga, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    // Space editors can remove an instance even after its template is revoked.
    s.fga.fence(&mut guard).await?;
    if !super::delete(&mut *tx, space_id, agent_instance_id).await? {
        return Err(AppError::NotFound);
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
