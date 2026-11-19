// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! A managed source feeds the ordinary original journal and processing pipeline.
use super::{Run, authorize_run, ensure_run_active};
use crate::{
    api::AppState,
    auth::CurrentUser,
    authorization::RuntimeCaller,
    db,
    documents::{
        self, SourceUpload, Spool,
        models::{Destination, UploadRow, UploadStatus},
    },
    domain::Space,
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery, idempotency_key},
    processing::{
        self,
        models::{ProcessingStatus, Summary},
    },
    spaces,
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, Multipart, State},
    http::{HeaderMap, StatusCode},
};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

fn conflict(code: &'static str) -> AppError {
    documents::conflict(
        code,
        "The source operation conflicts with its current state",
    )
}

pub(crate) async fn require_manual_folder<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    id: Uuid,
) -> AppResult<()> {
    if sqlx::query_scalar::<_, bool>("select exists(select 1 from kb_instance where folder_id=$1)")
        .bind(id)
        .fetch_one(ex)
        .await?
    {
        return Err(conflict("knowledge_base_managed"));
    }
    Ok(())
}
pub(crate) async fn require_manual_document<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    id: Uuid,
) -> AppResult<()> {
    if sqlx::query_scalar::<_, bool>(
        "select exists(select 1 from kb_source_document where document_id=$1)",
    )
    .bind(id)
    .fetch_one(ex)
    .await?
    {
        return Err(conflict("knowledge_base_managed"));
    }
    Ok(())
}

async fn writer(pool: &PgPool, run: &Run) -> AppResult<(Transaction<'static, Postgres>, Space)> {
    let space: Space = db::space(pool, run.space_id).await?.into();
    let mut tx = pool.begin().await?;
    spaces::lock_organization(&mut tx, &space).await?;
    ensure_run_active(&mut tx, run.id).await?;
    Ok((tx, space))
}

/// Scan completion never revokes an already admitted processing request.
/// Retirement still prevents publication and physical resources retain their own leases.
pub(crate) async fn processing_writer(
    pool: &PgPool,
    run: Uuid,
    document: Uuid,
) -> AppResult<Transaction<'static, Postgres>> {
    let space: Uuid = sqlx::query_scalar("select space_id from kb_run where id=$1")
        .bind(run)
        .fetch_one(pool)
        .await?;
    let space: Space = db::space(pool, space).await?.into();
    let mut tx = pool.begin().await?;
    spaces::lock_organization(&mut tx, &space).await?;
    let valid: bool = sqlx::query_scalar("select exists(select 1 from kb_run r join kb_instance i on i.id=r.instance_id join document d on d.id=$2 join folder f on f.id=i.folder_id join space s on s.id=i.space_id join space o on o.id=s.organization_id left join space parent on parent.id=s.parent_id where r.id=$1 and d.space_id=r.space_id and d.folder_id=r.folder_id and d.deletion_id is null and f.deletion_id is null and s.deletion_id is null and o.deletion_id is null and (parent.id is null or parent.deletion_id is null))")
        .bind(run).bind(document).fetch_one(&mut *tx).await?;
    if !valid {
        return Err(AppError::NotFound);
    }
    Ok(tx)
}

#[derive(Deserialize, utoipa::IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in = Query)]
pub struct Source {
    pub source_key: String,
    pub source_version: String,
}
impl Source {
    fn validate(&self) -> AppResult<()> {
        if self.source_key.is_empty()
            || self.source_key.len() > 2048
            || self.source_key.chars().any(char::is_control)
            || self.source_version.is_empty()
            || self.source_version.len() > 512
            || self.source_version.chars().any(char::is_control)
        {
            return Err(documents::invalid(
                "A bounded source key and version are required",
            ));
        }
        Ok(())
    }
}
#[derive(Serialize, utoipa::ToSchema)]
#[schema(as = KnowledgeBaseDocumentReceipt)]
pub struct Receipt {
    pub task_id: Uuid,
    pub document_id: Uuid,
    pub state: ProcessingStatus,
    pub error_code: Option<String>,
}
impl From<Summary> for Receipt {
    fn from(s: Summary) -> Self {
        Self {
            task_id: s.id,
            document_id: s.document_id,
            state: s.status,
            error_code: s.error_code,
        }
    }
}

async fn reserve(
    s: &AppState,
    run: &Run,
    user: &CurrentUser,
    key: Uuid,
    source: &Source,
    file: &Spool,
) -> AppResult<(UploadRow, Option<Receipt>)> {
    let storage = s.content.as_ref().ok_or_else(documents::unavailable)?;
    let (mut tx, space) = writer(&s.pool, run).await?;
    documents::token_current(user)?;
    // Replays retain their exact run and source identity even after a later source version.
    type TransferIdentity = (Uuid, Option<Uuid>, Option<String>, Option<String>);
    let existing: Option<TransferIdentity> = sqlx::query_as("select id,kb_run_id,source_key,source_version from document_upload where actor=$1 and request_key=$2")
        .bind(&user.uid).bind(key).fetch_optional(&mut *tx).await?;
    if let Some((id, old_run, old_key, old_version)) = existing {
        let row: UploadRow = sqlx::query_as(
            "select *,target_document_id as document_id from document_upload where id=$1",
        )
        .bind(id)
        .fetch_one(&mut *tx)
        .await?;
        if old_run != Some(run.id)
            || old_key.as_deref() != Some(&source.source_key)
            || old_version.as_deref() != Some(&source.source_version)
            || row.receipt.sha256 != file.sha256()
            || row.receipt.size != file.size
            || row.receipt.name != file.name
            || row.receipt.mime != file.mime
        {
            return Err(conflict("idempotency_conflict"));
        }
        if row.receipt.status != UploadStatus::Stored {
            return Err(conflict(if row.receipt.status == UploadStatus::Pending {
                "upload_in_progress"
            } else {
                "upload_failed"
            }));
        }
        let task: Uuid = sqlx::query_scalar(
            "select id from document_processing where actor=$1 and request_key=$2 and kb_run_id=$3",
        )
        .bind(&user.uid)
        .bind(key)
        .bind(run.id)
        .fetch_one(&mut *tx)
        .await?;
        let receipt = processing::store::summary(&mut *tx, task).await?.into();
        return Ok((row, Some(receipt)));
    }
    sqlx::query("insert into kb_source_document(instance_id,source_key) values($1,$2) on conflict do nothing")
        .bind(run.instance_id).bind(&source.source_key).execute(&mut *tx).await?;
    let (document, pending_upload, pending_processing):(Option<Uuid>,Option<Uuid>,Option<Uuid>)=sqlx::query_as("select document_id,pending_upload_id,pending_processing_id from kb_source_document where instance_id=$1 and source_key=$2 for update")
        .bind(run.instance_id).bind(&source.source_key).fetch_one(&mut *tx).await?;
    let active:bool=sqlx::query_scalar("select exists(select 1 from document_upload where id=$1 and status='pending') or exists(select 1 from document_processing where id=$2 and status in ('pending','running'))")
        .bind(pending_upload).bind(pending_processing).fetch_one(&mut *tx).await?;
    if active {
        return Err(conflict("source_pending"));
    }
    if let Some(document) = document {
        let (name, retired): (String, bool) =
            sqlx::query_as("select name,deletion_id is not null from document where id=$1")
                .bind(document)
                .fetch_one(&mut *tx)
                .await?;
        if retired {
            return Err(conflict("source_retiring"));
        }
        if name != file.name {
            return Err(conflict("source_name_changed"));
        }
    }
    let name_taken:bool=sqlx::query_scalar("select exists(select 1 from document where folder_id=$1 and deletion_id is null and name=$2 and id is distinct from $3)")
        .bind(run.folder_id).bind(&file.name).bind(document).fetch_one(&mut *tx).await?;
    if name_taken {
        return Err(conflict("name_conflict"));
    }
    let profile = serde_json::from_value(serde_json::Value::String(run.profile.clone()))
        .map_err(|_| documents::invalid("Invalid processing profile"))?;
    let row = storage
        .reserve_source(
            &mut tx,
            &space,
            SourceUpload {
                actor: &user.uid,
                key,
                destination: Destination::Folder(run.folder_id),
                file,
                profile: Some(profile),
                retry_of: None,
                target: document,
                source: Some((run.id, &source.source_key, &source.source_version)),
            },
        )
        .await?;
    sqlx::query("update kb_source_document set pending_version=$3,pending_upload_id=$4,pending_processing_id=null,last_seen_run_id=$5 where instance_id=$1 and source_key=$2")
        .bind(run.instance_id).bind(&source.source_key).bind(&source.source_version).bind(row.id).bind(run.id).execute(&mut *tx).await?;
    tx.commit().await?;
    Ok((row, None))
}

#[utoipa::path(post,path="/knowledge-base-runs/{id}/documents",params(("id"=Uuid,Path),("Idempotency-Key"=Uuid,Header),Source),request_body(content=crate::documents::http::FileUpload,content_type="multipart/form-data"),responses((status=202,body=Receipt),(status=200,body=Receipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=429,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn upload_knowledge_base_document(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(source): ApiQuery<Source>,
    headers: HeaderMap,
    multipart: Multipart,
) -> AppResult<(StatusCode, Json<Receipt>)> {
    let run = authorize_run(&s, &user, id).await?;
    source.validate()?;
    let key = idempotency_key(&headers)?;
    let storage = s.content.as_ref().ok_or_else(documents::unavailable)?;
    if !storage.config.uploads_enabled {
        return Err(documents::unavailable());
    }
    let processing = s.processing.as_ref().ok_or_else(processing::unavailable)?;
    Box::pin(processing.derived.validate_bucket())
        .await
        .map_err(|_| processing::unavailable())?;
    let _permit = storage.uploads.clone().try_acquire_owned().map_err(|_| {
        AppError::problem(
            StatusCode::TOO_MANY_REQUESTS,
            "transfer_capacity",
            "All document transfer slots are busy",
        )
    })?;
    // Fail closed before receiving potentially large bytes, then revalidate in each short transaction.
    writer(&s.pool, &run).await?.0.commit().await?;
    let file = tokio::time::timeout(storage.deadline(), storage.spool(multipart))
        .await
        .map_err(|_| {
            AppError::problem(
                StatusCode::REQUEST_TIMEOUT,
                "upload_timeout",
                "The file transfer exceeded its deadline",
            )
        })??;
    let (row, replay) = reserve(&s, &run, &user, key, &source, &file).await?;
    if let Some(receipt) = replay {
        return Ok((StatusCode::OK, Json(receipt)));
    }
    let result=async {
        storage.transfer_upload(row.id,&row.object_key,file).await?;
        let (mut tx,_)=writer(&s.pool,&run).await?;
        documents::token_current(&user)?;
        let row:UploadRow=sqlx::query_as("select *,target_document_id as document_id from document_upload where id=$1 for update").bind(row.id).fetch_one(&mut *tx).await?;
        let receipt=storage.store_upload(&mut tx,&row).await?;
        let summary=processing.admit_kb(&mut tx,&user.uid,&row,&run).await?;
        sqlx::query("update kb_source_document set document_id=$3,pending_processing_id=$4 where instance_id=$1 and source_key=$2 and pending_upload_id=$5")
            .bind(run.instance_id).bind(&source.source_key).bind(receipt.document_id).bind(summary.id).bind(row.id).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok::<_,AppError>(Receipt::from(summary))
    }.await;
    match result {
        Ok(receipt) => Ok((StatusCode::ACCEPTED, Json(receipt))),
        Err(error) => {
            storage.fail(row.id, "source_upload_failed").await?;
            Err(error)
        }
    }
}

#[derive(Deserialize, utoipa::IntoParams)]
#[into_params(parameter_in=Query)]
pub struct Page {
    pub cursor: Option<String>,
    pub limit: Option<i64>,
}
#[derive(Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct SourceDocument {
    pub source_key: String,
    pub document_id: Option<Uuid>,
    pub current_version: Option<String>,
    pub pending_version: Option<String>,
    pub error_code: Option<String>,
    #[sqlx(skip)]
    pub processing: Option<Summary>,
    #[serde(skip)]
    #[schema(ignore)]
    pub processing_id: Option<Uuid>,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct Catalogue {
    pub items: Vec<SourceDocument>,
    pub next_cursor: Option<String>,
}
#[utoipa::path(get,path="/knowledge-base-runs/{id}/documents",params(("id"=Uuid,Path),Page),responses((status=422,body=crate::error::ErrorBody),(status=200,body=Catalogue),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn catalogue(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(page): ApiQuery<Page>,
) -> AppResult<Json<Catalogue>> {
    let run = authorize_run(&s, &user, id).await?;
    let limit = page.limit.unwrap_or(100).clamp(1, 200);
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let mut items:Vec<SourceDocument>=sqlx::query_as("select k.source_key,k.document_id,k.current_version,case when u.status='pending' or p.status in ('pending','running') then k.pending_version end as pending_version,coalesce(p.error_code,u.error_code) as error_code,k.pending_processing_id as processing_id from kb_source_document k left join document_upload u on u.id=k.pending_upload_id left join document_processing p on p.id=k.pending_processing_id where k.instance_id=$1 and ($2::text is null or k.source_key>$2 collate \"C\") and (k.document_id is not null or k.pending_upload_id is not null) order by k.source_key limit $3")
        .bind(run.instance_id).bind(page.cursor).bind(limit+1).fetch_all(&mut *tx).await?;
    let next_cursor = if items.len() > limit as usize {
        items.truncate(limit as usize);
        items.last().map(|i| i.source_key.clone())
    } else {
        None
    };
    let documents: Vec<Uuid> = items.iter().filter_map(|item| item.document_id).collect();
    let summaries = processing::store::summaries(&mut *tx, &documents).await?;
    for item in &mut items {
        item.processing = item
            .document_id
            .and_then(|id| summaries.get(&id))
            .filter(|summary| Some(summary.id) == item.processing_id)
            .cloned();
    }
    tx.commit().await?;
    Ok(Json(Catalogue { items, next_cursor }))
}
#[utoipa::path(get,path="/knowledge-base-runs/{id}/documents/tasks/{task}",params(("id"=Uuid,Path),("task"=Uuid,Path)),responses((status=422,body=crate::error::ErrorBody),(status=200,body=Receipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn outcome(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((id, task)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<Receipt>> {
    let run = authorize_run(&s, &user, id).await?;
    let scoped:bool=sqlx::query_scalar("select exists(select 1 from document_processing p join kb_run r on r.id=p.kb_run_id where p.id=$1 and r.instance_id=$2)").bind(task).bind(run.instance_id).fetch_one(&s.pool).await?;
    if !scoped {
        return Err(AppError::NotFound);
    }
    Ok(Json(
        processing::store::summary(&s.pool, task).await?.into(),
    ))
}
#[derive(Deserialize, utoipa::IntoParams)]
#[serde(deny_unknown_fields)]
#[into_params(parameter_in=Query)]
pub struct Retract {
    pub source_key: String,
}
#[utoipa::path(delete,path="/knowledge-base-runs/{id}/documents",params(("id"=Uuid,Path),Retract),responses((status=422,body=crate::error::ErrorBody),(status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody)))]
async fn retract(
    State(s): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(source): ApiQuery<Retract>,
) -> AppResult<StatusCode> {
    let run = authorize_run(&s, &user, id).await?;
    let (mut tx, space) = writer(&s.pool, &run).await?;
    let mapping:Option<(Option<Uuid>,Option<Uuid>)>=sqlx::query_as("select document_id,pending_upload_id from kb_source_document where instance_id=$1 and source_key=$2 for update")
        .bind(run.instance_id).bind(&source.source_key).fetch_optional(&mut *tx).await?;
    if let Some((document, upload)) = mapping {
        let pending: bool = sqlx::query_scalar(
            "select exists(select 1 from document_upload where id=$1 and status='pending')",
        )
        .bind(upload)
        .fetch_one(&mut *tx)
        .await?;
        if pending {
            return Err(conflict("source_pending"));
        }
        if let Some(document) = document {
            s.lifecycle
                .retire_document(&mut tx, &user.uid, &space, document, None, false)
                .await?;
        }
        sqlx::query("update kb_source_document set document_id=null,current_version=null,pending_version=null,pending_upload_id=null,pending_processing_id=null where instance_id=$1 and source_key=$2")
            .bind(run.instance_id).bind(&source.source_key).execute(&mut *tx).await?;
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
pub(crate) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(
            routes!(upload_knowledge_base_document).layer(DefaultBodyLimit::max(
                documents::config::MAX_FILE_BYTES as usize + 64 * 1024,
            )),
        )
        .routes(routes!(catalogue, retract))
        .routes(routes!(outcome))
}
