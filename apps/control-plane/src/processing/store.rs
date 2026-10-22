// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{Processing, conflict, models::*};
use crate::{
    db,
    domain::Permission,
    error::{AppError, AppResult},
    onboarding, spaces,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{Postgres, Transaction, types::Json};
use uuid::Uuid;

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Generation {
    pub id: Uuid,
    pub execution_id: Uuid,
    pub activity_id: Uuid,
    pub attempt: u32,
    pub stage: Stage,
    pub expires_at: DateTime<Utc>,
    pub manifest: Option<Manifest>,
    pub reserved_bytes: i64,
    pub cleaned: bool,
    #[serde(default)]
    pub chunks: u32,
    #[serde(default)]
    pub cleanup_cursor: u32,
    pub cleanup_at: Option<DateTime<Utc>>,
}
#[derive(Clone, sqlx::FromRow)]
pub struct Row {
    #[sqlx(flatten)]
    pub summary: Summary,
    pub request_key: Uuid,
    pub actor: String,
    pub installation_id: Uuid,
    pub organization_id: Uuid,
    pub space_id: Uuid,
    pub original_sha256: String,
    pub workflow_id: String,
    pub submission: Json<serde_json::Value>,
    pub run_id: Option<String>,
    pub first_dispatch_at: Option<DateTime<Utc>>,
    pub delivered_at: Option<DateTime<Utc>>,
    pub deadline_at: DateTime<Utc>,
    pub profile_settings: Json<serde_json::Value>,
    pub generations: Json<Vec<Generation>>,
    pub manifest: Option<Json<Manifest>>,
}
impl Row {
    pub fn work(&self) -> Work {
        Work {
            contract_version: 1,
            installation_id: self.installation_id,
            processing_id: self.summary.id,
            document_id: self.summary.document_id,
            original_sha256: self.original_sha256.clone(),
            profile: self.summary.profile,
        }
    }
    pub fn bind(&self, work: &Work) -> AppResult<()> {
        work.validate()?;
        if serde_json::to_value(self.work()).ok() != serde_json::to_value(work).ok() {
            return Err(AppError::NotFound);
        }
        Ok(())
    }
    pub fn prefix(&self, root: &str, generation: Uuid) -> String {
        format!(
            "{}{}/output/{}/{}/{generation}/",
            if root.is_empty() {
                String::new()
            } else {
                format!("{root}/")
            },
            self.summary.document_id,
            self.installation_id,
            self.summary.id
        )
    }
}
pub async fn row(pool: &sqlx::PgPool, id: Uuid) -> AppResult<Row> {
    Ok(
        sqlx::query_as("select * from document_processing where id=$1")
            .bind(id)
            .fetch_one(pool)
            .await?,
    )
}
pub async fn summaries<'e, E>(
    executor: E,
    ids: &[Uuid],
) -> AppResult<std::collections::HashMap<Uuid, Summary>>
where
    E: sqlx::Executor<'e, Database = Postgres>,
{
    let rows:Vec<Summary>=sqlx::query_as("select distinct on(document_id) * from document_processing where document_id=any($1) order by document_id,created_at desc,id desc").bind(ids).fetch_all(executor).await?;
    Ok(rows.into_iter().map(|s| (s.document_id, s)).collect())
}
impl Processing {
    /// Called in the original's guarded publication transaction, or an explicit writer transaction.
    pub async fn admit(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        actor: &str,
        key: Uuid,
        document_id: Uuid,
        org: Uuid,
        start: &Start,
    ) -> AppResult<Summary> {
        if !self.config.enabled {
            return Err(super::unavailable());
        }
        sqlx::query("select pg_advisory_xact_lock(991,hashtext($1))")
            .bind(document_id.to_string())
            .execute(&mut **tx)
            .await?;
        let document = db::document(&mut **tx, document_id).await?;
        sqlx::query("select singleton from document_storage where singleton for update")
            .execute(&mut **tx)
            .await?;
        if let Some(existing) = sqlx::query_as::<_, Row>(
            "select * from document_processing where actor=$1 and request_key=$2",
        )
        .bind(actor)
        .bind(key)
        .fetch_optional(&mut **tx)
        .await?
        {
            if existing.summary.document_id != document_id
                || existing.summary.profile != start.profile
                || existing.summary.retry_of != start.retry_of
            {
                return Err(conflict("idempotency_conflict"));
            }
            return Ok(existing.summary);
        }
        if let Some(previous) = start.retry_of {
            let old: Row =
                sqlx::query_as("select * from document_processing where id=$1 for update")
                    .bind(previous)
                    .fetch_one(&mut **tx)
                    .await?;
            if old.summary.document_id != document_id
                || old.summary.status != ProcessingStatus::Failed
            {
                return Err(conflict("invalid_retry"));
            }
            if let Some(next) =
                sqlx::query_as::<_, Summary>("select * from document_processing where retry_of=$1")
                    .bind(previous)
                    .fetch_optional(&mut **tx)
                    .await?
            {
                let _ = next;
                return Err(conflict("retry_superseded"));
            }
        }
        if let Some(active)=sqlx::query_as::<_,Summary>("select * from document_processing where document_id=$1 and status in ('pending','running','succeeded')").bind(document_id).fetch_optional(&mut **tx).await? {
            let _=active; return Err(conflict("processing_exists"));
        }
        if start.retry_of.is_none()
            && sqlx::query_scalar::<_, bool>(
                "select exists(select 1 from document_processing where document_id=$1)",
            )
            .bind(document_id)
            .fetch_one(&mut **tx)
            .await?
        {
            return Err(conflict("retry_required"));
        }
        let pending: i64 = sqlx::query_scalar(
            "select count(*) from document_processing where status in ('pending','running')",
        )
        .fetch_one(&mut **tx)
        .await?;
        if pending >= self.config.limits.pending as i64 {
            return Err(super::capacity());
        }
        let id = Uuid::new_v4();
        let workflow = format!("manager-document-{}-{id}", self.installation);
        let summary=sqlx::query_as("insert into document_processing(id,request_key,actor,installation_id,document_id,organization_id,space_id,original_sha256,profile,workflow_id,deadline_at,retry_of,submission,profile_settings) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,clock_timestamp()+make_interval(secs=>$11),$12,$13,$14) returning *")
            .bind(id).bind(key).bind(actor).bind(self.installation).bind(document_id).bind(org).bind(document.space_id).bind(document.sha256).bind(start.profile).bind(&workflow).bind(self.config.limits.execution_seconds as f64).bind(start.retry_of).bind(Json(self.contract.submission(self.installation,id,document_id,actor,start.profile,&workflow))).bind(Json(&self.contract.processor_profiles[serde_json::to_value(start.profile).unwrap().as_str().unwrap()])).fetch_one(&mut **tx).await?;
        sqlx::query(
            "update document_upload set acknowledged_at=null where document_id=$1 and actor=$2",
        )
        .bind(document_id)
        .bind(actor)
        .execute(&mut **tx)
        .await?;
        Ok(summary)
    }
    pub async fn start(
        &self,
        actor: &str,
        key: Uuid,
        id: Uuid,
        start: Start,
    ) -> AppResult<Summary> {
        if !self.config.enabled {
            return Err(super::unavailable());
        }
        Box::pin(self.derived.validate_bucket())
            .await
            .map_err(|_| super::unavailable())?;
        let d = db::document(&self.pool, id).await?;
        let space = spaces::load(&self.pool, d.space_id).await?;
        let mut tx = spaces::authorized_write(&self.pool, &self.fga, actor, d.space_id).await?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), actor).await?;
        let summary = self
            .admit(&mut tx, actor, key, id, space.organization, &start)
            .await?;
        tx.commit().await?;
        tracing::info!(target:"fred.security.audit",audit_event="document.processing.accepted",actor_uid=actor,document_id=%id,operation_id=%summary.id,outcome="accepted","Document processing accepted");
        Ok(summary)
    }
    pub(crate) async fn authorize_actor(&self, r: &Row) -> AppResult<()> {
        onboarding::require_accepted(&self.pool, self.terms.as_deref(), &r.actor).await?;
        crate::spaces::authorize(
            &self.pool,
            &self.fga,
            &r.actor,
            r.space_id,
            Permission::Write,
        )
        .await
        .map_err(crate::documents::dependency_error)?;
        Ok(())
    }
    pub async fn history(
        &self,
        actor: &str,
        id: Uuid,
        before: Option<Uuid>,
    ) -> AppResult<Vec<Summary>> {
        let d = db::document(&self.pool, id).await?;
        crate::spaces::authorize(&self.pool, &self.fga, actor, d.space_id, Permission::Read)
            .await
            .map_err(crate::documents::dependency_error)?;
        Ok(sqlx::query_as("select * from document_processing where document_id=$1 and ($2::uuid is null or (created_at,id)<(select created_at,id from document_processing where id=$2 and document_id=$1)) order by created_at desc,id desc limit 50").bind(id).bind(before).fetch_all(&self.pool).await?)
    }
    pub async fn claim(&self, c: Claim) -> AppResult<Descriptor> {
        c.work.validate()?;
        if c.attempt == 0 {
            return Err(invalid());
        }
        if matches!(c.stage, Stage::Queued | Stage::Done) {
            return Err(invalid());
        }
        let r = row(&self.pool, c.work.processing_id).await?;
        r.bind(&c.work)?;
        if c.stage == Stage::Preparation {
            self.authorize_actor(&r).await?;
        }
        let mut tx = self.pool.begin().await?;
        sqlx::query("select singleton from document_storage where singleton for update")
            .execute(&mut *tx)
            .await?;
        let mut r: Row = sqlx::query_as("select * from document_processing where id=$1 for update")
            .bind(c.work.processing_id)
            .fetch_one(&mut *tx)
            .await?;
        r.bind(&c.work)?;
        if r.installation_id != self.installation {
            return Err(crate::error::AppError::NotFound);
        }
        if let Some(g) = r
            .generations
            .iter()
            .find(|g| g.execution_id == c.execution_id && g.stage == c.stage)
            .cloned()
        {
            if g.cleaned
                || (g.manifest.is_none() && g.expires_at <= Utc::now())
                || r.summary.status == ProcessingStatus::Failed
            {
                return Err(conflict("stale_generation"));
            }
            tx.commit().await?;
            return self.descriptor(&r, &g).await;
        }
        if r.summary.status != ProcessingStatus::Failed
            && let Some(g) = r
                .generations
                .iter()
                .find(|g| g.stage == c.stage && g.manifest.is_some() && !g.cleaned)
                .cloned()
        {
            tx.commit().await?;
            return self.descriptor(&r, &g).await;
        }
        if r.summary.status.terminal() || r.deadline_at <= Utc::now() {
            return Err(conflict("processing_terminal"));
        }
        if r.generations
            .iter()
            .any(|g| g.stage == c.stage && g.manifest.is_some())
        {
            return Err(conflict("stage_committed"));
        }
        if let Some(g) = r.generations.last_mut().filter(|g| g.manifest.is_none()) {
            // Temporal owns the attempt ordinal; a newer attempt fences late callbacks immediately.
            if g.activity_id == c.activity_id && g.stage == c.stage && c.attempt > g.attempt {
                g.expires_at = Utc::now();
            } else if g.expires_at > Utc::now()
                || (g.activity_id == c.activity_id && c.attempt <= g.attempt)
            {
                return Err(conflict("stale_generation"));
            }
        }
        let predecessor = r.generations.iter().rev().find(|g| g.manifest.is_some());
        let expected = predecessor.map_or(1, |g| g.stage.ordinal() + 1);
        if c.stage.ordinal() != expected {
            return Err(conflict("stage_order"));
        }
        if r.generations.len() >= self.config.limits.generations as usize {
            return Err(super::capacity());
        }
        let used: i64 = sqlx::query_scalar(
            "select coalesce(sum(reserved_bytes),0)::bigint from document_processing",
        )
        .fetch_one(&mut *tx)
        .await?;
        if used > self.config.limits.derived_bytes - self.config.limits.output_bytes {
            return Err(super::capacity());
        }
        let field = match c.stage {
            Stage::Preparation => "push_metadata_activity_timeout_seconds",
            Stage::Extraction => "input_activity_timeout_seconds",
            Stage::Indexing => "output_activity_timeout_seconds",
            _ => unreachable!(),
        };
        let seconds = r.submission["files"][0][field]
            .as_i64()
            .ok_or_else(invalid)?;
        let g = Generation {
            id: Uuid::new_v4(),
            execution_id: c.execution_id,
            activity_id: c.activity_id,
            attempt: c.attempt,
            stage: c.stage,
            expires_at: (Utc::now() + chrono::Duration::seconds(seconds as i64)).min(r.deadline_at),
            manifest: None,
            reserved_bytes: self.config.limits.output_bytes,
            cleaned: false,
            chunks: 0,
            cleanup_cursor: 0,
            cleanup_at: None,
        };
        r.generations.push(g.clone());
        sqlx::query("update document_processing set status='running',stage=$2,error_code=null,revision=revision+1,generations=$3,reserved_bytes=reserved_bytes+$4 where id=$1")
            .bind(r.summary.id).bind(c.stage).bind(&r.generations).bind(g.reserved_bytes).execute(&mut *tx).await?;
        tx.commit().await?;
        self.descriptor(&r, &g).await
    }
    async fn descriptor(&self, r: &Row, g: &Generation) -> AppResult<Descriptor> {
        let d = db::document(&self.pool, r.summary.document_id).await?;
        let folder = db::folder(&self.pool, d.folder_id.ok_or_else(invalid)?).await?;
        Ok(Descriptor {
            work: r.work(),
            organization_id: r.organization_id,
            space_id: r.space_id,
            folder_id: folder.id,
            folder_path: folder.path,
            name: d.name,
            mime: d.mime,
            size: d.size,
            actor: r.actor.clone(),
            stage: g.stage,
            generation: g.id,
            expires_at: g.expires_at,
            output_prefix: r.prefix(&self.config.derived.prefix, g.id),
            max_output_bytes: self.config.limits.output_bytes,
            max_artifacts: self.config.limits.artifacts,
            max_chunks: self.config.limits.chunks,
            file: r.submission["files"][0].clone(),
            profile_settings: r.profile_settings.0.clone(),
            predecessor: r
                .generations
                .iter()
                .rev()
                .find(|p| p.stage.ordinal() + 1 == g.stage.ordinal() && p.manifest.is_some())
                .and_then(|p| p.manifest.clone()),
            committed: g.manifest.clone(),
        })
    }
    /// Release only this failed activity generation; Temporal retains its retry budget.
    pub async fn abandon(&self, f: Failure) -> AppResult<Summary> {
        let mut tx = self.pool.begin().await?;
        let mut r: Row = sqlx::query_as("select * from document_processing where id=$1 for update")
            .bind(f.work.processing_id)
            .fetch_one(&mut *tx)
            .await?;
        r.bind(&f.work)?;
        let g = r
            .generations
            .last_mut()
            .ok_or_else(|| conflict("stale_generation"))?;
        if r.summary.status.terminal()
            || Some(g.id) != f.generation
            || g.stage != f.stage
            || g.manifest.is_some()
        {
            return Err(conflict("stale_generation"));
        }
        g.expires_at = Utc::now();
        let code = serde_json::to_value(f.code).map_err(|e| AppError::Internal(e.into()))?;
        let summary=sqlx::query_as("update document_processing set generations=$2,error_code=$3,revision=revision+1 where id=$1 returning *")
            .bind(r.summary.id).bind(&r.generations).bind(code.as_str().ok_or_else(invalid)?).fetch_one(&mut *tx).await?;
        tx.commit().await?;
        Ok(summary)
    }
}
