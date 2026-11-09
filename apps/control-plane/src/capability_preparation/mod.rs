// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Durable preparation of a library installed on one logical agent pod.
use crate::{
    api::AppState,
    auth::CurrentUser,
    error::{AppError, AppResult},
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{Postgres, Transaction};
use utoipa::ToSchema;
use uuid::Uuid;

pub mod dispatch;
mod http;
pub(crate) use http::routes;

#[derive(Clone, Debug, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// Logical pod -> verified workload. Separate identities prevent cross-pod consumption.
    #[serde(default)]
    pub workers: std::collections::BTreeMap<String, crate::processing::config::WorkerIdentity>,
}

pub(crate) fn worker(s: &AppState, user: &CurrentUser, runtime: &str) -> AppResult<()> {
    let expected = s
        .agent_catalog
        .capability_preparation
        .workers
        .get(runtime)
        .ok_or(AppError::Forbidden)?;
    if !user.service_account
        || user.client_id.as_deref() != Some(&expected.client_id)
        || user
            .token_issuer
            .as_deref()
            .map(|v| v.trim_end_matches('/'))
            != Some(expected.issuer.trim_end_matches('/'))
        || !user.token_audiences.contains(&expected.audience)
    {
        return Err(AppError::Forbidden);
    }
    Ok(())
}

pub(crate) fn queue(installation: Uuid, runtime: &str) -> String {
    format!("capability-{installation}-{runtime}")
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct FileChange {
    /// A staged CP receipt for this exact space, logical pod and instance; null removes.
    pub file_id: Option<Uuid>,
    pub expected_file_id: Option<Uuid>,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct Work {
    pub preparation_id: Uuid,
    pub installation_id: Uuid,
    pub runtime_id: String,
    pub capability_id: String,
    pub space_id: Uuid,
    #[schema(required = true)]
    pub agent_instance_id: Option<Uuid>,
    #[schema(required = true)]
    pub configuration_revision: Option<i64>,
    pub file_id: Uuid,
    pub sha256: String,
    pub filename: String,
    pub size: i64,
    #[schema(value_type = Object)]
    pub config: sqlx::types::Json<Value>,
    pub state: String,
}

pub(crate) async fn work(pool: &sqlx::PgPool, id: Uuid) -> AppResult<Work> {
    sqlx::query_as("select p.id preparation_id,d.namespace installation_id,p.runtime_id,p.capability_id,p.space_id,p.agent_instance_id,p.configuration_revision,p.file_id,f.sha256,f.name filename,f.size,p.config,p.state from capability_preparation p join powerpoint_file f on f.id=p.file_id cross join document_storage d where p.id=$1 and d.singleton")
        .bind(id).fetch_optional(pool).await?.ok_or(AppError::NotFound)
}

/// Called only inside the accepted save transaction, after canonical attachment changes.
pub(crate) async fn enqueue(
    tx: &mut Transaction<'_, Postgres>,
    file: Uuid,
    runtime: &str,
    instance: Option<(Uuid, i64)>,
    config: &Value,
) -> AppResult<Uuid> {
    let installation: Uuid =
        sqlx::query_scalar("select namespace from document_storage where singleton")
            .fetch_one(&mut **tx)
            .await?;
    let id = Uuid::new_v4();
    sqlx::query("insert into capability_preparation(id,file_id,runtime_id,capability_id,space_id,agent_instance_id,configuration_revision,config,workflow_id,task_queue) select $1,id,$3,'ppt_builder',space_id,$4,$5,$6,$7,$8 from powerpoint_file where id=$2 and status='stored' and runtime_id=$3")
        .bind(id).bind(file).bind(runtime).bind(instance.map(|v|v.0)).bind(instance.map(|v|v.1)).bind(config)
        .bind(format!("capability-{installation}-{id}")).bind(queue(installation,runtime)).execute(&mut **tx).await?;
    if let Some((agent, revision)) = instance {
        sqlx::query("update agent_instance set preparation_id=$2,preparation_state='pending',preparation_error=null where agent_instance_id=$1 and configuration_revision=$3")
            .bind(agent).bind(id).bind(revision).execute(&mut **tx).await?;
    }
    Ok(id)
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ResultConfirmation {
    pub reference: Option<String>,
    pub error: Option<String>,
}

#[derive(sqlx::FromRow)]
struct ConfirmationRow {
    state: String,
    file_id: Uuid,
    agent_instance_id: Option<Uuid>,
    configuration_revision: Option<i64>,
    runtime_id: String,
    reference: Option<String>,
    error: Option<String>,
}

pub(crate) async fn confirm(s: &AppState, id: Uuid, input: ResultConfirmation) -> AppResult<()> {
    if input.reference.is_some() == input.error.is_some()
        || input
            .reference
            .as_ref()
            .is_some_and(|r| r.is_empty() || r.len() > 256)
        || input
            .error
            .as_ref()
            .is_some_and(|r| r.is_empty() || r.len() > 2000)
    {
        return Err(AppError::Unprocessable(
            "Expected one bounded result or failure".into(),
        ));
    }
    let organization: Uuid = sqlx::query_scalar("select f.organization_id from capability_preparation p join powerpoint_file f on f.id=p.file_id where p.id=$1").bind(id).fetch_one(&s.pool).await?;
    let mut tx = s.pool.begin().await?;
    crate::spaces::lock_organization_id(&mut tx, organization).await?;
    let row: ConfirmationRow = sqlx::query_as("select state,file_id,agent_instance_id,configuration_revision,runtime_id,reference,error from capability_preparation where id=$1 for update").bind(id).fetch_one(&mut *tx).await?;
    if row.state != "pending" {
        if row.state == "obsolete" || (row.reference == input.reference && row.error == input.error)
        {
            return Ok(());
        }
        return Err(AppError::Conflict("Preparation already settled".into()));
    }
    let applicable: bool = sqlx::query_scalar("select exists(select 1 from powerpoint_file f join space s on s.id=f.space_id where f.id=$1 and f.status='stored' and s.deletion_id is null and (f.agent_instance_id is null or exists(select 1 from agent_instance a where a.agent_instance_id=$2 and a.configuration_revision=$3 and a.preparation_id=$4)))")
        .bind(row.file_id).bind(row.agent_instance_id).bind(row.configuration_revision).bind(id).fetch_one(&mut *tx).await?;
    if !applicable {
        sqlx::query("update capability_preparation set state='obsolete' where id=$1")
            .bind(id)
            .execute(&mut *tx)
            .await?;
    } else {
        let state = if input.error.is_some() {
            "failed"
        } else {
            "ready"
        };
        sqlx::query("update capability_preparation set state=$2,reference=$3,error=$4 where id=$1")
            .bind(id)
            .bind(state)
            .bind(&input.reference)
            .bind(&input.error)
            .execute(&mut *tx)
            .await?;
        if let Some(agent) = row.agent_instance_id {
            sqlx::query("update agent_instance set preparation_state=$2,preparation_error=$3 where agent_instance_id=$1 and preparation_id=$4 and configuration_revision=$5")
                .bind(agent).bind(state).bind(&input.error).bind(id).bind(row.configuration_revision).execute(&mut *tx).await?;
        } else if state == "ready" {
            // A re-read of the same file supersedes only earlier acknowledged attempts.
            sqlx::query("update capability_preparation set state='obsolete' where file_id=$1 and id<>$2 and state='ready'")
                .bind(row.file_id).bind(id).execute(&mut *tx).await?;
            // An organization replacement keeps its previous file until this transaction.
            // The database releases quota, obsoletes preparations and clears retired template settings.
            sqlx::query("update powerpoint_file set status='retired',effective=false,cleanup_due_at=greatest(expires_at,clock_timestamp()) where space_id=(select space_id from powerpoint_file where id=$1) and runtime_id=$2 and agent_instance_id is null and effective and id<>$1")
                .bind(row.file_id).bind(&row.runtime_id).execute(&mut *tx).await?;
            // The database checks whether template settings must be cleared.
            sqlx::query("update powerpoint_file set effective=true where id=$1")
                .bind(row.file_id)
                .execute(&mut *tx)
                .await?;
        }
    }
    tx.commit().await?;
    Ok(())
}

/// Per-turn projection of an opaque, acknowledged result; no readiness RPC or new inference.
pub(crate) async fn bind_result(
    tx: &mut Transaction<'_, Postgres>,
    record: &mut crate::agent_instances::AgentInstance,
    organization: Uuid,
) -> AppResult<()> {
    if !record
        .tuning
        .0
        .get("selected_capability_ids")
        .and_then(Value::as_array)
        .is_some_and(|ids| ids.iter().any(|id| id == "ppt_builder"))
    {
        return Ok(());
    }
    let common: Option<Value> = sqlx::query_scalar("select s.config from organization_powerpoint_settings s where s.organization_id=$1 and s.runtime_id=$2 and not exists(select 1 from powerpoint_file own where own.agent_instance_id=$3 and own.status='stored')")
        .bind(organization).bind(&record.source_runtime_id).bind(record.agent_instance_id).fetch_optional(&mut **tx).await?;
    if let Some(config) = record
        .tuning
        .0
        .pointer_mut("/capability_config/ppt_builder/config")
        .and_then(Value::as_object_mut)
    {
        config.insert(
            "common_template_config".into(),
            common.unwrap_or(Value::Null),
        );
    }
    let result:Option<(String,String)>=sqlx::query_as("select p.reference,f.sha256 from capability_preparation p join powerpoint_file f on f.id=p.file_id where p.state='ready' and f.status='stored' and p.runtime_id=$2 and ((p.agent_instance_id=$1 and p.configuration_revision=$3) or (p.agent_instance_id is null and f.space_id=$4 and f.effective and not exists(select 1 from powerpoint_file own where own.agent_instance_id=$1 and own.status='stored'))) order by p.agent_instance_id is null,p.created_at desc,p.id desc limit 1")
        .bind(record.agent_instance_id).bind(&record.source_runtime_id).bind(record.configuration_revision).bind(organization).fetch_optional(&mut **tx).await?;
    if let Some((reference, sha)) = result
        && let Some(config) = record
            .tuning
            .0
            .pointer_mut("/capability_config/ppt_builder/config")
            .and_then(Value::as_object_mut)
    {
        config.insert("analysis_id".into(), Value::String(reference));
        config.insert("template_sha256".into(), Value::String(sha));
    }
    Ok(())
}
