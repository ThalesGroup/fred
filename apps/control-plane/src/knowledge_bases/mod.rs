// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Managed mirrors: durable admission, with source collection owned by the runtime.
mod configuration;
pub mod dispatch;
pub(crate) mod documents;
mod http;
pub(crate) use http::routes;

use crate::{
    api::AppState,
    auth::CurrentUser,
    error::{AppError, AppResult},
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgConnection, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Clone, Debug, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
#[schema(as = KnowledgeBaseConfig)]
pub struct Config {
    #[serde(default)]
    pub workers: std::collections::BTreeMap<String, crate::processing::config::WorkerIdentity>,
    #[serde(default)]
    pub credentials: Vec<CredentialBinding>,
}

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
#[schema(as = KnowledgeBaseCredentialBinding)]
pub struct CredentialBinding {
    pub runtime_id: String,
    pub space_id: Uuid,
    pub credential_binding: String,
}

pub(crate) fn worker(s: &AppState, user: &CurrentUser, runtime: &str) -> AppResult<()> {
    let expected = s
        .agent_catalog
        .knowledge_bases
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
pub(crate) fn queue(installation: Uuid, runtime: &str, definition: &str) -> String {
    let owner = Uuid::new_v5(&installation, runtime.as_bytes());
    format!(
        "knowledge-base-{}",
        Uuid::new_v5(&owner, definition.as_bytes())
    )
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
#[schema(as = KnowledgeBaseRun)]
pub struct Run {
    pub id: Uuid,
    pub instance_id: Uuid,
    pub runtime_id: String,
    pub definition_id: String,
    pub space_id: Uuid,
    pub folder_id: Uuid,
    #[schema(value_type = Object)]
    pub config: Json<Value>,
    #[schema(value_type = Object)]
    pub credential_refs: Json<Value>,
    pub profile: String,
    pub state: String,
    pub deadline_at: DateTime<Utc>,
    pub error_code: Option<String>,
    #[schema(value_type=Option<Object>)]
    pub result: Option<Json<Value>>,
}
pub(crate) const RUN_SELECT: &str = "select id,instance_id,runtime_id,definition_id,space_id,folder_id,config,credential_refs,profile,state,deadline_at,error_code,result from kb_run";
pub(crate) async fn run(conn: &mut PgConnection, id: Uuid) -> AppResult<Run> {
    sqlx::query_as(sqlx::AssertSqlSafe(format!("{RUN_SELECT} where id=$1")))
        .bind(id)
        .fetch_optional(conn)
        .await?
        .ok_or(AppError::NotFound)
}
pub(crate) async fn authorize_run(s: &AppState, user: &CurrentUser, id: Uuid) -> AppResult<Run> {
    let row = run(&mut *s.pool.acquire().await?, id).await?;
    worker(s, user, &row.runtime_id)?;
    Ok(row)
}
/// Caller holds the owning organization lock, as for document mutations.
pub(crate) async fn ensure_run_active(conn: &mut PgConnection, id: Uuid) -> AppResult<Run> {
    let row = run(conn, id).await?;
    let live:bool=sqlx::query_scalar("select exists(select 1 from kb_instance i join space s on s.id=i.space_id join space o on o.id=s.organization_id left join space p on p.id=s.parent_id join folder f on f.id=i.folder_id where i.id=$1 and s.deletion_id is null and o.deletion_id is null and (p.id is null or p.deletion_id is null) and f.deletion_id is null)").bind(row.instance_id).fetch_one(&mut *conn).await?;
    if !live
        || !matches!(row.state.as_str(), "pending" | "running")
        || row.deadline_at <= Utc::now()
    {
        return Err(AppError::Conflict(
            "Knowledge base run is no longer active.".into(),
        ));
    }
    Ok(row)
}

pub(crate) async fn enqueue(
    conn: &mut PgConnection,
    s: &AppState,
    instance: Uuid,
    request_key: &str,
    actor: &str,
) -> AppResult<Run> {
    // Both manual and scheduled admission hold the organization lock first.
    // Serialize the idempotency lookup with creation, rather than relying on a
    // uniqueness error after another caller has already admitted this request.
    sqlx::query_scalar::<_, Uuid>("select id from kb_instance where id=$1 for update")
        .bind(instance)
        .fetch_optional(&mut *conn)
        .await?
        .ok_or(AppError::NotFound)?;
    if let Some(id) = sqlx::query_scalar::<_, Uuid>(
        "select id from kb_run where instance_id=$1 and request_key=$2",
    )
    .bind(instance)
    .bind(request_key)
    .fetch_optional(&mut *conn)
    .await?
    {
        return run(conn, id).await;
    }
    let (space_id,runtime,definition,paused):(Uuid,String,String,bool)=sqlx::query_as("select i.space_id,d.runtime_id,d.id,i.paused from kb_instance i join kb_definition d on d.id=i.definition_id where i.id=$1").bind(instance).fetch_optional(&mut *conn).await?.ok_or(AppError::NotFound)?;
    let space: crate::domain::Space = crate::db::space(&mut *conn, space_id).await?.into();
    let live: bool = sqlx::query_scalar("select exists(select 1 from kb_instance i join folder f on f.id=i.folder_id join space s on s.id=i.space_id join space o on o.id=s.organization_id left join space p on p.id=s.parent_id where i.id=$1 and f.deletion_id is null and s.deletion_id is null and o.deletion_id is null and (p.id is null or p.deletion_id is null))").bind(instance).fetch_one(&mut *conn).await?;
    if !live {
        return Err(AppError::Conflict(
            "Knowledge base scope is retired.".into(),
        ));
    }

    let policy = crate::agents::enablement::Policy::load_for_space(&mut *conn, &space).await?;
    let advertised: bool = sqlx::query_scalar(
        "select advertised from capability_offer where source_id=$1 and capability_id=$2 for share",
    )
    .bind(&runtime)
    .bind(format!("knowledge-base:{definition}"))
    .fetch_one(&mut *conn)
    .await?;
    if paused
        || !advertised
        || s.agent_catalog
            .runtime_catalog_sources
            .iter()
            .any(|r| r.runtime_id == runtime && !r.enabled)
        || !s
            .agent_catalog
            .knowledge_bases
            .workers
            .contains_key(&runtime)
        || !crate::agents::enablement::usable(
            &policy,
            &space,
            &runtime,
            &format!("knowledge-base:{definition}"),
        )
    {
        return Err(AppError::Forbidden);
    }
    if s.processing.is_none() {
        return Err(crate::processing::unavailable());
    }
    let active:bool=sqlx::query_scalar("select exists(select 1 from kb_run where instance_id=$1 and state in ('pending','running'))").bind(instance).fetch_one(&mut *conn).await?;
    if active {
        return Err(AppError::Conflict(
            "A knowledge base run is already active.".into(),
        ));
    }
    let installation: Uuid =
        sqlx::query_scalar("select namespace from document_storage where singleton")
            .fetch_one(&mut *conn)
            .await?;
    let id = Uuid::new_v4();
    sqlx::query("insert into kb_run(id,instance_id,runtime_id,definition_id,space_id,folder_id,config,credential_refs,profile,request_key,requested_by,workflow_id,task_queue) select $1,i.id,$2,i.definition_id,i.space_id,i.folder_id,i.config,i.credential_refs,i.profile,$3,$4,$5,$6 from kb_instance i where i.id=$7")
        .bind(id).bind(&runtime).bind(request_key).bind(actor).bind(format!("knowledge-base-{installation}-{id}")).bind(queue(installation,&runtime,&definition)).bind(instance).execute(&mut *conn).await?;
    sqlx::query("update kb_instance set next_run_at=case when interval_seconds is null then null else clock_timestamp()+make_interval(secs=>interval_seconds) end where id=$1").bind(instance).execute(&mut *conn).await?;
    run(conn, id).await
}
