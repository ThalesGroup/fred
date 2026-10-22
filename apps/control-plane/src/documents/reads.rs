// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{Storage, conflict, dependency_error, invalid, models::*, unavailable, upload};
use crate::{
    db,
    domain::{Document, Folder, Permission, Space},
    error::{AppError, AppResult},
    spaces,
};
use axum::{
    body::{Body, Bytes},
    http::{StatusCode, header},
    response::{IntoResponse, Response},
};
use sha2::{Digest, Sha256};
use tokio::io::AsyncReadExt;
use uuid::Uuid;

impl Storage {
    pub async fn receipt(&self, actor: &str, key: Uuid) -> AppResult<UploadReceipt> {
        let mut row: UploadReceipt =
            sqlx::query_as("select * from document_upload where actor=$1 and request_key=$2")
                .bind(actor)
                .bind(key)
                .fetch_one(&self.pool)
                .await?;
        spaces::authorize(&self.pool, &self.fga, actor, row.space_id, Permission::Read)
            .await
            .map_err(dependency_error)?;
        if let Some(id) = row.document_id {
            row.processing = crate::processing::store::summaries(&self.pool, &[id])
                .await?
                .remove(&id);
        }
        Ok(row)
    }

    pub async fn receipts(
        &self,
        actor: &str,
        space: Uuid,
        query: ReceiptQuery,
    ) -> AppResult<Vec<UploadReceipt>> {
        spaces::authorize(&self.pool, &self.fga, actor, space, Permission::Read)
            .await
            .map_err(dependency_error)?;
        if query.before.is_some() != query.before_key.is_some() {
            return Err(invalid("Both receipt cursor fields are required"));
        }
        let mut receipts:Vec<UploadReceipt>=sqlx::query_as("select * from document_upload u where actor=$1 and space_id=$2 and (acknowledged_at is null or exists(select 1 from document_processing p where p.document_id=u.document_id and p.status in ('pending','running'))) and successor_key is null and ($3::timestamptz is null or (created_at,request_key)<($3,$4)) order by created_at desc,request_key desc limit $5")
            .bind(actor).bind(space).bind(query.before).bind(query.before_key).bind(query.limit.unwrap_or(50).clamp(1,200)).fetch_all(&self.pool).await?;
        let ids: Vec<Uuid> = receipts.iter().filter_map(|r| r.document_id).collect();
        let mut summaries = crate::processing::store::summaries(&self.pool, &ids).await?;
        for receipt in &mut receipts {
            receipt.processing = receipt.document_id.and_then(|id| summaries.remove(&id));
        }
        Ok(receipts)
    }

    pub async fn acknowledge(&self, actor: &str, key: Uuid) -> AppResult<()> {
        let row = self.receipt(actor, key).await?;
        if row.status == UploadStatus::Pending {
            return Err(conflict(
                "upload_in_progress",
                "An active upload cannot be dismissed",
            ));
        }
        let mut tx = self.pool.begin().await?;
        if let Some(id) = row.document_id {
            sqlx::query("select pg_advisory_xact_lock(991,hashtext($1))")
                .bind(id.to_string())
                .execute(&mut *tx)
                .await?;
            let active:bool=sqlx::query_scalar("select exists(select 1 from document_processing where document_id=$1 and status in ('pending','running'))").bind(id).fetch_one(&mut *tx).await?;
            if active {
                return Err(crate::processing::conflict("processing_active"));
            }
        }
        sqlx::query("update document_upload set acknowledged_at=coalesce(acknowledged_at,clock_timestamp()) where actor=$1 and request_key=$2 and status<>'pending'")
            .bind(actor).bind(key).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(())
    }

    pub async fn summary(&self, actor: &str, id: Uuid) -> AppResult<StorageSummary> {
        let space = spaces::authorize(&self.pool, &self.fga, actor, id, Permission::Read)
            .await
            .map_err(dependency_error)?;
        self.usage(&space).await
    }

    async fn usage(&self, space: &Space) -> AppResult<StorageSummary> {
        let (owner, quota_bytes) = self.quota(space)?;
        let mut tx = self.pool.begin().await?;
        sqlx::query("set transaction isolation level repeatable read, read only")
            .execute(&mut *tx)
            .await?;
        let (used_bytes,reserved_bytes,documents,bytes): (i64,i64,i64,i64) = sqlx::query_as("select coalesce((select sum(size) from document where quota_owner=$1),0)::bigint, coalesce((select sum(size) from document_upload where quota_owner=$1 and status='pending'),0)::bigint, (select count(*) from document where space_id=$2), coalesce((select sum(size) from document where space_id=$2),0)::bigint")
            .bind(owner).bind(space.id).fetch_one(&mut *tx).await?;
        let types = sqlx::query_as("with grouped as (select mime,count(*)::bigint as documents,sum(size)::bigint as bytes from document where space_id=$1 group by mime), ranked as (select *,row_number() over(order by bytes desc,mime) as rank from grouped) select case when rank<=20 then mime else 'other' end as mime,sum(documents)::bigint as documents,sum(bytes)::bigint as bytes from ranked group by 1 order by bytes desc,mime")
            .bind(space.id).fetch_all(&mut *tx).await?;
        tx.commit().await?;
        Ok(StorageSummary {
            quota_bytes,
            used_bytes,
            reserved_bytes,
            documents,
            bytes,
            types,
            max_file_bytes: self.config.limits.file_bytes,
            uploads_enabled: self.config.uploads_enabled,
            processing_enabled: false,
        })
    }

    pub async fn preflight(
        &self,
        actor: &str,
        id: Uuid,
        input: Preflight,
    ) -> AppResult<PreflightResult> {
        let folder = db::folder(&self.pool, id).await?;
        let space = spaces::authorize(
            &self.pool,
            &self.fga,
            actor,
            folder.space_id,
            Permission::Write,
        )
        .await
        .map_err(dependency_error)?;
        if input.files.is_empty() || input.files.len() > 200 {
            return Err(invalid("Preflight accepts 1..200 files"));
        }
        let mut names = Vec::with_capacity(input.files.len());
        for file in input.files {
            names.push(upload::name(&file.name)?);
            if file.size > self.config.limits.file_bytes {
                return Err(AppError::problem(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "file_too_large",
                    "A selected file exceeds the configured limit",
                ));
            }
        }
        let conflicts = sqlx::query_scalar("select name from document where space_id=$1 and folder_id=$2 and name=any($3) union select name from document_upload where space_id=$1 and folder_id=$2 and name=any($3) and status='pending' order by name")
            .bind(space.id).bind(id).bind(&names).fetch_all(&self.pool).await?;
        Ok(PreflightResult {
            conflicts,
            storage: self.usage(&space).await?,
        })
    }

    pub async fn directory(
        pool: &sqlx::PgPool,
        fga: &crate::fga::Fga,
        actor: &str,
        space: Uuid,
        query: EntryQuery,
    ) -> AppResult<Directory> {
        if query
            .search
            .as_ref()
            .is_some_and(|s| s.chars().count() > 255)
        {
            return Err(invalid("Directory search exceeds 255 characters"));
        }
        spaces::authorize(pool, fga, actor, space, Permission::Read)
            .await
            .map_err(dependency_error)?;
        let can_write = fga
            .check(actor, Permission::Write, space)
            .await
            .map_err(|_| unavailable())?;
        let mut tx = pool.begin().await?;
        sqlx::query("set transaction isolation level repeatable read, read only")
            .execute(&mut *tx)
            .await?;
        let ancestors = db::folder_ancestors(&mut *tx, space, query.parent_id).await?;
        let total: i64 = directory_selection("select count(*)", space, &query)
            .build_query_scalar()
            .fetch_one(&mut *tx)
            .await?;
        let order = match query.order.unwrap_or_default() {
            EntryOrder::SizeAsc => " order by kind,size asc nulls last,name,id",
            EntryOrder::SizeDesc => " order by kind,size desc nulls last,name,id",
            EntryOrder::NameAsc => " order by kind,name,id",
            EntryOrder::NameDesc => " order by kind,name desc,id desc",
            EntryOrder::CreatedAsc => " order by kind,created_at,id",
            EntryOrder::CreatedDesc => " order by kind,created_at desc,id desc",
        };
        let offset = query.offset.unwrap_or(0).max(0);
        let limit = query.limit.unwrap_or(50).clamp(1, 200);
        let mut sql = directory_selection("select kind,id,name,created_at", space, &query);
        sql.push(order)
            .push(" limit ")
            .push_bind(limit)
            .push(" offset ")
            .push_bind(offset);
        let rows: Vec<(i32, Uuid, String, chrono::DateTime<chrono::Utc>)> =
            sql.build_query_as().fetch_all(&mut *tx).await?;
        let folders: Vec<Uuid> = rows.iter().filter(|r| r.0 == 0).map(|r| r.1).collect();
        let documents: Vec<Uuid> = rows.iter().filter(|r| r.0 == 1).map(|r| r.1).collect();
        let mut folder_rows: std::collections::HashMap<Uuid, Folder> =
            sqlx::query_as::<_, Folder>("select * from folder where id=any($1)")
                .bind(&folders)
                .fetch_all(&mut *tx)
                .await?
                .into_iter()
                .map(|f| (f.id, f))
                .collect();
        let mut document_rows: std::collections::HashMap<Uuid, Document> =
            sqlx::query_as::<_, Document>("select * from document where id=any($1)")
                .bind(&documents)
                .fetch_all(&mut *tx)
                .await?
                .into_iter()
                .map(|d| (d.id, d))
                .collect();
        let items = rows
            .into_iter()
            .map(|r| {
                if r.0 == 0 {
                    folder_rows.remove(&r.1).map(Entry::Folder)
                } else {
                    document_rows.remove(&r.1).map(Entry::Document)
                }
                .ok_or_else(unavailable)
            })
            .collect::<AppResult<Vec<_>>>()?;
        let processing = crate::processing::store::summaries(&mut *tx, &documents).await?;
        tx.commit().await?;
        Ok(Directory {
            items,
            ancestors,
            total,
            offset,
            limit,
            can_write,
            processing_enabled: false,
            processing,
        })
    }

    /// Hold one chunk until EOF/checksum verification so corruption cannot look complete.
    pub async fn content(&self, actor: &str, id: Uuid) -> AppResult<Response> {
        let document = db::document(&self.pool, id).await?;
        spaces::authorize(
            &self.pool,
            &self.fga,
            actor,
            document.space_id,
            Permission::Read,
        )
        .await
        .map_err(dependency_error)?;
        self.stream_original(document).await
    }

    /// The caller has already checked the document's exact owning-space authority.
    pub(crate) async fn stream_original(&self, document: Document) -> AppResult<Response> {
        let id = document.id;
        let permit = self.downloads.clone().try_acquire_owned().map_err(|_| {
            AppError::problem(
                StatusCode::TOO_MANY_REQUESTS,
                "transfer_capacity",
                "All document transfer slots are busy",
            )
        })?;
        let key: String = sqlx::query_scalar("select object_key from document where id=$1")
            .bind(id)
            .fetch_one(&self.pool)
            .await?;
        if !key.starts_with(&self.prefix) {
            return Err(unavailable());
        }
        let object = self.objects.get(&key).await.map_err(|_| unavailable())?;
        if object.content_length() != Some(document.size) {
            return Err(unavailable());
        }
        let reader = object.body.into_async_read();
        let deadline = tokio::time::Instant::now() + self.deadline();
        let idle = self.idle();
        let expected = document.sha256.clone();
        let size = document.size;
        let (sender, receiver) = tokio::sync::mpsc::channel(1);
        let task = tokio::spawn(async move {
            let _permit = permit;
            let outcome=async {
                let mut reader=reader;
                let mut pending=Vec::new();
                let mut hash=Sha256::new();
                let mut read=0_i64;
                loop {
                    let mut buffer=[0_u8;64*1024];
                    let n=tokio::time::timeout_at(deadline.min(tokio::time::Instant::now()+idle),reader.read(&mut buffer)).await
                        .map_err(|_|std::io::Error::other("original download timed out"))??;
                    if n==0 {
                        if read!=size || format!("{:x}",hash.finalize())!=expected {
                            tracing::error!(document_id=%id, outcome="integrity_failure", "original download interrupted");
                            return Err(std::io::Error::other("original integrity failure"));
                        }
                        if !pending.is_empty() {
                            tokio::time::timeout_at(deadline,sender.send(Ok(Bytes::from(pending)))).await
                                .map_err(|_|std::io::Error::other("original download timed out"))?
                                .map_err(|_|std::io::Error::other("original download cancelled"))?;
                        }
                        return Ok(());
                    }
                    read+=n as i64;
                    if read>size { return Err(std::io::Error::other("original length mismatch")); }
                    hash.update(&buffer[..n]);
                    let emit=std::mem::replace(&mut pending,buffer[..n].to_vec());
                    if !emit.is_empty() {
                        tokio::time::timeout_at(deadline,sender.send(Ok(Bytes::from(emit)))).await
                            .map_err(|_|std::io::Error::other("original download timed out"))?
                            .map_err(|_|std::io::Error::other("original download cancelled"))?;
                    }
                }
            }.await;
            if let Err(error) = outcome {
                let _ = sender.try_send(Err(error));
            }
        });
        let stream = futures::stream::unfold(
            (receiver, AbortDownload(task)),
            |(mut receiver, task)| async move {
                receiver.recv().await.map(|chunk| (chunk, (receiver, task)))
            },
        );
        let disposition = format!(
            "attachment; filename=\"document\"; filename*=UTF-8''{}",
            percent_encoding::utf8_percent_encode(
                &document.name,
                percent_encoding::NON_ALPHANUMERIC
            )
        );
        Ok((
            [
                (header::CONTENT_TYPE, "application/octet-stream".to_owned()),
                (header::CONTENT_LENGTH, document.size.to_string()),
                (header::CONTENT_DISPOSITION, disposition),
                (header::CACHE_CONTROL, "private, no-store".to_owned()),
                (header::X_CONTENT_TYPE_OPTIONS, "nosniff".to_owned()),
            ],
            Body::from_stream(stream),
        )
            .into_response())
    }
}

// Dropping an HTTP response cancels its producer, including a stalled upstream read.
struct AbortDownload(tokio::task::JoinHandle<()>);
impl Drop for AbortDownload {
    fn drop(&mut self) {
        self.0.abort();
    }
}

// Count and page share the same root/child and literal-search predicates.
fn directory_selection(
    select: &'static str,
    space: Uuid,
    query: &EntryQuery,
) -> sqlx::QueryBuilder<sqlx::Postgres> {
    let mut sql = sqlx::QueryBuilder::new(select);
    sql.push(" from (");
    for (index, (projection, table, parent)) in [
        (
            "0 as kind,id,name,created_at,null::bigint as size",
            "folder",
            "parent_id",
        ),
        ("1 as kind,id,name,created_at,size", "document", "folder_id"),
    ]
    .into_iter()
    .enumerate()
    {
        if index != 0 {
            sql.push(" union all ");
        }
        sql.push("select ")
            .push(projection)
            .push(" from ")
            .push(table)
            .push(" where space_id=")
            .push_bind(space)
            .push(" and ")
            .push(parent);
        match query.parent_id {
            Some(id) => {
                sql.push("=").push_bind(id);
            }
            None => {
                sql.push(" is null");
            }
        }
    }
    sql.push(") entries");
    if let Some(search) = query.search.as_ref().filter(|s| !s.is_empty()) {
        sql.push(" where strpos(lower(name),lower(")
            .push_bind(search.clone())
            .push("))>0");
    }
    sql
}
