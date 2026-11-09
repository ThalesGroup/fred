// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use crate::{
    api::AppState,
    capability_preparation::{self, FileChange},
};
use axum::http::HeaderValue;
use serde_json::Value;

/// Validate bytes without changing any accepted configuration or analysis.
pub(crate) async fn preflight(
    s: &AppState,
    user: &CurrentUser,
    target: PowerPointTarget<'_>,
    change: &FileChange,
    config: &Value,
    authorization: Option<&HeaderValue>,
) -> AppResult<Option<Uuid>> {
    let PowerPointTarget {
        space_id: space,
        agent,
        runtime,
    } = target;
    if !s
        .agent_catalog
        .capability_preparation
        .workers
        .contains_key(runtime)
    {
        return Err(AppError::Unavailable(
            "No preparation worker is configured for this pod".into(),
        ));
    }
    let Some(file) = change.file_id else {
        return Ok(agent);
    };
    let row: FileRow = sqlx::query_as("select * from powerpoint_file where id=$1")
        .bind(file)
        .fetch_optional(&s.pool)
        .await?
        .ok_or(AppError::NotFound)?;
    if row.actor != user.uid
        || row.file.space_id != space
        || row.file.runtime_id.as_deref() != Some(runtime)
        || agent.is_some_and(|id| Some(id) != row.file.agent_instance_id)
        || row.expected_file_id != change.expected_file_id
        || !row.upload_ready
        || row.file.status != PowerPointFileStatus::Pending
        || row.expires_at <= Utc::now()
    {
        return Err(AppError::Conflict(
            "The staged file does not match this save".into(),
        ));
    }
    let response = s
        .content
        .as_ref()
        .ok_or_else(unavailable)?
        .preparation_file(file)
        .await?;
    let bytes = axum::body::to_bytes(response.into_body(), 50 * 1024 * 1024)
        .await
        .map_err(|_| unavailable())?;
    let multipart = reqwest::multipart::Form::new()
        .text("config", config.to_string())
        .text("team_id", space.to_string())
        .part(
            "template",
            reqwest::multipart::Part::bytes(bytes.to_vec()).file_name(row.file.name),
        );
    let mut response = crate::agent_instances::tuning::capability_request(
        &s.agent_catalog,
        runtime,
        authorization,
        "ppt_builder/validate-config",
    )?
    .multipart(multipart)
    .send()
    .await
    .map_err(|_| unavailable())?;
    if response.status() != StatusCode::OK {
        let detail = crate::agent_instances::tuning::read_limited(&mut response, 16 * 1024)
            .await
            .and_then(|b| serde_json::from_slice::<Value>(&b).ok())
            .and_then(|v| v.get("detail").and_then(Value::as_str).map(str::to_owned))
            .unwrap_or_else(|| "PowerPoint validation unavailable".into());
        return Err(AppError::Unprocessable(detail));
    }
    Ok(row.file.agent_instance_id)
}

pub(crate) async fn attach(
    tx: &mut Transaction<'_, Postgres>,
    user: &CurrentUser,
    space: Uuid,
    agent: Option<Uuid>,
    runtime: &str,
    change: &FileChange,
) -> AppResult<()> {
    let previous = current(&mut **tx, space, agent, runtime).await?;
    unchanged(change.expected_file_id, previous.as_ref())?;
    if let Some(file) = change.file_id {
        let row: FileRow = sqlx::query_as("select * from powerpoint_file where id=$1 for update")
            .bind(file)
            .fetch_optional(&mut **tx)
            .await?
            .ok_or(AppError::NotFound)?;
        if row.actor != user.uid
            || row.file.space_id != space
            || row.file.agent_instance_id != agent
            || row.file.runtime_id.as_deref() != Some(runtime)
            || row.expected_file_id != change.expected_file_id
            || row.file.status != PowerPointFileStatus::Pending
            || !row.upload_ready
            || row.expires_at <= Utc::now()
        {
            return Err(AppError::Conflict(
                "The staged file changed before acceptance".into(),
            ));
        }
    }
    // The previous organization's effective file stays available during replacement.
    // The database releases quota, obsoletes preparations and clears retired template settings.
    sqlx::query("update powerpoint_file set status='retired',cleanup_due_at=greatest(expires_at,clock_timestamp()) where space_id=$1 and agent_instance_id is not distinct from $2 and runtime_id=$3 and status='stored' and ($2::uuid is not null or not effective or $4)")
        .bind(space).bind(agent).bind(runtime).bind(change.file_id.is_none()).execute(&mut **tx).await?;
    if let Some(file) = change.file_id {
        // The database runs local and organization used-byte and reservation accounting.
        sqlx::query("update powerpoint_file set status='stored',published_at=clock_timestamp(),live_agent_id=$2 where id=$1")
            .bind(file).bind(agent).execute(&mut **tx).await?;
    }
    Ok(())
}

pub(crate) async fn saved_agent(
    tx: &mut Transaction<'_, Postgres>,
    user: &CurrentUser,
    record: &crate::agent_instances::AgentInstance,
    change: Option<&FileChange>,
) -> AppResult<()> {
    let selected = record
        .tuning
        .0
        .get("selected_capability_ids")
        .and_then(Value::as_array)
        .is_some_and(|ids| ids.iter().any(|id| id == "ppt_builder"));
    if change.is_some_and(|c| c.file_id.is_some()) && !selected {
        return Err(AppError::Unprocessable(
            "Select PowerPoint before attaching a template".into(),
        ));
    }
    if let Some(change) = change {
        attach(
            tx,
            user,
            record.space_id,
            Some(record.agent_instance_id),
            &record.source_runtime_id,
            change,
        )
        .await?;
    }
    let row = current(
        &mut **tx,
        record.space_id,
        Some(record.agent_instance_id),
        &record.source_runtime_id,
    )
    .await?;
    if !selected || row.is_none() {
        sqlx::query("update capability_preparation set state='obsolete' where agent_instance_id=$1 and state<>'obsolete'").bind(record.agent_instance_id).execute(&mut **tx).await?;
        sqlx::query("update agent_instance set preparation_id=null,preparation_state='ready',preparation_error=null where agent_instance_id=$1").bind(record.agent_instance_id).execute(&mut **tx).await?;
        return Ok(());
    }
    let row = row.ok_or(AppError::NotFound)?;
    let reusable:bool=sqlx::query_scalar("select exists(select 1 from capability_preparation where agent_instance_id=$1 and configuration_revision=$2 and file_id=$3 and state in ('pending','ready'))")
        .bind(record.agent_instance_id).bind(record.configuration_revision).bind(row.file.id).fetch_one(&mut **tx).await?;
    if reusable {
        return Ok(());
    }
    sqlx::query("update capability_preparation set state='obsolete' where agent_instance_id=$1 and state<>'obsolete'").bind(record.agent_instance_id).execute(&mut **tx).await?;
    capability_preparation::enqueue(
        tx,
        row.file.id,
        &record.source_runtime_id,
        Some((record.agent_instance_id, record.configuration_revision)),
        slice(&record.tuning.0),
    )
    .await?;
    Ok(())
}

pub(crate) fn slice(tuning: &Value) -> &Value {
    tuning
        .pointer("/capability_config/ppt_builder/config")
        .unwrap_or(&Value::Null)
}
