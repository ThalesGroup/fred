// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped instance management, without execution admission.

use std::collections::BTreeMap;

use anyhow::Context;
use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode, header},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents::{self, enablement::usable_capability_ids},
    api::AppState,
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery, present},
    model_catalog::instance::{self as models, ModelOfferKey, ModelOptions, SavedModelSettings},
    onboarding::AdmittedUser,
    spaces,
};

use super::{
    AgentInstance, CreateAgentInstanceRequest, PAGE_SIZE, TuningValue, instance_write_error,
    prepare_create, require_instance_space, save_created, tuning,
};

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateAgentInstanceRequest {
    pub powerpoint: Option<crate::capability_preparation::FileChange>,
    /// Omitted/null metadata leaves the saved value unchanged.
    /// A new display name must remain unique within the space, ignoring case.
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
    /// Omitted keeps; null clears; a key sets a current M2-admissible recommendation.
    #[serde(default, deserialize_with = "present")]
    pub recommended_model: Option<Option<ModelOfferKey>>,
    /// Omitted keeps; null/{} resets; an object replaces all three overrides.
    #[serde(default, deserialize_with = "present")]
    pub model_options: Option<Option<ModelOptions>>,
}

#[derive(Serialize, ToSchema)]
pub struct ManagedAgentInstanceSummary {
    pub configuration_revision: i64,
    pub preparation_state: String,
    #[schema(required = true)]
    pub preparation_error: Option<String>,
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub template_id: Uuid,
    pub source_runtime_id: String,
    pub source_agent_id: String,
    pub logical_name: String,
    pub display_name: String,
    pub description: Option<String>,
    pub role: String,
    pub usage_statement: String,
    pub recommended_model: Option<ModelOfferKey>,
    /// Absent on pre-M3 records means no overrides, just like {}.
    pub model_options: Option<ModelOptions>,
    /// Operator state only, not runtime availability.
    pub status: AgentInstanceStatus,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub created_by: String,
    pub updated_by: String,
    pub created_by_name: Option<String>,
    pub updated_by_name: Option<String>,
    pub tuning_field_values: BTreeMap<String, Value>,
    pub selected_capability_ids: Option<Vec<String>>,
    /// Canonical names of selected managed MCP offers, including withdrawn offers.
    #[serde(skip_serializing_if = "BTreeMap::is_empty")]
    #[schema(required = false)]
    pub selected_capability_names: BTreeMap<String, String>,
    pub capability_config: BTreeMap<String, BTreeMap<String, Value>>,
}

/// Resolve one page's authors together, outside SQL transactions. Missing profiles are display data only.
async fn resolve_authors(s: &AppState, items: &mut [ManagedAgentInstanceSummary]) {
    let subjects = items
        .iter()
        .flat_map(|item| [item.created_by.clone(), item.updated_by.clone()])
        .collect();
    let names = async {
        crate::api::organization_directory(s)?
            .display_names(subjects)
            .await
    };
    let names = names.await.unwrap_or_else(|_| {
        tracing::warn!("Agent author names unavailable");
        Default::default()
    });
    for item in items {
        item.created_by_name = names.get(&item.created_by).cloned();
        item.updated_by_name = names.get(&item.updated_by).cloned();
    }
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AgentInstanceStatus {
    Enabled,
    Disabled,
}

fn record_to_summary(
    record: AgentInstance,
    managed_offers: &[agents::catalog::StoredCapability],
) -> AppResult<ManagedAgentInstanceSummary> {
    #[derive(Deserialize)]
    struct SavedTuning {
        role: String,
        #[serde(default)]
        usage_statement: String,
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
    let selected_capability_names = managed_offers
        .iter()
        .filter(|offer| {
            tuning
                .selected_capability_ids
                .as_ref()
                .is_some_and(|ids| ids.contains(&offer.capability_id))
        })
        .filter_map(|offer| {
            offer
                .descriptor
                .get("name")
                .and_then(Value::as_str)
                .map(|name| (offer.capability_id.clone(), name.to_owned()))
        })
        .collect();
    Ok(ManagedAgentInstanceSummary {
        selected_capability_names,
        created_by_name: None,
        updated_by_name: None,
        configuration_revision: record.configuration_revision,
        preparation_state: record.preparation_state,
        preparation_error: record.preparation_error,
        agent_instance_id: record.agent_instance_id,
        space_id: record.space_id,
        template_id: record.template_id,
        source_runtime_id: record.source_runtime_id,
        source_agent_id: record.source_agent_id,
        logical_name: record.logical_name,
        display_name: record.display_name,
        description: record.description,
        role: tuning.role,
        usage_statement: tuning.usage_statement,
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
    let instance = prepare_create(
        &s,
        &user,
        space_id,
        headers.get(header::AUTHORIZATION),
        &mut body,
    )
    .await?;
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    let record = save_created(&mut tx, &user, &space, &instance, body.powerpoint.as_ref()).await?;
    let managed_offers = agents::catalog::capabilities(
        &mut *tx,
        crate::mcp_connections::SOURCE_ID,
        space.organization,
    )
    .await?;
    let mut summary = record_to_summary(record, &managed_offers)?;
    tx.commit().await?;
    resolve_authors(&s, std::slice::from_mut(&mut summary)).await;
    Ok((StatusCode::CREATED, Json(summary)))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct AgentQuery {
    after: Option<String>,
}

#[derive(Serialize, ToSchema)]
pub struct AgentInstancePage {
    /// Authorized instances in immutable logical-name order; at most 100 rows.
    #[schema(max_items = 100)]
    pub items: Vec<ManagedAgentInstanceSummary>,
    /// Follow until null. Pages are current reads, not a snapshot.
    #[schema(required = true)]
    pub next_cursor: Option<String>,
}

#[utoipa::path(
    get, path = "/spaces/{space_id}/agent-instances",
    params(("space_id" = Uuid, Path), ("after" = Option<String>, Query, description = "Previous page cursor")),
    responses(
        (status = 200, body = AgentInstancePage),
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
    ApiQuery(query): ApiQuery<AgentQuery>,
) -> AppResult<Json<AgentInstancePage>> {
    let space = authorization::authorize(&s.pool, &user.uid, space_id, Permission::Read).await?;
    require_instance_space(space.kind)?;
    if query
        .after
        .as_deref()
        .is_some_and(|name| !crate::domain::valid_logical_name(name))
    {
        return Err(AppError::BadRequest("invalid agent catalog cursor".into()));
    }
    let mut records = super::list_by_space(&s.pool, &space, query.after.as_deref()).await?;
    let next_cursor = if records.len() > PAGE_SIZE {
        records.truncate(PAGE_SIZE);
        records.last().map(|record| record.logical_name.clone())
    } else {
        None
    };
    let managed_offers = agents::catalog::capabilities(
        &s.pool,
        crate::mcp_connections::SOURCE_ID,
        space.organization,
    )
    .await?;
    let mut items = records
        .into_iter()
        .map(|record| record_to_summary(record, &managed_offers))
        .collect::<AppResult<Vec<_>>>()?;
    resolve_authors(&s, &mut items).await;
    Ok(Json(AgentInstancePage { items, next_cursor }))
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
    let space = authorization::authorize(&s.pool, &user.uid, space_id, Permission::Read).await?;
    require_instance_space(space.kind)?;
    let record = super::get_for_space(&s.pool, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !authorization::can_use_agent(&s.pool, record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    let managed_offers = agents::catalog::capabilities(
        &s.pool,
        crate::mcp_connections::SOURCE_ID,
        space.organization,
    )
    .await?;
    let mut summary = record_to_summary(record, &managed_offers)?;
    resolve_authors(&s, std::slice::from_mut(&mut summary)).await;
    Ok(Json(summary))
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
    headers: HeaderMap,
    ApiJson(mut body): ApiJson<UpdateAgentInstanceRequest>,
) -> AppResult<Json<ManagedAgentInstanceSummary>> {
    // An effective edit preserves a failed analysis when its input file is unchanged.
    // A no-op PATCH (in particular {}) explicitly retries failure without changing
    // saved configuration; pending/ready preparations are retained, including on replay.
    let space = authorization::authorize(&s.pool, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    let record = super::get_for_space(&s.pool, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !authorization::can_use_agent(&s.pool, record.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    tuning::validate_update_request(&mut body)?;
    let changes_capabilities =
        body.capability_ids.is_some() || body.capability_config_values.is_some();
    // Discovery and pod validation run before the lock, without retaining a SQL connection.
    let template = if body.tuning_field_values.is_some() || changes_capabilities {
        match agents::editable_template(
            &s.pool,
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
    let capabilities = match (&template, changes_capabilities) {
        (Some(template), true) => Some(
            tuning::validate_capability_update(
                &s.agent_catalog,
                headers.get(header::AUTHORIZATION),
                template,
                &usable_capability_ids(&s.pool, &space, &template.source_runtime_id).await?,
                &record.tuning.0,
                &body,
            )
            .await?,
        ),
        (None, true) => {
            return Err(AppError::Unavailable(
                "Current template catalog is required to change capability settings.".into(),
            ));
        }
        _ => None,
    };
    if let Some(change) = &body.powerpoint {
        let config = capabilities
            .as_ref()
            .and_then(|c| c.config.get("ppt_builder"))
            .and_then(|v| v.get("config"))
            .unwrap_or_else(|| crate::documents::powerpoint::acceptance::slice(&record.tuning.0));
        crate::documents::powerpoint::acceptance::preflight(
            &s,
            &user,
            crate::documents::powerpoint::PowerPointTarget {
                space_id,
                agent: Some(agent_instance_id),
                runtime: &record.source_runtime_id,
            },
            change,
            config,
            headers.get(header::AUTHORIZATION),
        )
        .await?;
    }
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    // Lock before reading: concurrent partial edits must compose on the current row.
    sqlx::query("select agent_instance_id from agent_instance where space_id=$1 and agent_instance_id=$2 for update")
        .bind(space_id).bind(agent_instance_id).execute(&mut *tx).await?;
    let mut current = super::get_for_space(&mut *tx, space_id, agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    if !authorization::can_use_agent(&mut *tx, current.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    if body.powerpoint.is_some() && record.configuration_revision != current.configuration_revision
    {
        return Err(AppError::Conflict(
            "The agent changed during file validation; reload before saving".into(),
        ));
    }
    let previous = SavedModelSettings::read(&current.tuning.0)?;
    let new_recommendation = body
        .recommended_model
        .as_ref()
        .and_then(Option::as_ref)
        .is_some_and(|key| previous.recommended_model.as_ref() != Some(key));
    tuning::apply_update(&mut current, &body, template.as_ref(), capabilities)?;
    // Descriptive edits and explicit clears never depend on discovery health.
    if new_recommendation || matches!(body.model_options, Some(Some(_))) {
        models::validate_write(&mut tx, &space, &current.tuning.0, new_recommendation).await?;
    }

    if body.powerpoint.is_some() {
        sqlx::query("update agent_instance set configuration_revision=configuration_revision+1 where agent_instance_id=$1")
            .bind(agent_instance_id).execute(&mut *tx).await?;
    }
    let record = super::update(&mut *tx, &current, &user.uid)
        .await
        .map_err(instance_write_error)?;
    crate::documents::powerpoint::acceptance::saved_agent(
        &mut tx,
        &user,
        &record,
        body.powerpoint.as_ref(),
        record.configuration_revision == current.configuration_revision,
    )
    .await?;
    let record = super::get_for_space(&mut *tx, space_id, record.agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    let managed_offers = agents::catalog::capabilities(
        &mut *tx,
        crate::mcp_connections::SOURCE_ID,
        space.organization,
    )
    .await?;
    let mut summary = record_to_summary(record, &managed_offers)?;
    tx.commit().await?;
    resolve_authors(&s, std::slice::from_mut(&mut summary)).await;
    Ok(Json(summary))
}

#[utoipa::path(
    delete, path = "/spaces/{space_id}/agent-instances/{agent_instance_id}",
    params(("space_id" = Uuid, Path), ("agent_instance_id" = Uuid, Path)),
    responses(
        (status = 204, description = "Agent instance deleted; no CP file cleanup pending"),
        (status = 202, description = "Agent removed; original and prepared template cleanup pending"),
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
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    // Space editors can remove an instance even after its template is revoked.

    if !super::delete(&mut *tx, space_id, agent_instance_id).await? {
        return Err(AppError::NotFound);
    }
    let files_pending: bool = sqlx::query_scalar("select exists(select 1 from powerpoint_file where agent_instance_id=$1 and cleaned_at is null) or exists(select 1 from capability_preparation where agent_instance_id=$1 and state='obsolete' and cleaned_at is null)")
        .bind(agent_instance_id).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(if files_pending {
        StatusCode::ACCEPTED
    } else {
        StatusCode::NO_CONTENT
    })
}
