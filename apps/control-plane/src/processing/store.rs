// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Processing requests and their generations. A generation's stored prefix is the only
//! location any reader uses for its artifacts.
use super::{Processing, conflict, models::*};
use crate::{
    db,
    domain::Permission,
    error::{AppError, AppResult},
    onboarding, spaces,
};
use chrono::{DateTime, Utc};
use sqlx::{Postgres, Transaction, types::Json};
use uuid::Uuid;

/// Published counts come from the document's official generation, never a failed attempt.
macro_rules! summary_from {
    () => {
        "p.id, p.document_id, p.profile, p.status, p.stage, p.revision, p.error_code, p.created_at, p.completed_at, p.retry_of, coalesce(cardinality(g.vector_ordinals), 0)::bigint as chunks, coalesce(cardinality(g.vector_ordinals), 0)::bigint as vectors, g.rows from document_processing p join document d on d.id = p.document_id left join generation g on g.id = d.published_generation and g.processing_id = p.id"
    };
}
macro_rules! row {
    () => {
        "select p.*, p.submission->'files'->0 as file, d.sha256 as original_sha256, d.space_id, d.session_id, s.organization_id, d.published_generation, d.deletion_id is not null as retired, coalesce(cardinality(g.vector_ordinals), 0)::bigint as chunks, coalesce(cardinality(g.vector_ordinals), 0)::bigint as vectors, g.rows from document_processing p join document d on d.id = p.document_id join space s on s.id = d.space_id left join generation g on g.id = d.published_generation and g.processing_id = p.id"
    };
}

#[derive(Clone, Debug, sqlx::FromRow)]
pub struct Generation {
    pub id: Uuid,
    pub processing_id: Uuid,
    pub stage: Stage,
    pub execution_id: Uuid,
    pub activity_id: Uuid,
    pub attempt: i32,
    pub expires_at: DateTime<Utc>,
    pub prefix: String,
    pub committed_at: Option<DateTime<Utc>>,
    /// Vector ordinals this attempt may write, journaled before each write.
    pub chunks: i32,
    pub vector_ordinals: Option<Vec<i32>>,
    pub rows: Option<i64>,
    pub cleanup_cursor: i32,
    pub cleaned_at: Option<DateTime<Utc>>,
}

/// A request joined with its document. The submission is forwarded unread; only its
/// file entry is projected for the worker descriptor.
#[derive(Clone, sqlx::FromRow)]
pub struct Row {
    #[sqlx(flatten)]
    pub summary: Summary,
    pub actor: String,
    pub original_sha256: String,
    pub space_id: Uuid,
    pub session_id: Option<Uuid>,
    pub organization_id: Uuid,
    pub workflow_id: String,
    pub run_id: Option<String>,
    pub deadline_at: DateTime<Utc>,
    pub file: Json<serde_json::Value>,
    pub profile_settings: Json<serde_json::Value>,
    pub preparation_seconds: i32,
    pub extraction_seconds: i32,
    pub indexing_seconds: i32,
    pub published_generation: Option<Uuid>,
    pub retired: bool,
}
impl Row {
    pub fn work(&self, installation: Uuid) -> Work {
        Work {
            contract_version: 1,
            installation_id: installation,
            processing_id: self.summary.id,
            document_id: self.summary.document_id,
            original_sha256: self.original_sha256.clone(),
            profile: self.summary.profile,
        }
    }
    pub fn bind(&self, installation: Uuid, work: &Work) -> AppResult<()> {
        work.validate()?;
        if self.work(installation) != *work {
            return Err(AppError::NotFound);
        }
        Ok(())
    }
    fn lease(&self, stage: Stage) -> AppResult<i64> {
        Ok(i64::from(match stage {
            Stage::Preparation => self.preparation_seconds,
            Stage::Extraction => self.extraction_seconds,
            Stage::Indexing => self.indexing_seconds,
            Stage::Queued | Stage::Done => return Err(invalid()),
        }))
    }
    /// Cleanup removed this generation's objects; the published one always keeps them.
    pub fn objects_gone(&self, g: &Generation) -> bool {
        g.cleaned_at.is_some() && self.published_generation != Some(g.id)
    }
}

/// `{root}/{document_id}/output/`: every derived object of a document, never its input.
pub fn document_output(root: &str, document: Uuid) -> String {
    if root.is_empty() {
        format!("{document}/output/")
    } else {
        format!("{root}/{document}/output/")
    }
}

pub async fn row<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> AppResult<Row> {
    Ok(sqlx::query_as(concat!(row!(), " where p.id = $1"))
        .bind(id)
        .fetch_one(ex)
        .await?)
}
/// Every generation change is ordered by this lock on its processing row.
pub(crate) async fn locked(tx: &mut Transaction<'_, Postgres>, id: Uuid) -> AppResult<Row> {
    Ok(
        sqlx::query_as(concat!(row!(), " where p.id = $1 for update of p"))
            .bind(id)
            .fetch_one(&mut **tx)
            .await?,
    )
}
pub async fn summary<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> AppResult<Summary> {
    Ok(
        sqlx::query_as(concat!("select ", summary_from!(), " where p.id = $1"))
            .bind(id)
            .fetch_one(ex)
            .await?,
    )
}
pub async fn summaries<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    ids: &[Uuid],
) -> AppResult<std::collections::HashMap<Uuid, Summary>> {
    let rows: Vec<Summary> = sqlx::query_as(concat!(
        "select distinct on (p.document_id) ",
        summary_from!(),
        " where p.document_id = any($1) order by p.document_id, p.created_at desc, p.id desc"
    ))
    .bind(ids)
    .fetch_all(ex)
    .await?;
    Ok(rows.into_iter().map(|s| (s.document_id, s)).collect())
}
pub async fn generations<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    processing: Uuid,
) -> AppResult<Vec<Generation>> {
    Ok(
        sqlx::query_as("select * from generation where processing_id = $1 order by created_at, id")
            .bind(processing)
            .fetch_all(ex)
            .await?,
    )
}
pub async fn latest<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    processing: Uuid,
) -> AppResult<Option<Generation>> {
    Ok(sqlx::query_as(
        "select * from generation where processing_id = $1 order by created_at desc, id desc limit 1",
    )
    .bind(processing)
    .fetch_optional(ex)
    .await?)
}
/// The committed result of a generation, artifacts sorted by path.
pub async fn manifest<'e>(ex: impl sqlx::PgExecutor<'e>, g: &Generation) -> AppResult<Manifest> {
    let ordinals = g.vector_ordinals.as_ref().ok_or_else(invalid)?;
    let mut artifacts: Vec<Artifact> =
        sqlx::query_as("select path, size, sha256 from artifact where generation_id = $1")
            .bind(g.id)
            .fetch_all(ex)
            .await?;
    artifacts.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(Manifest {
        generation: g.id,
        artifacts,
        chunks: ordinals.len() as i64,
        vectors: ordinals.len() as i64,
        vector_ordinals: ordinals.iter().map(|v| *v as u32).collect(),
        rows: g.rows,
    })
}

impl Processing {
    /// Called in the original's guarded publication transaction, or an explicit writer transaction.
    pub async fn admit(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        actor: &str,
        key: Uuid,
        document_id: Uuid,
        start: &Start,
    ) -> AppResult<Summary> {
        if !self.config.enabled {
            return Err(super::unavailable());
        }
        sqlx::query("select pg_advisory_xact_lock(991,hashtext($1))")
            .bind(document_id.to_string())
            .execute(&mut **tx)
            .await?;
        db::pipeline_document(&mut **tx, document_id).await?;
        // Serializes admissions so the pending-attempt cap stays exact.
        sqlx::query("select singleton from document_storage where singleton for update")
            .execute(&mut **tx)
            .await?;
        if let Some(existing) = sqlx::query_as::<_, Summary>(concat!(
            "select ",
            summary_from!(),
            " where p.actor = $1 and p.request_key = $2"
        ))
        .bind(actor)
        .bind(key)
        .fetch_optional(&mut **tx)
        .await?
        {
            if existing.document_id != document_id
                || existing.profile != start.profile
                || existing.retry_of != start.retry_of
            {
                return Err(conflict("idempotency_conflict"));
            }
            return Ok(existing);
        }
        if let Some(previous) = start.retry_of {
            let (old_document, old_status): (Uuid, ProcessingStatus) = sqlx::query_as(
                "select document_id, status from document_processing where id=$1 for update",
            )
            .bind(previous)
            .fetch_one(&mut **tx)
            .await?;
            if old_document != document_id || old_status != ProcessingStatus::Failed {
                return Err(conflict("invalid_retry"));
            }
            if sqlx::query_scalar::<_, bool>(
                "select exists(select 1 from document_processing where retry_of=$1)",
            )
            .bind(previous)
            .fetch_one(&mut **tx)
            .await?
            {
                return Err(conflict("retry_superseded"));
            }
        }
        if sqlx::query_scalar::<_, bool>("select exists(select 1 from document_processing where document_id=$1 and status in ('pending','running','succeeded'))").bind(document_id).fetch_one(&mut **tx).await? {
            return Err(conflict("processing_exists"));
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
        let [preparation, extraction, indexing] = self.contract.leases(start.profile);
        sqlx::query("insert into document_processing(id,request_key,actor,document_id,profile,workflow_id,deadline_at,retry_of,submission,profile_settings,preparation_seconds,extraction_seconds,indexing_seconds) values($1,$2,$3,$4,$5,$6,clock_timestamp()+make_interval(secs=>$7),$8,$9,$10,$11,$12,$13)")
            .bind(id).bind(key).bind(actor).bind(document_id).bind(start.profile).bind(&workflow).bind(self.config.limits.execution_seconds as f64).bind(start.retry_of).bind(Json(self.contract.submission(self.installation,id,document_id,actor,start.profile,&workflow))).bind(Json(&self.contract.processor_profiles[start.profile.as_str()])).bind(preparation).bind(extraction).bind(indexing).execute(&mut **tx).await?;
        // Sent only if this transaction commits; the dispatcher's poll covers a missed wake-up.
        sqlx::query("select pg_notify($1, '')")
            .bind(super::dispatch::WAKE_CHANNEL)
            .execute(&mut **tx)
            .await?;
        sqlx::query(
            "update document_upload set acknowledged_at=null where id=$1 and status='stored' and actor=$2",
        )
        .bind(document_id)
        .bind(actor)
        .execute(&mut **tx)
        .await?;
        summary(&mut **tx, id).await
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
        let mut tx = spaces::authorized_write(&self.pool, &self.fga, actor, d.space_id).await?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), actor).await?;
        let summary = self.admit(&mut tx, actor, key, id, &start).await?;
        tx.commit().await?;
        tracing::info!(target:"fred.security.audit",audit_event="document.processing.accepted",actor_uid=actor,document_id=%id,operation_id=%summary.id,outcome="accepted","Document processing accepted");
        Ok(summary)
    }
    pub(crate) async fn authorize_actor(&self, r: &Row) -> AppResult<()> {
        onboarding::require_accepted(&self.pool, self.terms.as_deref(), &r.actor).await?;
        let tx = crate::documents::authorized_mutation(
            &self.pool,
            &self.fga,
            &r.actor,
            r.space_id,
            r.session_id,
        )
        .await
        .map_err(crate::documents::dependency_error)?;
        tx.commit().await?;
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
        Ok(sqlx::query_as(concat!("select ", summary_from!(), " where p.document_id=$1 and ($2::uuid is null or (p.created_at,p.id)<(select created_at,id from document_processing where id=$2 and document_id=$1)) order by p.created_at desc,p.id desc limit 50")).bind(id).bind(before).fetch_all(&self.pool).await?)
    }
    pub async fn claim(&self, c: Claim) -> AppResult<Descriptor> {
        c.work.validate()?;
        let attempt = i32::try_from(c.attempt)
            .ok()
            .filter(|a| *a > 0)
            .ok_or_else(invalid)?;
        if matches!(c.stage, Stage::Queued | Stage::Done) {
            return Err(invalid());
        }
        let r = row(&self.pool, c.work.processing_id).await?;
        r.bind(self.installation, &c.work)?;
        if c.stage == Stage::Preparation {
            self.authorize_actor(&r).await?;
        }
        // Only this processing row is locked: claims of different documents never wait.
        let mut tx = self.pool.begin().await?;
        let r = locked(&mut tx, c.work.processing_id).await?;
        r.bind(self.installation, &c.work)?;
        let generations = generations(&mut *tx, r.summary.id).await?;
        let now = Utc::now();
        if let Some(g) = generations
            .iter()
            .find(|g| g.execution_id == c.execution_id && g.stage == c.stage)
        {
            if r.objects_gone(g)
                || (g.committed_at.is_none() && g.expires_at <= now)
                || r.summary.status == ProcessingStatus::Failed
            {
                return Err(conflict("stale_generation"));
            }
            tx.commit().await?;
            return self.descriptor(&r, &generations, g).await;
        }
        if r.summary.status != ProcessingStatus::Failed
            && let Some(g) = generations
                .iter()
                .find(|g| g.stage == c.stage && g.committed_at.is_some() && !r.objects_gone(g))
        {
            tx.commit().await?;
            return self.descriptor(&r, &generations, g).await;
        }
        if r.summary.status.terminal() || r.deadline_at <= now {
            return Err(conflict("processing_terminal"));
        }
        if generations
            .iter()
            .any(|g| g.stage == c.stage && g.committed_at.is_some())
        {
            return Err(conflict("stage_committed"));
        }
        if let Some(g) = generations.last().filter(|g| g.committed_at.is_none()) {
            // Temporal owns the attempt ordinal; a newer attempt fences late callbacks immediately.
            if g.activity_id == c.activity_id && g.stage == c.stage && attempt > g.attempt {
                sqlx::query("update generation set expires_at=least(expires_at,$2) where id=$1")
                    .bind(g.id)
                    .bind(now)
                    .execute(&mut *tx)
                    .await?;
            } else if g.expires_at > now || (g.activity_id == c.activity_id && attempt <= g.attempt)
            {
                return Err(conflict("stale_generation"));
            }
        }
        let predecessor = generations.iter().rev().find(|g| g.committed_at.is_some());
        let expected = predecessor.map_or(1, |g| g.stage.ordinal() + 1);
        if c.stage.ordinal() != expected {
            return Err(conflict("stage_order"));
        }
        let id = Uuid::new_v4();
        let expires = (now + chrono::Duration::seconds(r.lease(c.stage)?)).min(r.deadline_at);
        let prefix = format!(
            "{}{id}/",
            document_output(&self.config.derived.prefix, r.summary.document_id)
        );
        let g: Generation = sqlx::query_as("insert into generation(id,processing_id,stage,execution_id,activity_id,attempt,expires_at,prefix,cleanup_after) values($1,$2,$3,$4,$5,$6,$7,$8,$7 + interval '60 seconds') returning *")
            .bind(id).bind(r.summary.id).bind(c.stage).bind(c.execution_id).bind(c.activity_id).bind(attempt).bind(expires).bind(prefix).fetch_one(&mut *tx).await?;
        sqlx::query("update document_processing set status='running',stage=$2,error_code=null,revision=revision+1 where id=$1")
            .bind(r.summary.id).bind(c.stage).execute(&mut *tx).await?;
        tx.commit().await?;
        self.descriptor(&r, &generations, &g).await
    }
    async fn descriptor(
        &self,
        r: &Row,
        generations: &[Generation],
        g: &Generation,
    ) -> AppResult<Descriptor> {
        let d = db::pipeline_document(&self.pool, r.summary.document_id).await?;
        let folder = match (d.folder_id, r.session_id) {
            (Some(id), None) => Some(db::folder(&self.pool, id).await?),
            (None, Some(_)) => None,
            _ => return Err(invalid()),
        };
        let predecessor = match generations
            .iter()
            .rev()
            .find(|p| p.stage.ordinal() + 1 == g.stage.ordinal() && p.committed_at.is_some())
        {
            Some(p) => Some(Predecessor {
                prefix: p.prefix.clone(),
                manifest: manifest(&self.pool, p).await?,
            }),
            None => None,
        };
        let committed = match g.committed_at {
            Some(_) => Some(manifest(&self.pool, g).await?),
            None => None,
        };
        Ok(Descriptor {
            work: r.work(self.installation),
            organization_id: r.organization_id,
            space_id: r.space_id,
            folder_id: d.folder_id,
            folder_path: folder.map(|f| f.path),
            session_id: r.session_id,
            name: d.name,
            mime: d.mime,
            size: d.size,
            actor: r.actor.clone(),
            stage: g.stage,
            generation: g.id,
            expires_at: g.expires_at,
            output_prefix: g.prefix.clone(),
            max_output_bytes: self.config.limits.output_bytes,
            max_artifacts: self.config.limits.artifacts,
            max_chunks: self.config.limits.chunks,
            file: r.file.0.clone(),
            profile_settings: r.profile_settings.0.clone(),
            predecessor,
            committed,
        })
    }
    /// Release only this failed activity generation; Temporal retains its retry budget.
    pub async fn abandon(&self, f: Failure) -> AppResult<Summary> {
        let mut tx = self.pool.begin().await?;
        let r = locked(&mut tx, f.work.processing_id).await?;
        r.bind(self.installation, &f.work)?;
        let g = latest(&mut *tx, r.summary.id)
            .await?
            .ok_or_else(|| conflict("stale_generation"))?;
        if r.summary.status.terminal()
            || Some(g.id) != f.generation
            || g.stage != f.stage
            || g.committed_at.is_some()
        {
            return Err(conflict("stale_generation"));
        }
        sqlx::query("update generation set expires_at=least(expires_at,$2) where id=$1")
            .bind(g.id)
            .bind(Utc::now())
            .execute(&mut *tx)
            .await?;
        let code = serde_json::to_value(f.code).map_err(|e| AppError::Internal(e.into()))?;
        sqlx::query("update document_processing set error_code=$2,revision=revision+1 where id=$1")
            .bind(r.summary.id)
            .bind(code.as_str().ok_or_else(invalid)?)
            .execute(&mut *tx)
            .await?;
        let summary = summary(&mut *tx, r.summary.id).await?;
        tx.commit().await?;
        Ok(summary)
    }
}
