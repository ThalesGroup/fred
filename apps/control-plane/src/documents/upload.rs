// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use axum::{extract::Multipart, http::StatusCode};
use chrono::Utc;
use sha2::{Digest, Sha256};
use sqlx::{Postgres, Transaction};
use tokio::io::AsyncWriteExt;
use unicode_normalization::UnicodeNormalization;
use uuid::Uuid;

use super::{
    Storage, conflict, dependency_error, invalid,
    models::{Destination, UploadQuery, UploadReceipt, UploadRow, UploadStatus},
    unavailable,
};
use crate::{
    auth::CurrentUser,
    db,
    domain::{Permission, Space},
    error::{AppError, AppResult},
    onboarding,
};

pub(crate) struct Spool {
    pub file: tokio::fs::File,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub digest: [u8; 32],
}
impl Spool {
    pub fn sha256(&self) -> String {
        self.digest.iter().map(|b| format!("{b:02x}")).collect()
    }
}

pub(crate) struct SourceUpload<'a> {
    pub actor: &'a str,
    pub key: Uuid,
    pub destination: Destination,
    pub file: &'a Spool,
    pub profile: Option<crate::processing::models::Profile>,
    pub retry_of: Option<Uuid>,
    pub target: Option<Uuid>,
    pub source: Option<(Uuid, &'a str, &'a str)>,
}

pub(crate) fn name(value: &str) -> AppResult<String> {
    let name: String = value.nfc().collect();
    if name.trim().is_empty()
        || name.chars().count() > 255
        || name == "."
        || name == ".."
        || name
            .chars()
            .any(|c| c.is_control() || c == '/' || c == '\\')
    {
        return Err(invalid(
            "A filename must contain 1..255 characters without paths or control characters",
        ));
    }
    Ok(name)
}

fn stalled() -> AppError {
    AppError::problem(
        StatusCode::REQUEST_TIMEOUT,
        "upload_timeout",
        "The file transfer stalled",
    )
}
pub(crate) fn exceeded() -> AppError {
    AppError::problem(
        StatusCode::REQUEST_TIMEOUT,
        "upload_timeout",
        "The file transfer exceeded its deadline",
    )
}
fn too_large() -> AppError {
    AppError::problem(
        StatusCode::PAYLOAD_TOO_LARGE,
        "file_too_large",
        "The file exceeds the configured limit",
    )
}
fn malformed(error: axum::extract::multipart::MultipartError) -> AppError {
    if error.status() == StatusCode::PAYLOAD_TOO_LARGE {
        too_large()
    } else {
        AppError::problem(
            StatusCode::BAD_REQUEST,
            "invalid_multipart",
            "Invalid multipart upload",
        )
    }
}

/// A known request key answers with its stored result, or says why it cannot yet.
pub(crate) fn replayed(status: UploadStatus) -> AppResult<()> {
    match status {
        UploadStatus::Stored => Ok(()),
        UploadStatus::Pending => Err(in_progress()),
        UploadStatus::Failed => Err(conflict(
            "upload_failed",
            "This attempt failed; start an explicit retry",
        )),
    }
}
pub(crate) fn in_progress() -> AppError {
    conflict(
        "upload_in_progress",
        "The original request is still being resolved",
    )
}

pub(crate) fn token_current(user: &CurrentUser) -> AppResult<()> {
    if user
        .valid_until
        .is_some_and(|deadline| Utc::now().timestamp_millis() as f64 / 1000.0 >= deadline)
    {
        return Err(AppError::problem(
            StatusCode::UNAUTHORIZED,
            "token_expired",
            "The authentication token expired during upload",
        ));
    }
    Ok(())
}

impl Storage {
    /// Server-produced bytes reuse the private spool and checksum used by multipart uploads.
    pub(crate) async fn spool_bytes(
        &self,
        filename: &str,
        mime: &str,
        bytes: &[u8],
    ) -> AppResult<Spool> {
        if bytes.len() as u64 > self.config.limits.file_bytes || bytes.len() > 32 * 1024 * 1024 {
            return Err(invalid("Configuration file exceeds the upload limit"));
        }
        let name = name(filename)?;
        let mut file = self.spool_file().await?;
        file.write_all(bytes).await.map_err(|_| unavailable())?;
        file.flush().await.map_err(|_| unavailable())?;
        Ok(Spool {
            file,
            name,
            mime: mime.to_owned(),
            size: bytes.len() as i64,
            digest: Sha256::digest(bytes).into(),
        })
    }

    /// Uploads retain a pod-local permit through verification/publication, not a SQL lock.
    pub async fn upload(
        &self,
        user: &CurrentUser,
        destination: Destination,
        key: Uuid,
        choices: UploadQuery,
        multipart: Multipart,
        processing: Option<&crate::processing::Processing>,
    ) -> AppResult<(bool, UploadReceipt)> {
        let profile = choices.profile;
        if !self.config.uploads_enabled {
            return Err(unavailable());
        }
        if profile.is_some() && processing.is_none_or(|p| !p.config.enabled) {
            return Err(crate::processing::unavailable());
        }
        let _permit = self.uploads.clone().try_acquire_owned().map_err(|_| {
            AppError::problem(
                StatusCode::TOO_MANY_REQUESTS,
                "transfer_capacity",
                "All document transfer slots are busy",
            )
        })?;
        let space = match destination {
            Destination::Folder(id) => {
                let folder = db::folder(&self.pool, id).await?;
                crate::authorization::authorize(
                    &self.pool,
                    &user.uid,
                    folder.space_id,
                    Permission::Write,
                )
                .await
            }
            Destination::Conversation {
                space_id,
                session_id,
            } => crate::sessions::require_owner(&self.pool, &user.uid, space_id, session_id).await,
        }
        .map_err(dependency_error)?;
        if profile.is_some() {
            Box::pin(
                processing
                    .ok_or_else(crate::processing::unavailable)?
                    .derived
                    .validate_bucket(),
            )
            .await
            .map_err(|_| crate::processing::unavailable())?;
        }
        let spool = tokio::time::timeout(self.deadline(), self.spool(multipart))
            .await
            .map_err(|_| exceeded())??;
        let reserved = self
            .reserve(user, &space, destination, key, &spool, choices)
            .await;
        // A concurrent key/name conflict rolls back before replaying the winning reservation.
        let (fresh, row) = if reserved.is_err()
            && sqlx::query_scalar::<_, bool>(
                "select exists(select 1 from document_upload where actor=$1 and request_key=$2)",
            )
            .bind(&user.uid)
            .bind(key)
            .fetch_one(&self.pool)
            .await?
        {
            self.reserve(user, &space, destination, key, &spool, choices)
                .await?
        } else {
            reserved?
        };
        if !fresh {
            return Ok((false, row.receipt));
        }
        // Boxed: inline, this future overflows a 2 MiB test-thread stack in debug builds.
        let outcome = Box::pin(async {
            self.transfer_upload(row.id, &row.object_key, spool).await?;
            self.publish(user, destination, &row, processing).await
        })
        .await;
        match outcome {
            Ok(receipt) => Ok((true, receipt)),
            Err(error) => {
                let code = match &error {
                    AppError::Forbidden | AppError::Denied(_) => "access_changed",
                    AppError::Problem { code, .. } => *code,
                    _ => "upload_interrupted",
                };
                if self.fail(row.id, code).await.is_err() {
                    tracing::warn!(operation_id=%row.id, outcome="uncertain", "upload outcome awaits reconciliation");
                }
                Err(error)
            }
        }
    }

    /// Shared journal acknowledgement and read-back verification, always outside SQL transactions.
    pub(crate) async fn transfer_upload(&self, id: Uuid, key: &str, spool: Spool) -> AppResult<()> {
        let (certain, result) = self
            .objects
            .put_file(key, spool.file, spool.size, &spool.digest)
            .await;
        if certain {
            // The database runs local and organization reservation accounting.
            sqlx::query("update document_upload set put_pending=false where id=$1")
                .bind(id)
                .execute(&self.pool)
                .await?;
        }
        result.map_err(|_| unavailable())?;
        self.objects
            .verify(key, spool.size, &spool.digest)
            .await
            .map_err(|_| unavailable())
    }

    /// An anonymous spool has no durable pathname, including before reservation.
    /// Its inode is released on close or process loss; other replicas need no reaper.
    async fn spool_file(&self) -> AppResult<tokio::fs::File> {
        let path = self.temp.path().to_owned();
        let file = tokio::task::spawn_blocking(move || tempfile::tempfile_in(path))
            .await
            .map_err(|_| unavailable())?
            .map_err(|_| unavailable())?;
        Ok(tokio::fs::File::from_std(file))
    }

    /// Stored bytes are copied, never trusted: a length or digest mismatch fails the copy.
    pub(crate) async fn spool_object(
        &self,
        key: &str,
        name: String,
        mime: String,
        size: i64,
        sha256: &str,
    ) -> AppResult<Spool> {
        if size as u64 > self.config.limits.file_bytes {
            return Err(too_large());
        }
        let mut file = self.spool_file().await?;
        let digest = self
            .objects
            .read_to(key, size, &mut file)
            .await
            .map_err(|_| unavailable())?;
        file.flush().await.map_err(|_| unavailable())?;
        let spool = Spool {
            file,
            name,
            mime,
            size,
            digest,
        };
        if spool.sha256() != sha256 {
            return Err(unavailable());
        }
        Ok(spool)
    }

    pub(crate) async fn spool(&self, mut multipart: Multipart) -> AppResult<Spool> {
        let mut file = self.spool_file().await?;
        let mut field = tokio::time::timeout(self.idle(), multipart.next_field())
            .await
            .map_err(|_| stalled())?
            .map_err(malformed)?
            .ok_or_else(|| invalid("Exactly one file field is required"))?;
        if field.name() != Some("file") {
            return Err(invalid("Exactly one file field is required"));
        }
        let name = name(
            field
                .file_name()
                .ok_or_else(|| invalid("A filename is required"))?,
        )?;
        let mime = field
            .content_type()
            .unwrap_or("application/octet-stream")
            .to_owned();
        if mime.len() > 127 || !mime.is_ascii() || mime.chars().any(char::is_control) {
            return Err(invalid("Invalid file media type"));
        }
        let mut size = 0_i64;
        let mut hash = Sha256::new();
        while let Some(chunk) = tokio::time::timeout(self.idle(), field.chunk())
            .await
            .map_err(|_| stalled())?
            .map_err(malformed)?
        {
            size += chunk.len() as i64;
            if size as u64 > self.config.limits.file_bytes {
                return Err(too_large());
            }
            hash.update(&chunk);
            file.write_all(&chunk).await.map_err(|_| unavailable())?;
        }
        drop(field);
        if tokio::time::timeout(self.idle(), multipart.next_field())
            .await
            .map_err(|_| stalled())?
            .map_err(malformed)?
            .is_some()
        {
            return Err(invalid("Exactly one file field is required"));
        }
        file.flush().await.map_err(|_| unavailable())?;
        Ok(Spool {
            file,
            name,
            mime,
            size,
            digest: hash.finalize().into(),
        })
    }

    /// A folder needs write access to its space; a conversation, only its live ownership.
    async fn writer(
        &self,
        user: &CurrentUser,
        destination: Destination,
        space: Uuid,
    ) -> AppResult<Transaction<'static, Postgres>> {
        token_current(user)?;
        let mut tx =
            super::authorized_mutation(&self.pool, &user.uid, space, destination.columns().1)
                .await
                .map_err(super::dependency_error)?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &user.uid).await?;
        token_current(user)?;
        Ok(tx)
    }

    async fn reserve(
        &self,
        user: &CurrentUser,
        space: &Space,
        destination: Destination,
        key: Uuid,
        file: &Spool,
        choices: UploadQuery,
    ) -> AppResult<(bool, UploadRow)> {
        let UploadQuery { retry_of, profile } = choices;
        let mut tx = self.writer(user, destination, space.id).await?;
        if let Destination::Folder(id) = destination
            && db::folder(&mut *tx, id).await?.space_id != space.id
        {
            return Err(AppError::NotFound);
        }
        if let Destination::Folder(id) = destination {
            crate::knowledge_bases::documents::require_manual_folder(&mut *tx, id).await?;
        }
        let (folder_id, session_id) = destination.columns();
        let placed = |r: &UploadReceipt| {
            r.space_id == space.id && r.folder_id == folder_id && r.session_id == session_id
        };
        let digest = file.sha256();
        let existing: Option<UploadRow> =
            sqlx::query_as("select *, case when status='stored' then id end as document_id from document_upload where actor=$1 and request_key=$2")
                .bind(&user.uid)
                .bind(key)
                .fetch_optional(&mut *tx)
                .await?;
        if let Some(row) = existing {
            if !placed(&row.receipt)
                || row.receipt.name != file.name
                || row.receipt.size != file.size
                || row.receipt.sha256 != digest
                || row.receipt.processing_profile != profile
            {
                return Err(conflict(
                    "idempotency_conflict",
                    "This request key identifies different content or a different destination",
                ));
            }
            replayed(row.receipt.status)?;
            return Ok((false, row));
        }
        let predecessor: Option<UploadRow> = if let Some(retry) = retry_of {
            let previous: UploadRow = sqlx::query_as(
                "select *, case when status='stored' then id end as document_id from document_upload where actor=$1 and request_key=$2 for update",
            )
            .bind(&user.uid)
            .bind(retry)
            .fetch_one(&mut *tx)
            .await?;
            if previous.receipt.status != UploadStatus::Failed
                || !placed(&previous.receipt)
                || previous.receipt.name != file.name
                || previous.receipt.sha256 != digest
                || previous.receipt.size != file.size
                || previous.receipt.processing_profile != profile
            {
                return Err(conflict(
                    "invalid_retry",
                    "The retry must match a failed upload and its original destination",
                ));
            }
            if previous.receipt.successor_key.is_some() {
                return Err(conflict(
                    "retry_superseded",
                    "A retry already exists; consult the original receipt",
                ));
            }
            Some(previous)
        } else {
            None
        };
        // Names are unique per folder or per conversation; each predicate matches the unique indexes.
        let (scope, target) = match destination {
            Destination::Folder(id) => (
                "select exists(select 1 from document where purpose='source' and deletion_id is null and space_id=$1 and folder_id=$2 and session_id is null and name=$3) or exists(select 1 from document_upload where purpose='source' and space_id=$1 and folder_id=$2 and session_id is null and name=$3 and status='pending')",
                id,
            ),
            Destination::Conversation { session_id, .. } => (
                "select exists(select 1 from document where purpose='source' and deletion_id is null and space_id=$1 and folder_id is null and session_id=$2 and name=$3) or exists(select 1 from document_upload where purpose='source' and space_id=$1 and folder_id is null and session_id=$2 and name=$3 and status='pending')",
                session_id,
            ),
        };
        let name_taken: bool = sqlx::query_scalar(scope)
            .bind(space.id)
            .bind(target)
            .bind(&file.name)
            .fetch_one(&mut *tx)
            .await?;
        if name_taken {
            return Err(conflict(
                "name_conflict",
                "A document with this name already exists or is being uploaded",
            ));
        }
        if let Some(session) = session_id {
            // The existing session lock serializes admissions. Stored receipts are represented
            // by their document; only pending uploads add a separate reservation.
            let (files, bytes): (i64, i64) = sqlx::query_as(
                "select count(*), coalesce(sum(size), 0)::bigint from (
                    select size from document_current where purpose='source' and space_id=$1 and session_id=$2 and deletion_id is null
                    union all
                    select size from document_upload where purpose='source' and space_id=$1 and folder_id is null and session_id=$2 and status='pending'
                ) as occupied",
            )
            .bind(space.id)
            .bind(session)
            .fetch_one(&mut *tx)
            .await?;
            if files >= i64::from(self.config.limits.conversation_files) {
                return Err(AppError::problem(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "conversation_files_exceeded",
                    "The conversation file limit is exhausted",
                ));
            }
            if file.size > self.config.limits.conversation_bytes.saturating_sub(bytes) {
                return Err(AppError::problem(
                    StatusCode::UNPROCESSABLE_ENTITY,
                    "conversation_bytes_exceeded",
                    "The conversation source byte limit is exhausted",
                ));
            }
        }
        let row = self
            .reserve_source(
                &mut tx,
                space,
                SourceUpload {
                    actor: &user.uid,
                    key,
                    destination,
                    file,
                    profile,
                    retry_of: predecessor.as_ref().map(|p| p.id),
                    target: None,
                    source: None,
                },
            )
            .await?;
        let id = row.id;
        if let Some(previous) = predecessor {
            // The database runs local and organization reservation accounting.
            sqlx::query("update document_upload set successor_key=$2, acknowledged_at=clock_timestamp() where id=$1").bind(previous.id).bind(key).execute(&mut *tx).await?;
        }
        tx.commit().await?;
        tracing::info!(operation_id=%id, space_id=%space.id, actor_uid=%user.uid, bytes=file.size, outcome="reserved", "document upload");
        Ok((true, row))
    }

    /// Shared quota reservation and durable PUT journal for every source producer.
    pub(crate) async fn reserve_source(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        space: &Space,
        upload: SourceUpload<'_>,
    ) -> AppResult<UploadRow> {
        let SourceUpload {
            actor,
            key,
            destination,
            file,
            profile,
            retry_of,
            target,
            source,
        } = upload;
        let (folder_id, session_id) = destination.columns();
        let (owner, _) = self.quota(space)?;
        self.ensure_budgets(tx, space).await?;
        self.require_cleanup_capacity(&mut **tx).await?;
        let (expected, previous_size) = match target {
            Some(document) => {
                let (content, size): (Uuid, i64) = sqlx::query_as("select d.current_content_id,c.size from document d join document_content c on c.id=d.current_content_id where d.id=$1 and d.deletion_id is null and d.space_id=$2 and d.folder_id is not distinct from $3 and d.session_id is not distinct from $4 for update of d")
                    .bind(document).bind(space.id).bind(folder_id).bind(session_id).fetch_one(&mut **tx).await?;
                (Some(content), size)
            }
            None => (None, 0),
        };
        let id = Uuid::new_v4();
        let object_key = format!("{}{id}/input/{}", self.prefix, file.name);
        if object_key.len() > 1024 {
            return Err(invalid(
                "The encoded document path exceeds the object-store key limit",
            ));
        }
        Ok(sqlx::query_as("insert into document_upload (id,request_key,actor,organization_id,space_id,folder_id,session_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,retry_of,processing_profile,put_pending,reserved_bytes,target_document_id,expected_content_id,kb_run_id,source_key,source_version) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'pending',clock_timestamp()+make_interval(secs=>$14),$15,$16,true,$17,$18,$19,$20,$21,$22) returning *, null::uuid as document_id")
            .bind(id).bind(key).bind(actor).bind(space.organization).bind(space.id).bind(folder_id).bind(session_id).bind(owner)
            .bind(&file.name).bind(&file.mime).bind(file.size).bind(file.sha256()).bind(object_key)
            .bind(self.config.limits.lease_seconds() as f64).bind(retry_of).bind(profile)
            .bind((file.size-previous_size).max(0)).bind(target).bind(expected)
            .bind(source.map(|s| s.0)).bind(source.map(|s| s.1)).bind(source.map(|s| s.2))
            .fetch_one(&mut **tx).await?)
    }

    async fn publish(
        &self,
        user: &CurrentUser,
        destination: Destination,
        upload: &UploadRow,
        processing: Option<&crate::processing::Processing>,
    ) -> AppResult<UploadReceipt> {
        let mut tx = self
            .writer(user, destination, upload.receipt.space_id)
            .await?;
        let row: UploadRow = sqlx::query_as("select *, case when status='stored' then id end as document_id from document_upload where id=$1 for update")
            .bind(upload.id)
            .fetch_one(&mut *tx)
            .await?;
        if row.receipt.status != UploadStatus::Pending || row.expires_at <= Utc::now() {
            return Err(conflict(
                "upload_expired",
                "This upload can no longer be published",
            ));
        }
        if let Destination::Folder(id) = destination {
            db::folder(&mut *tx, id).await?;
        }
        let receipt = self.store_upload(&mut tx, &row).await?;
        if let Some(profile) = row.receipt.processing_profile {
            processing
                .ok_or_else(crate::processing::unavailable)?
                .admit(
                    &mut tx,
                    &row.actor,
                    row.receipt.request_key,
                    row.id,
                    &crate::processing::models::Start {
                        profile,
                        retry_of: None,
                    },
                )
                .await?;
        }
        token_current(user)?;
        tx.commit().await?;
        tracing::info!(target:"fred.security.audit", audit_event="document.stored", operation_id=%row.id, actor_uid=%user.uid, space_id=%row.receipt.space_id, outcome="succeeded", "Document original stored");
        Ok(receipt)
    }

    /// Publish verified original bytes, or retain a replacement candidate until processing commits.
    pub(crate) async fn store_upload(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        row: &UploadRow,
    ) -> AppResult<UploadReceipt> {
        if row.receipt.status != UploadStatus::Pending || row.expires_at <= Utc::now() {
            return Err(conflict(
                "upload_expired",
                "This upload can no longer be published",
            ));
        }
        let document = row.target_document_id.unwrap_or(row.id);
        let receipt = sqlx::query_as("update document_upload set status='stored',completed_at=clock_timestamp() where id=$1 and status='pending' and not put_pending and expires_at>clock_timestamp() returning *, $2::uuid as document_id")
            .bind(row.id).bind(document).fetch_one(&mut **tx).await?;
        if row.target_document_id.is_none() {
            sqlx::query("insert into document (id,space_id,folder_id,session_id,name,created_by,quota_owner) values ($1,$2,$3,$4,$5,$6,$7)")
                .bind(document).bind(row.receipt.space_id).bind(row.receipt.folder_id).bind(row.receipt.session_id).bind(&row.receipt.name).bind(&row.actor).bind(row.quota_owner).execute(&mut **tx).await?;
        }
        sqlx::query("insert into document_content (id,document_id,kind,mime,size,sha256,object_key,published_at) values ($1,$2,'primary',$3,$4,$5,$6,clock_timestamp())")
            .bind(row.id).bind(document).bind(&row.receipt.mime).bind(row.receipt.size).bind(&row.receipt.sha256).bind(&row.object_key).execute(&mut **tx).await?;
        if row.expected_content_id.is_none() {
            sqlx::query("update document set current_content_id=$2 where id=$1")
                .bind(document)
                .bind(row.id)
                .execute(&mut **tx)
                .await?;
        }
        sqlx::query("update document_upload set target_document_id=$2,content_id=$1 where id=$1")
            .bind(row.id)
            .bind(document)
            .execute(&mut **tx)
            .await?;
        Ok(receipt)
    }

    pub(crate) async fn fail(&self, id: Uuid, code: &str) -> AppResult<()> {
        // The database runs local and organization reservation accounting.
        sqlx::query("update document_upload set status='failed',error_code=$2,completed_at=clock_timestamp() where id=$1 and status='pending'")
            .bind(id).bind(code).execute(&self.pool).await?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn filenames_have_one_safe_canonical_form() {
        assert_eq!(name("re\u{301}sume\u{301}.txt").unwrap(), "résumé.txt");
        for value in [
            "",
            " ",
            ".",
            "..",
            "../secret",
            "C:\\file",
            "x\r\nheader",
            "x\0",
        ] {
            assert!(name(value).is_err());
        }
        assert_ne!(name("A.txt").unwrap(), name("a.txt").unwrap());
    }
}
