// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! CP-owned originals, not capability preparation or activation. No PowerPoint
//! validation lives here; the owning library must validate before future activation.
use super::{Storage, conflict, unavailable, upload};
use crate::{
    auth::CurrentUser,
    authorization,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    onboarding, spaces,
};
use axum::{extract::Multipart, http::StatusCode};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{Postgres, Transaction};
use utoipa::ToSchema;
use uuid::Uuid;

pub(crate) mod acceptance;
mod http;
pub(crate) mod settings;
pub(crate) use http::routes;

#[derive(Serialize, ToSchema, sqlx::Type, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum PowerPointFileStatus {
    Pending,
    Stored,
    Retired,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PowerPointSource {
    Agent,
    Organization,
    Builtin,
}

pub(crate) struct PowerPointTarget<'a> {
    pub space_id: Uuid,
    pub agent: Option<Uuid>,
    pub runtime: &'a str,
}

pub(crate) enum PowerPointUpload {
    Multipart(Multipart),
    Snapshot { name: String, bytes: Vec<u8> },
}

/// Same original selection as ordinary agent usage; callers authorize the usage space.
pub(crate) async fn snapshot_file(
    conn: &mut sqlx::PgConnection,
    space: &Space,
    agent: Uuid,
    runtime: &str,
) -> AppResult<Option<PowerPointFile>> {
    Ok(resolved_original(conn, space, Some(agent), runtime)
        .await?
        .map(|row| row.file))
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PowerPointFile {
    pub id: Uuid,
    pub request_key: Uuid,
    pub space_id: Uuid,
    #[schema(required = true)]
    pub agent_instance_id: Option<Uuid>,
    #[schema(required = true)]
    pub runtime_id: Option<String>,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub sha256: String,
    /// Stored means attached in CP, not prepared or activated in the pod.
    pub status: PowerPointFileStatus,
    #[schema(required = true)]
    pub published_at: Option<DateTime<Utc>>,
    #[schema(required = true)]
    pub cleaned_at: Option<DateTime<Utc>>,
    #[schema(required = true)]
    pub error_code: Option<String>,
}
#[derive(sqlx::FromRow)]
struct FileRow {
    #[sqlx(flatten)]
    file: PowerPointFile,
    object_key: String,
    expected_file_id: Option<Uuid>,
    actor: String,
    upload_ready: bool,
    expires_at: DateTime<Utc>,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PowerPointChange {
    /// Compare-and-swap: omit only when no own file is currently attached.
    pub expected_file_id: Option<Uuid>,
}
#[derive(Serialize, ToSchema)]
pub struct PowerPointResolution {
    /// agent, organization, or builtin; no configurable platform default.
    pub source: PowerPointSource,
    #[schema(required = true)]
    pub file: Option<PowerPointFile>,
    pub activation_ready: bool,
    pub preparation_state: String,
    #[schema(required = true)]
    pub preparation_error: Option<String>,
    /// Opaque reference owned by the capability on the resolved logical pod.
    #[schema(required = true)]
    pub analysis_reference: Option<String>,
}

async fn resolve_file_preparation<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    file: Option<PowerPointFile>,
    ready_only: bool,
) -> AppResult<PowerPointResolution> {
    let prep: Option<(String, Option<String>, Option<String>)> = if let Some(f) = &file {
        sqlx::query_as("select state,error,reference from capability_preparation where file_id=$1 and runtime_id=$2 and state<>'obsolete' and (not $3 or state='ready') order by created_at desc,id desc limit 1")
            .bind(f.id).bind(&f.runtime_id).bind(ready_only).fetch_optional(ex).await?
    } else {
        None
    };
    let (state, error, reference) = prep.unwrap_or_else(|| {
        (
            if file.is_none() { "ready" } else { "failed" }.into(),
            None,
            None,
        )
    });
    Ok(PowerPointResolution {
        source: match &file {
            Some(f) if f.agent_instance_id.is_some() => PowerPointSource::Agent,
            Some(_) => PowerPointSource::Organization,
            None => PowerPointSource::Builtin,
        },
        activation_ready: state == "ready",
        preparation_state: state,
        preparation_error: error,
        analysis_reference: reference,
        file,
    })
}

async fn target<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: &Space,
    agent: Option<Uuid>,
) -> AppResult<()> {
    match agent {
        Some(id) => {
            crate::agent_instances::get_for_space(ex, space.id, id)
                .await?
                .ok_or(AppError::NotFound)?;
        }
        None if space.kind != SpaceKind::Organization => return Err(AppError::NotFound),
        None => (),
    }
    Ok(())
}
async fn current<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    space: Uuid,
    agent: Option<Uuid>,
    runtime: &str,
) -> AppResult<Option<FileRow>> {
    Ok(sqlx::query_as("select * from powerpoint_file where space_id=$1 and agent_instance_id is not distinct from $2 and status='stored' and runtime_id=$3 order by effective limit 1")
        .bind(space).bind(agent).bind(runtime).fetch_optional(ex).await?)
}
fn unchanged(expected: Option<Uuid>, current: Option<&FileRow>) -> AppResult<()> {
    if expected != current.map(|r| r.file.id) {
        return Err(conflict(
            "powerpoint_file_changed",
            "The saved file changed; reload before replacing or removing it",
        ));
    }
    Ok(())
}
async fn writer(
    pool: &sqlx::PgPool,
    user: &CurrentUser,
    space: Uuid,
    agent: Option<Uuid>,
) -> AppResult<(Transaction<'static, Postgres>, Space)> {
    upload::token_current(user)?;
    let (mut tx, space) = spaces::authorized_mutation(
        pool,
        &user.uid,
        space,
        agent.map_or(Permission::Manage, |_| Permission::Write),
    )
    .await?;
    if let Some(agent) = agent {
        sqlx::query("select agent_instance_id from agent_instance where agent_instance_id=$1 and space_id=$2 for update")
            .bind(agent).bind(space.id).execute(&mut *tx).await?;
    } else {
        // The current organization template may be absent: lock its stable owner before replacement.
        sqlx::query("select id from space where id=$1 for no key update")
            .bind(space.id)
            .execute(&mut *tx)
            .await?;
    }
    target(&mut *tx, &space, agent).await?;
    Ok((tx, space))
}

async fn resolved_original(
    conn: &mut sqlx::PgConnection,
    space: &Space,
    agent: Option<Uuid>,
    runtime: &str,
) -> AppResult<Option<FileRow>> {
    let own = current(&mut *conn, space.id, agent, runtime).await?;
    if own.is_some() || agent.is_none() {
        return Ok(own);
    }
    crate::lifecycle::store::require_active(&mut *conn, space.organization).await?;
    Ok(sqlx::query_as("select * from powerpoint_file where space_id=$1 and runtime_id=$2 and agent_instance_id is null and status='stored' and effective")
        .bind(space.organization).bind(runtime).fetch_optional(conn).await?)
}

impl Storage {
    pub(crate) async fn upload_powerpoint(
        &self,
        user: &CurrentUser,
        usage: PowerPointTarget<'_>,
        key: Uuid,
        change: PowerPointChange,
        input: PowerPointUpload,
        draft: bool,
    ) -> AppResult<PowerPointFile> {
        let PowerPointTarget {
            space_id,
            agent,
            runtime,
        } = usage;
        if !self.config.uploads_enabled {
            return Err(unavailable());
        }
        let _permit = self.uploads.clone().try_acquire_owned().map_err(|_| {
            AppError::problem(
                StatusCode::TOO_MANY_REQUESTS,
                "transfer_capacity",
                "All transfer slots are busy",
            )
        })?;
        let permission = agent.map_or(Permission::Manage, |_| Permission::Write);
        let space = authorization::authorize(&self.pool, &user.uid, space_id, permission).await?;
        if !draft {
            target(&self.pool, &space, agent).await?;
        }
        let spool = tokio::time::timeout(self.deadline(), async {
            match input {
                PowerPointUpload::Multipart(multipart) => self.spool(multipart).await,
                PowerPointUpload::Snapshot { name, bytes } => {
                    self.spool_bytes(
                        &name,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                        &bytes,
                    )
                    .await
                }
            }
        })
        .await
        .map_err(|_| unavailable())??;
        let mut replayed = false;
        let row = loop {
            let (mut tx, space) =
                spaces::authorized_mutation(&self.pool, &user.uid, space_id, permission).await?;
            let result: AppResult<FileRow> = async {
                if draft {
                    let exists: bool = sqlx::query_scalar(
                        "select exists(select 1 from agent_instance where agent_instance_id=$1)",
                    )
                    .bind(agent)
                    .fetch_one(&mut *tx)
                    .await?;
                    if exists || agent.is_none() {
                        return Err(AppError::Conflict("Draft identity already exists".into()));
                    }
                } else {
                    target(&mut *tx, &space, agent).await?;
                }
                if spool.size > 50 * 1024 * 1024 {
                    return Err(super::invalid("PowerPoint file exceeds 50 MB"));
                }
                onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &user.uid).await?;
                let existing: Option<FileRow> =
                    sqlx::query_as("select * from powerpoint_file where actor=$1 and request_key=$2")
                        .bind(&user.uid)
                        .bind(key)
                        .fetch_optional(&mut *tx)
                        .await?;
                let row = if let Some(row) = existing {
                    if row.file.space_id != space_id
                        || row.file.agent_instance_id != agent
                        || row.file.name != spool.name
                        || row.file.mime != spool.mime
                        || row.file.size != spool.size
                        || row.file.sha256 != spool.sha256()
                        || row.expected_file_id != change.expected_file_id
                        || row.file.runtime_id.as_deref() != Some(runtime)
                    {
                        return Err(conflict(
                            "idempotency_conflict",
                            "The request key identifies different content or ownership",
                        ));
                    }
                    if row.file.published_at.is_some() {
                        return Ok(row);
                    }
                    if row.file.status != PowerPointFileStatus::Pending || row.expires_at <= Utc::now() {
                        return Err(conflict(
                            "upload_expired",
                            "This attempt is retired; use a new request key",
                        ));
                    }
                    row
                } else {
                    unchanged(
                        change.expected_file_id,
                        current(&mut *tx, space_id, agent, runtime).await?.as_ref(),
                    )?;
                    let (owner, _) = self.quota(&space)?;
                    self.ensure_budgets(&mut tx, &space).await?;

                    self.require_cleanup_capacity(&mut *tx).await?;
                    let id = Uuid::new_v4();
                    let object_key = format!("{}{id}/input/{}", self.prefix, spool.name);
                    if object_key.len() > 1024 {
                        return Err(super::invalid("The object key is too long"));
                    }
                    // The database runs local and organization used-byte and reservation accounting.
                    sqlx::query_as("insert into powerpoint_file (id,request_key,actor,organization_id,space_id,agent_instance_id,live_space_id,live_agent_id,quota_owner,expected_file_id,name,mime,size,sha256,object_key,status,expires_at,cleanup_due_at,runtime_id) values ($1,$2,$3,$4,$5,$6,$5,$15,$7,$8,$9,$10,$11,$12,$13,'pending',clock_timestamp()+make_interval(secs=>$14),clock_timestamp()+make_interval(secs=>$14),$16) returning *")
                        .bind(id).bind(key).bind(&user.uid).bind(space.organization).bind(space_id).bind(agent).bind(owner).bind(change.expected_file_id)
                        .bind(&spool.name).bind(&spool.mime).bind(spool.size).bind(spool.sha256()).bind(object_key).bind(self.config.limits.lease_seconds() as f64).bind(if draft {None}else{agent}).bind(runtime)
                        .fetch_one(&mut *tx).await?
                };
                Ok(row)
            }
            .await;
            match result {
                Ok(row) => {
                    tx.commit().await?;
                    break row;
                }
                Err(error) => {
                    tx.rollback().await?;
                    if !replayed
                        && sqlx::query_scalar::<_, bool>(
                            "select exists(select 1 from powerpoint_file where actor=$1 and request_key=$2)",
                        )
                        .bind(&user.uid)
                        .bind(key)
                        .fetch_one(&self.pool)
                        .await?
                    {
                        replayed = true;
                        continue;
                    }
                    return Err(error);
                }
            }
        };
        if row.file.published_at.is_some() {
            return Ok(row.file);
        }
        // Immutable conditional PUT permits replay after a lost response or a crash.
        // SQL has released its locks and connection for the entire network transfer.
        let (_, written) = self
            .objects
            .put_file(&row.object_key, spool.file, spool.size, &spool.digest)
            .await;
        written.map_err(|_| unavailable())?;
        self.objects
            .verify(&row.object_key, spool.size, &spool.digest)
            .await
            .map_err(|_| unavailable())?;
        // Staging never replaces the saved attachment. Acceptance belongs to the
        // configuration transaction after bounded capability preflight.
        // The database runs local and organization used-byte and reservation accounting.
        let file = sqlx::query_as("update powerpoint_file set upload_ready=true where id=$1 and status='pending' and expires_at>clock_timestamp() returning *")
            .bind(row.file.id).fetch_optional(&self.pool).await?.ok_or_else(|| conflict("upload_expired", "The upload expired before acceptance"))?;
        Ok(file)
    }

    pub(crate) async fn preparation_file(&self, file: Uuid) -> AppResult<axum::response::Response> {
        let row: FileRow = sqlx::query_as("select * from powerpoint_file where id=$1 and status in ('pending','stored') and upload_ready")
            .bind(file).fetch_optional(&self.pool).await?.ok_or(AppError::NotFound)?;
        self.stream_file(
            row.file.id,
            &row.object_key,
            &row.file.name,
            row.file.size,
            &row.file.sha256,
        )
        .await
    }

    /// Read authorization is tied to the requesting usage, not a supplied file ID.
    async fn resolve_powerpoint_row(
        &self,
        actor: &str,
        space_id: Uuid,
        agent: Option<Uuid>,
        runtime: &str,
    ) -> AppResult<Option<FileRow>> {
        let mut tx = self.pool.begin().await?;
        sqlx::query("set transaction isolation level repeatable read, read only")
            .execute(&mut *tx)
            .await?;
        let space = authorization::authorize(
            &mut *tx,
            actor,
            space_id,
            agent.map_or(Permission::Manage, |_| Permission::Read),
        )
        .await?;
        target(&mut *tx, &space, agent).await?;
        if let Some(id) = agent {
            let instance = crate::agent_instances::get_for_space(&mut *tx, space_id, id)
                .await?
                .ok_or(AppError::NotFound)?;
            if !authorization::can_use_agent(&mut *tx, instance.template_id, &space).await? {
                return Err(AppError::NotFound);
            }
        }
        let row = resolved_original(&mut tx, &space, agent, runtime).await?;
        tx.commit().await?;
        Ok(row)
    }
    pub async fn resolve_powerpoint(
        &self,
        actor: &str,
        space: Uuid,
        agent: Option<Uuid>,
        runtime: &str,
    ) -> AppResult<PowerPointResolution> {
        let file = self
            .resolve_powerpoint_row(actor, space, agent, runtime)
            .await?
            .map(|r| r.file);
        let inherited =
            agent.is_some() && file.as_ref().is_some_and(|f| f.agent_instance_id.is_none());
        resolve_file_preparation(&self.pool, file, inherited).await
    }

    pub async fn download_powerpoint(
        &self,
        actor: &str,
        space: Uuid,
        agent: Option<Uuid>,
        file: Uuid,
        runtime: &str,
    ) -> AppResult<axum::response::Response> {
        let row = self
            .resolve_powerpoint_row(actor, space, agent, runtime)
            .await?
            .filter(|r| r.file.id == file)
            .ok_or(AppError::NotFound)?;
        self.stream_file(
            row.file.id,
            &row.object_key,
            &row.file.name,
            row.file.size,
            &row.file.sha256,
        )
        .await
    }
    pub async fn remove_powerpoint(
        &self,
        user: &CurrentUser,
        space: Uuid,
        agent: Option<Uuid>,
        change: PowerPointChange,
        runtime: &str,
    ) -> AppResult<()> {
        let (mut tx, _) = writer(&self.pool, user, space, agent).await?;
        let row = current(&mut *tx, space, agent, runtime).await?;
        let changed = row.is_some();
        // Replayed removal is harmless, but cannot remove a subsequent replacement.
        if row.is_some() {
            unchanged(change.expected_file_id, row.as_ref())?;
            // The database releases quota, obsoletes preparations and clears retired template settings.
            sqlx::query("update powerpoint_file set status='retired',cleanup_due_at=greatest(expires_at,clock_timestamp()) where id=$1")
                .bind(row.map(|r| r.file.id)).execute(&mut *tx).await?;
        }
        // The database releases quota, obsoletes preparations and clears retired template settings.
        sqlx::query("update powerpoint_file set status='retired',cleanup_due_at=greatest(expires_at,clock_timestamp()) where space_id=$1 and agent_instance_id is not distinct from $2 and runtime_id=$3 and status in ('pending','stored')")
            .bind(space).bind(agent).bind(runtime).execute(&mut *tx).await?;
        if agent.is_none() {
            sqlx::query("delete from organization_powerpoint_settings where organization_id=$1 and runtime_id=$2")
                .bind(space).bind(runtime).execute(&mut *tx).await?;
        }
        if let Some(agent) = agent
            && changed
        {
            sqlx::query("update agent_instance set configuration_revision=configuration_revision+1,preparation_id=null,preparation_state='ready',preparation_error=null where agent_instance_id=$1")
                .bind(agent).execute(&mut *tx).await?;
        }
        tx.commit().await?;
        Ok(())
    }
}
