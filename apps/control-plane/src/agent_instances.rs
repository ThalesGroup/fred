// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-scoped instance persistence. Callers supply canonical identities, enforce
//! authorization/lifecycle rules and validate tuning before calling this module.

use chrono::{DateTime, Utc};
use serde_json::Value;
use sqlx::types::Json;
use uuid::Uuid;

use crate::domain::{Space, SpaceRow};

mod chat_controls;
pub mod http;
pub(crate) mod preparation;
mod runtime;
pub(crate) use runtime::require_executable;
mod tuning;

pub struct NewAgentInstance {
    pub agent_instance_id: Uuid,
    pub space_id: Uuid,
    pub template_id: Uuid,
    pub source_runtime_id: String,
    pub source_agent_id: String,
    pub display_name: String,
    pub description: Option<String>,
    pub enabled: bool,
    pub created_by: Option<String>,
    pub updated_by: Option<String>,
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
    pub display_name: String,
    pub description: Option<String>,
    pub enabled: bool,
    pub created_by: Option<String>,
    pub updated_by: Option<String>,
    pub configuration_revision: i64,
    pub tuning: Json<Value>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Returns the inserted row in the same statement, including database timestamps.
/// A name collision is SQLSTATE 23505 on `uq_agent_instance_space_name`.
pub async fn create<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    instance: &NewAgentInstance,
) -> sqlx::Result<AgentInstance> {
    sqlx::query_as(
        "insert into agent_instance (
            agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            display_name, description, enabled, created_by, updated_by, tuning
        ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, created_at, updated_at",
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
    .bind(&instance.updated_by)
    .bind(Json(&instance.tuning))
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
            display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, created_at, updated_at
        from agent_instance where space_id = $1 and agent_instance_id = $2",
    )
    .bind(space_id)
    .bind(agent_instance_id)
    .fetch_optional(ex)
    .await
}

pub async fn list_by_space<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space_id: Uuid,
) -> sqlx::Result<Vec<AgentInstance>> {
    sqlx::query_as(
        "select agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, created_at, updated_at
        from agent_instance where space_id = $1 order by created_at, agent_instance_id",
    )
    .bind(space_id)
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
            s.id, s.kind, s.name, s.personal_owner, s.parent_id, s.organization_id
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
            updated_at = case when (display_name, description, enabled, tuning)
                is distinct from ($3, $4, $5, $6) then clock_timestamp() else updated_at end,
            updated_by = case when (display_name, description, enabled, tuning)
                is distinct from ($3, $4, $5, $6) then $7 else updated_by end
        where space_id = $1 and agent_instance_id = $2
        returning agent_instance_id, space_id, template_id, source_runtime_id, source_agent_id,
            display_name, description, enabled, created_by, updated_by, tuning, configuration_revision, created_at, updated_at",
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
        sqlx::query("delete from agent_instance where space_id = $1 and agent_instance_id = $2")
            .bind(space_id)
            .bind(agent_instance_id)
            .execute(ex)
            .await?;
    Ok(result.rows_affected() > 0)
}
