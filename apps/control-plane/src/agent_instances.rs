// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped instance creation, lifecycle validation and persistence.

use std::collections::BTreeMap;

use axum::http::StatusCode;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::types::Json;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    agents::{self, enablement::usable_capability_ids},
    api::AppState,
    authorization,
    domain::{Permission, Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    model_catalog::instance::{self as models, ModelOfferKey, ModelOptions},
};

mod chat_controls;
pub mod http;
pub(crate) mod preparation;
mod runtime;
pub(crate) use runtime::{
    RuntimeSpace, TitleAdmission, require_executable, resolve_person_runtime_binding,
};
pub(crate) mod tuning;

const PAGE_SIZE: usize = 100;

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateAgentInstanceRequest {
    pub powerpoint: Option<crate::capability_preparation::FileChange>,
    /// Canonical UUID returned by this space's template catalog.
    pub template_id: Uuid,
    /// Unique within the space, ignoring case. Surrounding whitespace is trimmed.
    #[schema(min_length = 1, max_length = 255)]
    pub display_name: String,
    /// Immutable space-local reference, independent of the mutable display label.
    /// Omitted/null generates "agent-" followed by the new instance UUID's 32 hex digits.
    /// Explicit references are preserved; collisions return 409 agent_name_conflict.
    #[schema(min_length = 1, max_length = 64, pattern = "^[a-z0-9_-]{1,64}$")]
    pub logical_name: Option<String>,
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
    pub recommended_model: Option<ModelOfferKey>,
    /// Omitted/null means no invocation overrides; only the three typed fields are accepted.
    pub model_options: Option<ModelOptions>,
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

pub(crate) fn require_instance_space(kind: SpaceKind) -> AppResult<()> {
    if matches!(
        kind,
        SpaceKind::Team | SpaceKind::Project | SpaceKind::Personal
    ) {
        Ok(())
    } else {
        Err(AppError::BadRequest(
            "agent instances require a team, project or personal space".into(),
        ))
    }
}

/// Shared creation preflight: no SQL transaction survives discovery or capability calls.
pub(crate) async fn prepare_create(
    s: &AppState,
    user: &crate::auth::CurrentUser,
    space_id: Uuid,
    authorization_header: Option<&axum::http::HeaderValue>,
    body: &mut CreateAgentInstanceRequest,
) -> AppResult<NewAgentInstance> {
    let space = authorization::authorize(&s.pool, &user.uid, space_id, Permission::Write).await?;
    require_instance_space(space.kind)?;
    if !authorization::can_use_agent(&s.pool, body.template_id, &space).await? {
        return Err(AppError::NotFound);
    }
    tuning::validate_request(body)?;
    // Discovery and pod validation never retain a SQL connection or transaction.
    let (template, default_tuning) = agents::enrollable_template(
        &s.pool,
        &s.agent_catalog,
        space.organization,
        body.template_id,
    )
    .await?;
    let usable = usable_capability_ids(&s.pool, &space, &template.source_runtime_id).await?;
    let tuning = tuning::enroll(
        &s.agent_catalog,
        authorization_header,
        default_tuning,
        &template,
        &usable,
        body,
    )
    .await?;
    let draft_id = if let Some(change) = &body.powerpoint {
        crate::documents::powerpoint::acceptance::preflight(
            s,
            user,
            crate::documents::powerpoint::PowerPointTarget {
                space_id,
                agent: None,
                runtime: &template.source_runtime_id,
            },
            change,
            crate::documents::powerpoint::acceptance::slice(&tuning),
            authorization_header,
        )
        .await?
    } else {
        None
    };
    Ok(NewAgentInstance {
        agent_instance_id: draft_id.unwrap_or_else(Uuid::new_v4),
        space_id,
        template_id: template.template_id,
        source_runtime_id: template.source_runtime_id,
        source_agent_id: template.source_agent_id,
        logical_name: body.logical_name.clone(),
        display_name: body.display_name.clone(),
        description: body.description.clone(),
        enabled: true,
        created_by: user.uid.clone(),
        tuning,
    })
}

/// Ordinary creation and catalogue installation commit through the same validators.
pub(crate) async fn save_created(
    tx: &mut sqlx::Transaction<'_, sqlx::Postgres>,
    user: &crate::auth::CurrentUser,
    space: &crate::domain::Space,
    instance: &NewAgentInstance,
    powerpoint: Option<&crate::capability_preparation::FileChange>,
) -> AppResult<AgentInstance> {
    let space_id = space.id;
    let usable = usable_capability_ids(&mut **tx, space, &instance.source_runtime_id).await?;
    for id in tuning::saved_selection(&instance.tuning)? {
        if !usable.contains(&id) {
            return Err(agents::enablement::not_enabled(&id));
        }
    }
    require_instance_space(space.kind)?;
    if !authorization::can_use_agent(&mut **tx, instance.template_id, space).await? {
        return Err(AppError::NotFound);
    }
    models::validate_write(tx, space, &instance.tuning, true).await?;

    let record = create(&mut **tx, instance)
        .await
        .map_err(instance_write_error)?;
    crate::documents::powerpoint::acceptance::saved_agent(
        &mut *tx, user, &record, powerpoint, false,
    )
    .await?;
    let record = get_for_space(&mut **tx, space_id, record.agent_instance_id)
        .await?
        .ok_or(AppError::NotFound)?;
    Ok(record)
}

fn instance_write_error(error: sqlx::Error) -> AppError {
    if let Some(db) = error
        .as_database_error()
        .filter(|db| db.is_unique_violation())
    {
        let detail = match db.constraint() {
            Some("agent_instance_space_logical_name_key") => {
                "An agent with this logical name already exists in this space."
            }
            Some("uq_agent_instance_space_name") => {
                "An agent with this display name already exists in this space."
            }
            _ => return error.into(),
        };
        return AppError::problem(StatusCode::CONFLICT, "agent_name_conflict", detail);
    }
    error.into()
}

pub struct NewAgentInstance {
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub template_id: Uuid,
    pub source_runtime_id: String,
    pub source_agent_id: String,
    /// None generates a stable reference from this new instance's UUID.
    pub logical_name: Option<String>,
    pub display_name: String,
    pub description: Option<String>,
    pub enabled: bool,
    pub created_by: String,
    /// Complete, already validated Swift tuning, including opaque capability envelopes.
    pub tuning: Value,
}

#[derive(sqlx::FromRow)]
pub struct AgentInstance {
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub template_id: Uuid,
    pub source_runtime_id: String,
    pub source_agent_id: String,
    pub logical_name: String,
    pub display_name: String,
    pub description: Option<String>,
    pub enabled: bool,
    pub created_by: String,
    pub updated_by: String,
    pub configuration_revision: i64,
    pub preparation_state: String,
    pub preparation_error: Option<String>,
    pub tuning: Json<Value>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Returns the inserted row in the same statement, including database timestamps.
/// Omitted logical names use the new UUID, never the mutable display label.
/// All logical-name collisions fail through the space-local unique constraint.
pub async fn create<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    instance: &NewAgentInstance,
) -> sqlx::Result<AgentInstance> {
    let logical_name = instance
        .logical_name
        .clone()
        .unwrap_or_else(|| format!("agent-{}", instance.agent_instance_id.simple()));
    sqlx::query_as(
        "insert into agent_instance (
            agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            display_name, description, enabled, created_by, tuning, logical_name
        ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            logical_name, display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, preparation_state, preparation_error, created_at, updated_at",
    )
    .bind(instance.agent_instance_id)
    .bind(instance.space_id)
    .bind(instance.template_id)
    .bind(&instance.source_runtime_id)
    .bind(&instance.source_agent_id)
    .bind(instance.display_name.trim())
    .bind(&instance.description)
    .bind(instance.enabled)
    .bind(&instance.created_by)
    .bind(Json(&instance.tuning))
    .bind(logical_name)
    .fetch_one(ex)
    .await
}

pub async fn get_for_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    agent_instance_id: Uuid,
) -> sqlx::Result<Option<AgentInstance>> {
    sqlx::query_as(
        "select agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            logical_name, display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, preparation_state, preparation_error, created_at, updated_at
        from agent_instance where space_id = $1 and agent_instance_id = $2",
    )
    .bind(space_id)
    .bind(agent_instance_id)
    .fetch_optional(ex)
    .await
}

/// Policy filtering happens before pagination: neither a row nor a cursor can
/// disclose an agent whose template is disabled in this organization. This uses
/// the same authoritative policy relation as authorization::can_use_agent.
pub(super) async fn list_by_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: &Space,
    after: Option<&str>,
) -> sqlx::Result<Vec<AgentInstance>> {
    sqlx::query_as(
        "select a.agent_instance_id, a.space_id, a.template_id, a.source_runtime_id, a.source_agent_id,
            a.logical_name, a.display_name, a.description, a.enabled, a.created_by, a.updated_by,
            a.tuning, a.configuration_revision, a.preparation_state, a.preparation_error, a.created_at, a.updated_at
        from agent_instance a join agent_template_policy policy
            on policy.template_id = a.template_id and policy.organization_id = $2
        where a.space_id = $1 and a.logical_name > coalesce($3, '')
        order by a.logical_name limit $4",
    )
    .bind(space.id)
    .bind(space.organization)
    .bind(after)
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(ex)
    .await
}

/// A live instance's saved capability selection, with its space.
pub struct SelectingInstance {
    pub agent_instance_id: Uuid,
    pub display_name: String,
    pub source_runtime_id: String,
    pub selected: Vec<String>,
    pub space: Space,
}

#[derive(sqlx::FromRow)]
struct SelectingRow {
    agent_instance_id: Uuid,
    display_name: String,
    source_runtime_id: String,
    selected: Json<Vec<String>>,
    #[sqlx(flatten)]
    space: SpaceRow,
}

/// Instances of the organization's live spaces that select a capability.
/// Bounded by `space_organization`, then the `space_id` prefix of the name index.
pub async fn selecting_in_organization<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization_id: Uuid,
) -> sqlx::Result<Vec<SelectingInstance>> {
    let rows: Vec<SelectingRow> = sqlx::query_as(
        "select a.agent_instance_id, a.display_name, a.source_runtime_id,
            a.tuning -> 'selected_capability_ids' as selected,
            s.id, s.kind, s.name, s.description, s.personal_owner, s.parent_id, s.organization_id
        from space s join agent_instance a on a.space_id = s.id
        where s.organization_id = $1 and s.deletion_id is null
            and a.tuning -> 'selected_capability_ids' <> '[]'::jsonb
        order by s.name, a.display_name",
    )
    .bind(organization_id)
    .fetch_all(ex)
    .await?;
    Ok(rows
        .into_iter()
        .map(|row| SelectingInstance {
            agent_instance_id: row.agent_instance_id,
            display_name: row.display_name,
            source_runtime_id: row.source_runtime_id,
            selected: row.selected.0,
            space: row.space.into(),
        })
        .collect())
}

/// Writes only editable data; a no-op keeps both update attribution and timestamp.
/// Callers must reread and patch under the existing space mutation lock.
/// The database trigger owns update timestamps and no-op attribution; this
/// statement owns the execution revision used to reject stale conversations.
pub async fn update<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    instance: &AgentInstance,
    updated_by: &str,
) -> sqlx::Result<AgentInstance> {
    sqlx::query_as(
        "update agent_instance set
            display_name = $3, description = $4, enabled = $5, tuning = $6,
            configuration_revision = case when (display_name, description, enabled, tuning)
                is distinct from ($3, $4, $5, $6) then configuration_revision + 1 else configuration_revision end,
            updated_by = $7
        where space_id = $1 and agent_instance_id = $2
        returning agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            logical_name, display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, preparation_state, preparation_error, created_at, updated_at",
    )
    .bind(instance.space_id)
    .bind(instance.agent_instance_id)
    .bind(&instance.display_name)
    .bind(&instance.description)
    .bind(instance.enabled)
    .bind(&instance.tuning)
    .bind(updated_by)
    .fetch_one(ex)
    .await
}

pub(crate) fn require_revision(expected: i64, current: i64) -> crate::error::AppResult<()> {
    if expected != current {
        return Err(crate::error::AppError::problem(
            axum::http::StatusCode::CONFLICT,
            "agent_configuration_changed",
            "This agent has changed since this conversation started. Start a new conversation to use its new configuration.",
        ));
    }
    Ok(())
}

pub async fn delete<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
    agent_instance_id: Uuid,
) -> sqlx::Result<bool> {
    let result =
        // The database also retires PowerPoint files and marks agent preparations obsolete.
        sqlx::query("delete from agent_instance where space_id = $1 and agent_instance_id = $2")
            .bind(space_id)
            .bind(agent_instance_id)
            .execute(ex)
            .await?;
    Ok(result.rows_affected() > 0)
}

/// Preparation and admission expose skills only to the connected execution families.
fn supports_skills(template: &agents::AgentTemplateSummary) -> bool {
    !crate::embedded_agent::serves(&template.source_runtime_id, &template.source_agent_id)
        && matches!(template.category.as_str(), "react" | "deep")
}
