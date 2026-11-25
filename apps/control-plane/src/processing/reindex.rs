// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Durable corpus reconstruction from published chunk artifacts. No extraction,
//! new upload, permission widening or process-local ownership is involved.
use super::{http::Worker, models::Artifact};
use crate::{
    api::AppState,
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};
use axum::{Json, extract::State, http::StatusCode};
use chrono::{DateTime, Utc};
use fred_rust_sdk::inference::{InferenceAdmission, ModelOfferKey};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, PgPool, Postgres, Transaction, types::Json as SqlJson};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

// Count and walk exactly the same published corpus. Attachments have no folder.
macro_rules! reindex_documents {
    () => {
        "from document_current d join space s on s.id=d.space_id
         join space org on org.id=s.organization_id left join space parent on parent.id=s.parent_id
         left join folder f on f.id=d.folder_id
         join artifact a on a.generation_id=d.published_generation and a.path='chunks.jsonl'
         where s.organization_id=$1 and org.deletion_id is null and parent.deletion_id is null
           and f.deletion_id is null and s.deletion_id is null and d.deletion_id is null"
    };
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct VectorReindex {
    pub id: Uuid,
    pub status: String,
    #[sqlx(json)]
    pub embedding: ModelOfferKey,
    pub cleanup_pending: bool,
    pub completed: i64,
    pub total: i64,
    pub error_code: Option<String>,
    pub created_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}

pub(super) async fn expire(pool: &PgPool) -> sqlx::Result<()> {
    sqlx::query(
        "update organization_vector_reindex set status='failed',error_code='worker_unavailable',
           lease=null,lease_until=null,completed_at=clock_timestamp()
         where status in ('pending','running') and deadline_at<=clock_timestamp()",
    )
    .execute(pool)
    .await?;
    Ok(())
}

async fn read(
    conn: &mut PgConnection,
    organization: Uuid,
    id: Option<Uuid>,
) -> AppResult<Option<VectorReindex>> {
    sqlx::query_as(
        "select r.id,r.status,r.admission->'selection'->'key' as embedding,r.completed,r.total,
           r.error_code,r.created_at,r.completed_at,
           exists(select 1 from vector_corpus_retirement t where t.replaced_by=r.id and t.cleaned_at is null) as cleanup_pending
         from organization_vector_reindex r where r.organization_id=$1 and ($2::uuid is null or r.id=$2)
         order by r.created_at desc,r.id desc limit 1",
    )
    .bind(organization)
    .bind(id)
    .fetch_optional(conn)
    .await
    .map_err(Into::into)
}

/// A failed reconstruction can resume from its checkpoint, so writes that would
/// change the corpus stay paused until it succeeds or is replaced.
pub(crate) async fn require_writable(conn: &mut PgConnection, organization: Uuid) -> AppResult<()> {
    let latest: Option<String> = sqlx::query_scalar(
        "select status from organization_vector_reindex where organization_id=$1
         order by created_at desc,id desc limit 1",
    )
    .bind(organization)
    .fetch_optional(conn)
    .await?;
    if latest.is_some_and(|status| status != "succeeded") {
        return Err(super::conflict("corpus_reindex_running"));
    }
    Ok(())
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct StartVectorReindex {
    /// Stable request identity; resubmit the failed operation's ID to resume.
    pub id: Uuid,
    pub expected_policy_revision: i64,
    pub embedding: ModelOfferKey,
}

#[utoipa::path(post,path="/organizations/{organization_id}/vector-reindex",params(("organization_id"=Uuid,Path)),request_body=StartVectorReindex,
    responses((status=200,body=VectorReindex),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn start_vector_reindex(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization): ApiPath<Uuid>,
    ApiJson(input): ApiJson<StartVectorReindex>,
) -> AppResult<Json<VectorReindex>> {
    if !super::http::service(&s)?.config.enabled {
        return Err(super::unavailable());
    }
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization),
        Permission::Manage,
    )
    .await?;
    let latest = read(&mut tx, organization, None).await?;
    if let Some(existing) = read(&mut tx, organization, Some(input.id)).await? {
        if existing.embedding != input.embedding {
            return Err(super::conflict("idempotency_conflict"));
        }
        if existing.status != "failed" || !latest.as_ref().is_some_and(|job| job.id == input.id) {
            return Ok(Json(existing));
        }
    } else if latest
        .as_ref()
        .is_some_and(|job| matches!(job.status.as_str(), "pending" | "running"))
    {
        return Err(super::conflict("corpus_reindex_running"));
    }
    let revision: i64 = sqlx::query_scalar(
        "select revision from organization_model_policy where organization_id=$1",
    )
    .bind(organization)
    .fetch_one(&mut *tx)
    .await?;
    if revision != input.expected_policy_revision {
        return Err(super::conflict("model_policy_conflict"));
    }
    let mut admission = crate::model_catalog::instance::admit_embedding_choice(
        &mut tx,
        organization,
        &input.embedding,
    )
    .await?;
    admission.corpus_generation = Some(input.id.to_string());

    if latest.as_ref().is_some_and(|job| job.id == input.id) {
        let saved: SqlJson<InferenceAdmission> =
            sqlx::query_scalar("select admission from organization_vector_reindex where id=$1")
                .bind(input.id)
                .fetch_one(&mut *tx)
                .await?;
        if saved.connection != admission.connection {
            return Err(super::conflict("reindex_model_changed"));
        }
        sqlx::query(
            "update organization_vector_reindex set status='pending',admission=$2,error_code=null,
               lease=null,lease_until=null,execution_id=gen_random_uuid(),dispatch_after=clock_timestamp(),
               deadline_at=clock_timestamp()+interval '1 day',completed_at=null where id=$1",
        )
        .bind(input.id)
        .bind(SqlJson(admission))
        .execute(&mut *tx)
        .await?;
    } else {
        // The exclusive organization guard also serializes normal indexing and
        // visibility admissions. Previously accepted writes must finish first.
        if sqlx::query_scalar::<_, bool>(
            "select exists(
               select 1 from document_current d join space s on s.id=d.space_id
               where s.organization_id=$1 and d.deletion_id is null and (
                 d.retrievable_pending or exists(select 1 from document_processing p
                   where p.document_id=d.id and p.status in ('pending','running'))
               )
             )",
        )
        .bind(organization)
        .fetch_one(&mut *tx)
        .await?
        {
            return Err(super::conflict("corpus_processing_active"));
        }
        let total: i64 = sqlx::query_scalar(concat!("select count(*) ", reindex_documents!()))
            .bind(organization)
            .fetch_one(&mut *tx)
            .await?;
        let inserted = sqlx::query(
            "insert into organization_vector_reindex(id,organization_id,requested_by,status,admission,total)
             values($1,$2,$3,'pending',$4,$5) on conflict(id) do nothing",
        )
        .bind(input.id)
        .bind(organization)
        .bind(&user.uid)
        .bind(SqlJson(admission))
        .bind(total)
        .execute(&mut *tx)
        .await?;
        if inserted.rows_affected() == 0 {
            return Err(super::conflict("idempotency_conflict"));
        }
        if let Some(previous) = latest.filter(|job| job.status == "failed") {
            // The superseded target never became active. It cannot be resumed.
            retire(&mut tx, organization, Some(previous.id), None).await?;
        }
    }
    sqlx::query("select pg_notify($1, '')")
        .bind(super::dispatch::WAKE_CHANNEL)
        .execute(&mut *tx)
        .await?;
    let result = read(&mut tx, organization, Some(input.id))
        .await?
        .ok_or(AppError::NotFound)?;
    tx.commit().await?;
    Ok(Json(result))
}

#[utoipa::path(get,path="/organizations/{organization_id}/vector-reindex",params(("organization_id"=Uuid,Path)),responses((status=200,body=Option<VectorReindex>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn vector_reindex_status(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization): ApiPath<Uuid>,
) -> AppResult<Json<Option<VectorReindex>>> {
    authorization::authorize_organization(&s.pool, &user.uid, organization, Permission::Manage)
        .await?;
    let mut conn = s.pool.acquire().await?;
    Ok(Json(read(&mut conn, organization, None).await?))
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct ReindexDocument {
    pub document_id: Uuid,
    pub generation: Uuid,
    pub prefix: String,
    #[sqlx(flatten)]
    pub artifact: Artifact,
    pub space_id: Uuid,
    pub session_id: Option<Uuid>,
    pub retrievable: bool,
    pub folder_path: Option<String>,
}
async fn next_document(
    conn: &mut PgConnection,
    organization: Uuid,
    cursor: Option<Uuid>,
) -> AppResult<Option<ReindexDocument>> {
    sqlx::query_as(concat!(
        "select d.id as document_id,d.published_generation as generation,
         (select g.prefix from generation g where g.id=d.published_generation) as prefix,
         a.path,a.size,a.sha256,d.space_id,d.session_id,d.retrievable,f.path as folder_path ",
        reindex_documents!(),
        " and ($2::uuid is null or d.id>$2) order by d.id limit 1"
    ))
    .bind(organization)
    .bind(cursor)
    .fetch_optional(conn)
    .await
    .map_err(Into::into)
}

async fn retire(
    conn: &mut PgConnection,
    organization: Uuid,
    generation: Option<Uuid>,
    replaced_by: Option<Uuid>,
) -> sqlx::Result<()> {
    sqlx::query(
        "insert into vector_corpus_retirement(organization_id,corpus_generation,replaced_by,due_at)
         values($1,$2,$3,clock_timestamp()+interval '30 seconds') on conflict do nothing",
    )
    .bind(organization)
    .bind(generation)
    .bind(replaced_by)
    .execute(conn)
    .await?;
    Ok(())
}

async fn complete(conn: &mut PgConnection, job: &ReindexCandidate) -> AppResult<bool> {
    let key = &job.admission.selection.key;
    let available =
        crate::model_catalog::instance::admit_embedding_choice(conn, job.organization_id, key)
            .await;
    let same_connection = match available {
        Ok(current) => current.connection == job.admission.connection,
        Err(error @ AppError::Internal(_)) => return Err(error),
        Err(_) => false,
    };
    if !same_connection {
        fail(conn, job.id, "embedding_model_unavailable").await?;
        return Ok(false);
    }
    let previous: Option<Uuid> = sqlx::query_scalar(
        "select corpus_generation from organization_model_policy where organization_id=$1 for update",
    )
    .bind(job.organization_id)
    .fetch_one(&mut *conn)
    .await?;
    sqlx::query(
        "update organization_vector_reindex set status='succeeded',total=completed,
           completed_at=clock_timestamp(),error_code=null,lease=null,lease_until=null where id=$1",
    )
    .bind(job.id)
    .execute(&mut *conn)
    .await?;
    sqlx::query(
        "update organization_model_policy set embedding_source_id=$2,embedding_upstream_model_id=$3,
           corpus_generation=$4,revision=revision+1,updated_by=$5,updated_at=clock_timestamp()
         where organization_id=$1",
    )
    .bind(job.organization_id)
    .bind(&key.source_id)
    .bind(&key.upstream_model_id)
    .bind(job.id)
    .bind(&job.requested_by)
    .execute(&mut *conn)
    .await?;
    retire(conn, job.organization_id, previous, Some(job.id)).await?;
    Ok(true)
}

async fn fail(conn: &mut PgConnection, id: Uuid, code: &str) -> sqlx::Result<()> {
    sqlx::query(
        "update organization_vector_reindex set status='failed',error_code=$2,
           completed_at=clock_timestamp(),lease=null,lease_until=null where id=$1",
    )
    .bind(id)
    .bind(code)
    .execute(conn)
    .await?;
    Ok(())
}

#[derive(Serialize, ToSchema)]
pub struct VectorReindexWork {
    pub id: Uuid,
    pub execution_id: Uuid,
    pub organization_id: Uuid,
    pub lease: Uuid,
    pub admission: InferenceAdmission,
    pub document: ReindexDocument,
    pub offset: i64,
}

#[derive(sqlx::FromRow)]
struct ReindexCandidate {
    id: Uuid,
    organization_id: Uuid,
    requested_by: String,
    admission: SqlJson<InferenceAdmission>,
    cursor: Option<Uuid>,
    document_id: Option<Uuid>,
    chunk_cursor: i64,
    lease: Option<Uuid>,
}

async fn lock_job(
    tx: &mut Transaction<'_, Postgres>,
    id: Uuid,
    execution_id: Uuid,
) -> AppResult<Option<ReindexCandidate>> {
    let Some(organization) = sqlx::query_scalar(
        "select organization_id from organization_vector_reindex where id=$1 and execution_id=$2",
    )
    .bind(id)
    .bind(execution_id)
    .fetch_optional(&mut **tx)
    .await?
    else {
        return Ok(None);
    };
    // Lock order matches admission and catalogue writes. No model call holds it.
    sqlx::query("set local lock_timeout = '5s'")
        .execute(&mut **tx)
        .await?;
    spaces::lock_organization_id(tx, organization).await?;
    sqlx::query_as(
        "select r.id,r.organization_id,r.requested_by,r.admission,r.cursor,r.document_id,r.chunk_cursor,
           case when r.lease_until>clock_timestamp() then r.lease end as lease
         from organization_vector_reindex r join space org on org.id=r.organization_id
         where r.id=$1 and r.execution_id=$2 and r.status in ('pending','running')
           and org.deletion_id is null and r.deadline_at>clock_timestamp() for update of r",
    )
    .bind(id)
    .bind(execution_id)
    .fetch_optional(&mut **tx)
    .await
    .map_err(Into::into)
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ClaimVectorReindex {
    pub execution_id: Uuid,
}

#[utoipa::path(post,path="/document-processing/vector-reindex/{id}/claim",params(("id"=Uuid,Path)),request_body=ClaimVectorReindex,
    responses((status=200,body=Option<VectorReindexWork>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn vector_reindex_work(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<ClaimVectorReindex>,
) -> AppResult<Json<Option<VectorReindexWork>>> {
    let mut tx = s.pool.begin().await?;
    let Some(job) = lock_job(&mut tx, id, input.execution_id).await? else {
        return Ok(Json(None));
    };
    if job.lease.is_some() {
        // An activity retry waits for the earlier writer's lease to expire.
        return Err(super::unavailable());
    }
    let Some(document) = next_document(&mut tx, job.organization_id, job.cursor).await? else {
        let succeeded = complete(&mut tx, &job).await?;
        tx.commit().await?;
        return if succeeded {
            Ok(Json(None))
        } else {
            Err(super::conflict("embedding_model_unavailable"))
        };
    };
    let lease = Uuid::new_v4();
    let offset = if job.document_id == Some(document.document_id) {
        job.chunk_cursor
    } else {
        0
    };
    sqlx::query(
        "update organization_vector_reindex set status='running',lease=$2,document_id=$3,
           chunk_cursor=$4,lease_until=clock_timestamp()+interval '15 minutes' where id=$1",
    )
    .bind(id)
    .bind(lease)
    .bind(document.document_id)
    .bind(offset)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Json(Some(VectorReindexWork {
        id,
        execution_id: input.execution_id,
        organization_id: job.organization_id,
        lease,
        admission: job.admission.0,
        document,
        offset,
    })))
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReindexProgress {
    pub execution_id: Uuid,
    pub lease: Uuid,
    pub document_id: Uuid,
    pub succeeded: bool,
    pub offset: i64,
    pub finished: bool,
}
#[utoipa::path(post,path="/document-processing/vector-reindex/{id}",params(("id"=Uuid,Path)),request_body=ReindexProgress,
    responses((status=200,body=bool),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn vector_reindex_progress(
    State(s): State<AppState>,
    Worker: Worker,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<ReindexProgress>,
) -> AppResult<Json<bool>> {
    if input.offset < 0 {
        return Err(super::models::invalid());
    }
    let mut tx = s.pool.begin().await?;
    let Some(job) = lock_job(&mut tx, id, input.execution_id).await? else {
        return Err(super::conflict("stale_reindex_work"));
    };
    if job.lease != Some(input.lease)
        || job.document_id != Some(input.document_id)
        || input.succeeded && input.offset < job.chunk_cursor
    {
        return Err(super::conflict("stale_reindex_work"));
    }
    // A retired document cannot enter the live corpus. Skip it if the activity
    // fails, but keep its lease valid while it is still checkpointing.
    let retired = !input.succeeded
        && next_document(&mut tx, job.organization_id, job.cursor)
            .await?
            .is_none_or(|document| document.document_id != input.document_id);
    if !input.succeeded && !retired {
        fail(&mut tx, id, "indexing_failed").await?;
        tx.commit().await?;
        return Ok(Json(false));
    }
    let finished = input.finished || retired;
    sqlx::query(
        "update organization_vector_reindex set cursor=case when $2 then document_id else cursor end,
           completed=completed+case when $2 then 1 else 0 end,chunk_cursor=case when $2 then 0 else $3 end,
           lease=case when $2 then null else lease end,
           lease_until=case when $2 then null else clock_timestamp()+interval '15 minutes' end
         where id=$1",
    )
    .bind(id)
    .bind(finished)
    .bind(input.offset)
    .execute(&mut *tx)
    .await?;
    let mut succeeded = true;
    if finished
        && next_document(&mut tx, job.organization_id, Some(input.document_id))
            .await?
            .is_none()
    {
        succeeded = complete(&mut tx, &job).await?;
    }
    tx.commit().await?;
    Ok(Json(succeeded))
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct RetiredCorpus {
    pub organization_id: Uuid,
    pub corpus_generation: Option<Uuid>,
}
#[utoipa::path(get,path="/document-processing/vector-reindex/retired",responses((status=200,body=Vec<RetiredCorpus>),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn retired_corpora(
    State(s): State<AppState>,
    Worker: Worker,
) -> AppResult<Json<Vec<RetiredCorpus>>> {
    // Retain the retirement fact and revisit it: an old timed-out remote write
    // must never leave a recreated, unreferenced physical store indefinitely.
    let rows=sqlx::query_as("with due as (select r.ctid from vector_corpus_retirement r where r.due_at<clock_timestamp() and not exists(select 1 from organization_model_policy p where p.organization_id=r.organization_id and p.corpus_generation is not distinct from r.corpus_generation) order by r.due_at limit 1 for update skip locked) update vector_corpus_retirement r set due_at=clock_timestamp()+interval '2 minutes' from due where r.ctid=due.ctid returning r.organization_id,r.corpus_generation")
        .fetch_all(&s.pool).await?;
    Ok(Json(rows))
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RetiredCorpusProgress {
    pub organization_id: Uuid,
    pub corpus_generation: Option<Uuid>,
    pub complete: bool,
}
#[utoipa::path(post,path="/document-processing/vector-reindex/retired",request_body=RetiredCorpusProgress,responses((status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody)))]
async fn retired_corpus_progress(
    State(s): State<AppState>,
    Worker: Worker,
    ApiJson(input): ApiJson<RetiredCorpusProgress>,
) -> AppResult<StatusCode> {
    sqlx::query("update vector_corpus_retirement
       set due_at=clock_timestamp()+case when $3 then interval '1 day' else interval '30 seconds' end,
           cleaned_at=case when $3 then coalesce(cleaned_at,clock_timestamp()) end
       where organization_id=$1 and corpus_generation is not distinct from $2")
        .bind(input.organization_id).bind(input.corpus_generation).bind(input.complete).execute(&s.pool).await?;
    Ok(StatusCode::NO_CONTENT)
}

pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(start_vector_reindex, vector_reindex_status))
        .routes(routes!(vector_reindex_work))
        .routes(routes!(vector_reindex_progress))
        .routes(routes!(retired_corpora, retired_corpus_progress))
}
