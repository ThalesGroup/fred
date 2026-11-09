// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Conversation deliverables use the document catalogue and the original upload journal.
//! Workloads assert their admitted person/run/agent; only resource lifetime is checked here.

use super::{Storage, conflict, http::no_store, invalid, unavailable, upload};
use crate::{
    api::AppState,
    authorization::{Delegation, RuntimeCaller},
    error::{AppError, AppResult},
    extract::{ApiPath, ApiQuery, idempotency_key},
};
use axum::{
    Json,
    extract::{DefaultBodyLimit, FromRef, Multipart, State},
    http::{HeaderMap, StatusCode},
    response::Response,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{Postgres, Transaction};
use utoipa::ToSchema;
use utoipa_axum::{
    router::{OpenApiRouter, UtoipaMethodRouterExt},
    routes,
};
use uuid::Uuid;

#[derive(Serialize, sqlx::FromRow, ToSchema)]
pub struct ConversationFile {
    pub document_id: Uuid,
    pub content_id: Uuid,
    pub path: String,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub sha256: String,
    pub updated_at: DateTime<Utc>,
    pub preview_content_id: Option<Uuid>,
}

#[derive(Serialize, sqlx::FromRow, ToSchema)]
pub struct FileWrite {
    pub document_id: Uuid,
    pub content_id: Uuid,
}

#[derive(Serialize, ToSchema)]
pub struct FileWriteTarget {
    /// Null means create; a write must submit this value unchanged after rendering.
    pub current_content_id: Option<Uuid>,
}

#[derive(Deserialize)]
pub struct WriteQuery {
    #[serde(flatten)]
    delegation: Delegation,
    path: String,
    expected_content_id: Option<Uuid>,
    /// Preview of precisely this primary content. It is never a second user file.
    source_content_id: Option<Uuid>,
}

#[derive(Deserialize)]
pub struct ReadQuery {
    #[serde(flatten)]
    delegation: Delegation,
    limit: Option<i64>,
    offset: Option<i64>,
}

async fn require_reader(
    state: &AppState,
    caller: &crate::auth::CurrentUser,
    delegation: &Delegation,
    space: Uuid,
    session: Uuid,
) -> AppResult<()> {
    let person = delegation.subject(state, caller)?;
    if delegation.agent.is_some() {
        // Reuse admitted execution and the writer's private, live resource boundary.
        let bound = BoundWriter::new(state, caller, delegation, space, session)?;
        bound
            .transaction(state.content.as_ref().ok_or_else(unavailable)?)
            .await?
            .commit()
            .await?;
    } else {
        let admission = crate::onboarding::AdmissionState::from_ref(state);
        crate::onboarding::require_admitted(&admission.pool, &admission.auth, person).await?;
        if admission.auth.enabled() {
            crate::onboarding::require_accepted(
                &admission.pool,
                admission.version.as_deref(),
                person,
            )
            .await?;
        }
        crate::users::snapshot(&admission, caller).await;
        crate::sessions::require_owner(&state.pool, person, space, session).await?;
    }
    Ok(())
}

struct BoundWriter<'a> {
    person: &'a str,
    agent: Uuid,
    space: Uuid,
    session: Uuid,
}

impl<'a> BoundWriter<'a> {
    fn new(
        state: &AppState,
        caller: &'a crate::auth::CurrentUser,
        delegation: &'a Delegation,
        space: Uuid,
        session: Uuid,
    ) -> AppResult<Self> {
        let person = delegation.subject(state, caller)?;
        let agent = delegation
            .agent
            .as_deref()
            .and_then(|s| Uuid::parse_str(s).ok())
            .ok_or(AppError::Forbidden)?;
        Ok(Self {
            person,
            agent,
            space,
            session,
        })
    }

    async fn transaction(&self, storage: &Storage) -> AppResult<Transaction<'static, Postgres>> {
        let mut tx = crate::spaces::storage_transaction(&storage.pool, self.space, true).await?;
        // One conversation's bounded inventory is coordinated here; unrelated users proceed.
        sqlx::query_scalar::<_, Uuid>("select m.session_id from session_metadata m join space s on s.id=m.space_id where m.session_id=$1 and m.space_id=$2 and m.user_id=$3 and m.agent_instance_id=$4 and m.deletion_id is null and s.deletion_id is null for update of m")
            .bind(self.session).bind(self.space).bind(self.person).bind(self.agent)
            .fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
        Ok(tx)
    }
}

fn path(value: &str) -> AppResult<(String, String)> {
    let parts = value
        .split('/')
        .map(upload::name)
        .collect::<AppResult<Vec<_>>>()?;
    let (name, parents) = parts
        .split_last()
        .ok_or_else(|| invalid("A relative file path is required"))?;
    let parent = parents.join("/");
    if parent.len() > 768 || parents.len() > 15 {
        return Err(invalid("The relative file path is too long"));
    }
    Ok((parent, name.clone()))
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(list_conversation_files))
        .routes(routes!(file_write_target))
        .routes(
            routes!(write_conversation_file).layer(DefaultBodyLimit::max(
                super::config::MAX_FILE_BYTES as usize + 64 * 1024,
            )),
        )
        .routes(routes!(download_conversation_file))
        .routes(routes!(preview_conversation_file))
        .route_layer(axum::middleware::from_fn(no_store))
}

#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/files",
    params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),
        ("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query),
        ("limit"=Option<i64>,Query),("offset"=Option<i64>,Query)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=[ConversationFile]),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn list_conversation_files(
    State(state): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<ReadQuery>,
) -> AppResult<Json<Vec<ConversationFile>>> {
    require_reader(&state, &user, &query.delegation, space, session).await?;
    let limit = query.limit.unwrap_or(10000);
    let offset = query.offset.unwrap_or(0);
    if !(1..=10000).contains(&limit) || !(0..=10000).contains(&offset) {
        return Err(invalid("File list bounds exceeded"));
    }
    let files = sqlx::query_as("select d.id as document_id,d.current_content_id as content_id,case when d.parent_path='' then d.name else d.parent_path||'/'||d.name end as path,d.name,d.mime,d.size,d.sha256,d.updated_at,(select id from document_content where source_content_id=d.current_content_id and published_at is not null and cleaned_at is null) as preview_content_id from document_current d where d.space_id=$1 and d.session_id=$2 and d.purpose='output' and d.deletion_id is null order by d.updated_at desc,d.id desc limit $3 offset $4")
        .bind(space).bind(session).bind(limit).bind(offset).fetch_all(&state.pool).await?;
    Ok(Json(files))
}

#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/files/write-target",
    params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("path"=String,Query),
        ("person"=String,Query),("run"=String,Query),("agent"=String,Query)),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=FileWriteTarget),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn file_write_target(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<WriteQuery>,
) -> AppResult<Json<FileWriteTarget>> {
    let writer = BoundWriter::new(&state, &caller, &query.delegation, space, session)?;
    let storage = state.content.as_ref().ok_or_else(unavailable)?;
    let (parent, name) = path(&query.path)?;
    let mut tx = writer.transaction(storage).await?;
    let content: Option<Option<Uuid>> = sqlx::query_scalar("select current_content_id from document where session_id=$1 and space_id=$2 and parent_path=$3 and name=$4 and purpose='output' and deletion_id is null")
        .bind(session).bind(space).bind(parent).bind(name).fetch_optional(&mut *tx).await?;
    tx.commit().await?;
    Ok(Json(FileWriteTarget {
        current_content_id: content.flatten(),
    }))
}

#[derive(sqlx::FromRow)]
struct Attempt {
    id: Uuid,
    target_document_id: Uuid,
    content_id: Option<Uuid>,
    status: String,
    object_key: String,
    session_id: Uuid,
    space_id: Uuid,
    parent_path: String,
    name: String,
    mime: String,
    size: i64,
    sha256: String,
    purpose: String,
    expected_content_id: Option<Uuid>,
}

#[utoipa::path(post,path="/spaces/{space_id}/sessions/{session_id}/files",
    params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("path"=String,Query),
        ("person"=String,Query),("run"=String,Query),("agent"=String,Query),
        ("expected_content_id"=Option<Uuid>,Query),("source_content_id"=Option<Uuid>,Query),
        ("Idempotency-Key"=Uuid,Header)),
    request_body(content=super::http::FileUpload,content_type="multipart/form-data"),
    responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,body=FileWrite),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn write_conversation_file(
    State(state): State<AppState>,
    RuntimeCaller(caller): RuntimeCaller,
    ApiPath((space, session)): ApiPath<(Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<WriteQuery>,
    headers: HeaderMap,
    multipart: Multipart,
) -> AppResult<Json<FileWrite>> {
    let writer = BoundWriter::new(&state, &caller, &query.delegation, space, session)?;
    let storage = state.content.as_ref().ok_or_else(unavailable)?;
    let key = idempotency_key(&headers)?;
    if !storage.config.uploads_enabled {
        return Err(unavailable());
    }
    let _permit = storage.uploads.clone().try_acquire_owned().map_err(|_| {
        AppError::problem(
            StatusCode::TOO_MANY_REQUESTS,
            "transfer_capacity",
            "All file transfer slots are busy",
        )
    })?;
    let (parent, name) = path(&query.path)?;
    // Check the bound live resource before accepting bytes; release all SQL locks for transfer.
    writer.transaction(storage).await?.commit().await?;
    let spool = tokio::time::timeout(storage.deadline(), storage.spool(multipart))
        .await
        .map_err(|_| unavailable())??;
    if query.source_content_id.is_none() && name != spool.name {
        return Err(invalid(
            "The multipart filename must match the destination path",
        ));
    }
    let reserved = storage
        .reserve_output(&writer, &query, key, &parent, &name, &spool)
        .await;
    // Session rows serialize one conversation, but request keys span conversations.
    let attempt = if reserved.is_err()
        && sqlx::query_scalar::<_, bool>(
            "select exists(select 1 from document_upload where actor=$1 and request_key=$2)",
        )
        .bind(writer.person)
        .bind(key)
        .fetch_one(&storage.pool)
        .await?
    {
        storage
            .reserve_output(&writer, &query, key, &parent, &name, &spool)
            .await?
    } else {
        reserved?
    };
    if attempt.status == "stored" {
        return Ok(Json(FileWrite {
            document_id: attempt.target_document_id,
            content_id: attempt.content_id.ok_or_else(unavailable)?,
        }));
    }
    let outcome = async {
        storage
            .transfer_upload(attempt.id, &attempt.object_key, spool)
            .await?;
        upload::token_current(&caller)?;
        storage.publish_output(&writer, &query, &attempt).await
    }
    .await;
    if outcome.is_err() {
        storage.fail(attempt.id, "output_interrupted").await?;
    }
    outcome.map(Json)
}

impl Storage {
    async fn reserve_output(
        &self,
        writer: &BoundWriter<'_>,
        query: &WriteQuery,
        key: Uuid,
        parent: &str,
        name: &str,
        file: &upload::Spool,
    ) -> AppResult<Attempt> {
        let mut tx = writer.transaction(self).await?;
        let purpose = if query.source_content_id.is_some() {
            "preview"
        } else {
            "output"
        };
        let expected = query.source_content_id.or(query.expected_content_id);
        let prior: Option<Attempt> = sqlx::query_as(
            "select * from document_upload where actor=$1 and request_key=$2 and purpose<>'source'",
        )
        .bind(writer.person)
        .bind(key)
        .fetch_optional(&mut *tx)
        .await?;
        if let Some(prior) = prior {
            if prior.session_id != writer.session
                || prior.space_id != writer.space
                || prior.parent_path != parent
                || prior.name != name
                || prior.mime != file.mime
                || prior.size != file.size
                || prior.sha256 != file.sha256()
                || prior.purpose != purpose
                || prior.expected_content_id != expected
            {
                return Err(conflict(
                    "idempotency_conflict",
                    "The request key names another write",
                ));
            }
            return if prior.status == "stored" {
                Ok(prior)
            } else {
                Err(conflict(
                    "write_unresolved",
                    "Use the original receipt or a new attempt after failure",
                ))
            };
        }
        let placement: crate::domain::Space = sqlx::query_as::<_, crate::domain::SpaceRow>(
            "select * from space where id=$1 and deletion_id is null",
        )
        .bind(writer.space)
        .fetch_one(&mut *tx)
        .await?
        .into();
        let (owner, _) = self.quota(&placement)?;
        self.ensure_budgets(&mut tx, &placement).await?;
        let existing: Option<(Uuid,Option<Uuid>)> = sqlx::query_as("select id,current_content_id from document where space_id=$1 and session_id=$2 and parent_path=$3 and name=$4 and purpose='output' and deletion_id is null for update")
            .bind(writer.space).bind(writer.session).bind(parent).bind(name).fetch_optional(&mut *tx).await?;
        if existing.and_then(|r| r.1) != expected || (purpose == "preview" && expected.is_none()) {
            return Err(conflict(
                "content_changed",
                "Read the file again before producing a new revision",
            ));
        }
        let doc = if let Some((id, _)) = existing {
            id
        } else {
            let id = Uuid::new_v4();
            // The database runs local and organization used-byte accounting.
            sqlx::query("insert into document(id,space_id,session_id,name,parent_path,purpose,created_by,quota_owner) values($1,$2,$3,$4,$5,'output',$6,$7)")
                .bind(id).bind(writer.space).bind(writer.session).bind(name).bind(parent).bind(writer.person).bind(owner).execute(&mut *tx).await?;
            id
        };
        let old_size: i64 = sqlx::query_scalar(
            "select coalesce((select size from document_content where id=$1),0)",
        )
        .bind(expected)
        .fetch_one(&mut *tx)
        .await?;
        let reserved = if purpose == "preview" {
            0
        } else {
            (file.size - old_size).max(0)
        };
        let (count,bytes):(i64,i64) = sqlx::query_as("select count(*),coalesce(sum(c.size),0)::bigint from document d left join document_content c on c.id=d.current_content_id where d.session_id=$1 and d.purpose='output' and d.deletion_id is null and (d.current_content_id is not null or d.id=$2 or exists(select 1 from document_upload u where u.target_document_id=d.id and u.status='pending'))")
            .bind(writer.session).bind(doc).fetch_one(&mut *tx).await?;
        let pending: i64 = sqlx::query_scalar("select coalesce(sum(reserved_bytes),0)::bigint from document_upload where session_id=$1 and purpose='output' and status='pending'")
            .bind(writer.session).fetch_one(&mut *tx).await?;
        if count > i64::from(self.config.limits.conversation_files)
            || reserved
                > self
                    .config
                    .limits
                    .conversation_bytes
                    .saturating_sub(bytes + pending)
        {
            return Err(invalid("The conversation deliverable budget is exhausted"));
        }
        self.require_cleanup_capacity(&mut *tx).await?;
        let id = Uuid::new_v4();
        let object_key = format!("{}{id}/input/{}", self.prefix, file.name);
        if object_key.len() > 1024 {
            return Err(invalid(
                "The encoded file path exceeds the object-store key limit",
            ));
        }
        // The database runs local and organization reservation accounting.
        let row=sqlx::query_as("insert into document_upload(id,request_key,actor,organization_id,space_id,session_id,quota_owner,name,parent_path,mime,size,sha256,object_key,status,expires_at,put_pending,target_document_id,expected_content_id,purpose,reserved_bytes) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'pending',clock_timestamp()+make_interval(secs=>$14),true,$15,$16,$17,$18) returning *")
            .bind(id).bind(key).bind(writer.person).bind(placement.organization).bind(writer.space).bind(writer.session).bind(owner).bind(name).bind(parent).bind(&file.mime).bind(file.size).bind(file.sha256()).bind(object_key).bind(self.config.limits.lease_seconds() as f64).bind(doc).bind(expected).bind(purpose).bind(reserved).fetch_one(&mut *tx).await?;
        tx.commit().await?;
        Ok(row)
    }

    async fn publish_output(
        &self,
        writer: &BoundWriter<'_>,
        query: &WriteQuery,
        attempt: &Attempt,
    ) -> AppResult<FileWrite> {
        let mut tx = writer.transaction(self).await?;
        let current: Option<Uuid> = sqlx::query_scalar("select current_content_id from document where id=$1 and deletion_id is null for update")
            .bind(attempt.target_document_id).fetch_one(&mut *tx).await?;
        if current != attempt.expected_content_id {
            return Err(conflict(
                "content_changed",
                "The source content changed while writing",
            ));
        }
        // The database runs local and organization reservation accounting.
        let count=sqlx::query("update document_upload set status='stored',completed_at=clock_timestamp() where id=$1 and status='pending' and not put_pending and expires_at>clock_timestamp()")
            .bind(attempt.id).execute(&mut *tx).await?.rows_affected();
        if count != 1 {
            return Err(conflict(
                "upload_expired",
                "The write can no longer be published",
            ));
        }
        sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values($1,$2,$3,$4,$5,$6,$7,$8,clock_timestamp())")
            .bind(attempt.id).bind(attempt.target_document_id).bind(if query.source_content_id.is_some() {"preview"} else {"primary"}).bind(query.source_content_id)
            .bind(&attempt.object_key).bind(&attempt.mime).bind(attempt.size).bind(&attempt.sha256).execute(&mut *tx).await?;
        if query.source_content_id.is_none() {
            // The database adjusts used storage bytes and schedules obsolete content cleanup.
            sqlx::query("update document set current_content_id=$2,updated_at=clock_timestamp() where id=$1").bind(attempt.target_document_id).bind(attempt.id).execute(&mut *tx).await?;
        }
        // The database runs local and organization reservation accounting.
        sqlx::query("update document_upload set content_id=$2 where id=$1")
            .bind(attempt.id)
            .bind(attempt.id)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(FileWrite {
            document_id: attempt.target_document_id,
            content_id: attempt.id,
        })
    }
}

async fn download(
    state: AppState,
    space: Uuid,
    session: Uuid,
    document: Uuid,
    preview: bool,
) -> AppResult<Response> {
    let (id,key,name,size,sha):(Uuid,String,String,i64,String)=sqlx::query_as("select c.id,c.object_key,case when $4 then d.name||'.pdf' else d.name end,c.size,c.sha256 from document d join document_content c on (case when $4 then c.source_content_id=d.current_content_id else c.id=d.current_content_id end) where d.id=$1 and d.space_id=$2 and d.session_id=$3 and d.purpose='output' and d.deletion_id is null and c.published_at is not null and c.cleaned_at is null")
        .bind(document).bind(space).bind(session).bind(preview).fetch_one(&state.pool).await?;
    let mut response = state
        .content
        .as_ref()
        .ok_or_else(unavailable)?
        .stream_file(id, &key, &name, size, &sha)
        .await?;
    // This identity and the immutable object key come from the same SQL row.
    response.headers_mut().insert(
        "x-content-id",
        id.to_string().parse().map_err(|_| unavailable())?,
    );
    Ok(response)
}

#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/files/{document_id}/content",
    params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("document_id"=Uuid,Path),
        ("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,description="Current file bytes",headers(("X-Content-Id"=Uuid,description="Identity of the returned bytes"))),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn download_conversation_file(
    State(state): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, session, document)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<ReadQuery>,
) -> AppResult<Response> {
    require_reader(&state, &user, &query.delegation, space, session).await?;
    download(state, space, session, document, false).await
}

#[utoipa::path(get,path="/spaces/{space_id}/sessions/{session_id}/files/{document_id}/preview",
    params(("space_id"=Uuid,Path),("session_id"=Uuid,Path),("document_id"=Uuid,Path),
        ("person"=Option<String>,Query),("run"=Option<String>,Query),("agent"=Option<String>,Query)),responses((status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=200,description="Preview of the current file"),(status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn preview_conversation_file(
    State(state): State<AppState>,
    RuntimeCaller(user): RuntimeCaller,
    ApiPath((space, session, document)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiQuery(query): ApiQuery<ReadQuery>,
) -> AppResult<Response> {
    require_reader(&state, &user, &query.delegation, space, session).await?;
    download(state, space, session, document, true).await
}
