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
    models::{UploadQuery, UploadReceipt, UploadRow, UploadStatus},
    unavailable,
};
use crate::{
    auth::CurrentUser,
    db,
    domain::{Folder, Permission, Space},
    error::{AppError, AppResult},
    onboarding, spaces,
};

pub(crate) struct Spool {
    pub path: tempfile::TempPath,
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
fn malformed(error: axum::extract::multipart::MultipartError) -> AppError {
    if error.status() == StatusCode::PAYLOAD_TOO_LARGE {
        AppError::problem(
            StatusCode::PAYLOAD_TOO_LARGE,
            "file_too_large",
            "The file exceeds the configured limit",
        )
    } else {
        AppError::problem(
            StatusCode::BAD_REQUEST,
            "invalid_multipart",
            "Invalid multipart upload",
        )
    }
}

fn token_current(user: &CurrentUser) -> AppResult<()> {
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
    /// Uploads retain a pod-local permit through verification/publication, not a SQL lock.
    pub async fn upload(
        &self,
        user: &CurrentUser,
        folder_id: Uuid,
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
        let folder = db::folder(&self.pool, folder_id).await?;
        let space = spaces::authorize(
            &self.pool,
            &self.fga,
            &user.uid,
            folder.space_id,
            Permission::Write,
        )
        .await
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
            .map_err(|_| {
                AppError::problem(
                    StatusCode::REQUEST_TIMEOUT,
                    "upload_timeout",
                    "The file transfer exceeded its deadline",
                )
            })??;
        let (fresh, row) = self
            .reserve(user, &space, &folder, key, &spool, choices)
            .await?;
        if !fresh {
            return Ok((false, row.receipt));
        }
        let outcome = async {
            self.objects
                .put_verified(&row.object_key, &spool.path, spool.size, &spool.digest)
                .await
                .map_err(|_| unavailable())?;
            self.publish(user, &row, processing).await
        }
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

    async fn spool(&self, mut multipart: Multipart) -> AppResult<Spool> {
        let path = self.temp.path().to_owned();
        let file = tokio::task::spawn_blocking(move || tempfile::NamedTempFile::new_in(path))
            .await
            .map_err(|_| unavailable())?
            .map_err(|_| unavailable())?;
        let (file, path) = file.into_parts();
        let mut file = tokio::fs::File::from_std(file);
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
                return Err(AppError::problem(
                    StatusCode::PAYLOAD_TOO_LARGE,
                    "file_too_large",
                    "The file exceeds the configured limit",
                ));
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
            path,
            name,
            mime,
            size,
            digest: hash.finalize().into(),
        })
    }

    async fn writer(
        &self,
        user: &CurrentUser,
        space: Uuid,
    ) -> AppResult<Transaction<'static, Postgres>> {
        token_current(user)?;
        let mut tx = spaces::authorized_write(&self.pool, &self.fga, &user.uid, space)
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
        folder: &Folder,
        key: Uuid,
        file: &Spool,
        choices: UploadQuery,
    ) -> AppResult<(bool, UploadRow)> {
        let UploadQuery { retry_of, profile } = choices;
        let mut tx = self.writer(user, space.id).await?;
        let current = db::folder(&mut *tx, folder.id).await?;
        if current.space_id != space.id {
            return Err(AppError::NotFound);
        }
        let digest = file.sha256();
        let existing: Option<UploadRow> =
            sqlx::query_as("select * from document_upload where actor=$1 and request_key=$2")
                .bind(&user.uid)
                .bind(key)
                .fetch_optional(&mut *tx)
                .await?;
        if let Some(row) = existing {
            if row.receipt.folder_id != folder.id
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
            return match row.receipt.status {
                UploadStatus::Stored => Ok((false, row)),
                UploadStatus::Pending => Err(conflict(
                    "upload_in_progress",
                    "The original request is still being resolved",
                )),
                UploadStatus::Failed => Err(conflict(
                    "upload_failed",
                    "This attempt failed; start an explicit retry",
                )),
            };
        }
        let predecessor: Option<UploadRow> = if let Some(retry) = retry_of {
            let previous: UploadRow = sqlx::query_as(
                "select * from document_upload where actor=$1 and request_key=$2 for update",
            )
            .bind(&user.uid)
            .bind(retry)
            .fetch_one(&mut *tx)
            .await?;
            if previous.receipt.status != UploadStatus::Failed
                || previous.receipt.folder_id != folder.id
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
        let name_taken: bool = sqlx::query_scalar("select exists(select 1 from document where deletion_id is null and space_id=$1 and folder_id=$2 and name=$3) or exists(select 1 from document_upload where space_id=$1 and folder_id=$2 and name=$3 and status='pending')")
            .bind(space.id).bind(folder.id).bind(&file.name).fetch_one(&mut *tx).await?;
        if name_taken {
            return Err(conflict(
                "name_conflict",
                "A document with this name already exists or is being uploaded",
            ));
        }
        let (owner, limit) = self.quota(space)?;
        let usage: i64 = sqlx::query_scalar("select coalesce((select sum(size) from document where deletion_id is null and quota_owner=$1),0)::bigint + coalesce((select sum(size) from document_upload where quota_owner=$1 and status='pending'),0)::bigint")
            .bind(owner).fetch_one(&mut *tx).await?;
        if file.size > limit.saturating_sub(usage) {
            return Err(AppError::problem(
                StatusCode::UNPROCESSABLE_ENTITY,
                "quota_exceeded",
                "The destination storage quota is exhausted",
            ));
        }
        let backlog: i64 = sqlx::query_scalar("select coalesce((select sum(size) from document_upload where status='failed' and cleaned_at is null),0)::bigint + coalesce((select orphan_bytes from document_storage where singleton),0)").fetch_one(&mut *tx).await?;
        if backlog >= self.config.limits.cleanup_backlog_bytes {
            return Err(unavailable());
        }
        let id = Uuid::new_v4();
        let object_key = format!("{}{id}/input/{}", self.prefix, file.name);
        if object_key.len() > 1024 {
            return Err(invalid(
                "The encoded document path exceeds the object-store key limit",
            ));
        }
        let row: UploadRow = sqlx::query_as("insert into document_upload (id,request_key,actor,organization_id,space_id,folder_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,retry_of,processing_profile) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'pending',clock_timestamp()+make_interval(secs=>$13),$14,$15) returning *")
            .bind(id).bind(key).bind(&user.uid).bind(space.organization).bind(space.id).bind(folder.id).bind(owner)
            .bind(&file.name).bind(&file.mime).bind(file.size).bind(&digest).bind(object_key)
            .bind(self.config.limits.lease_seconds() as f64).bind(predecessor.as_ref().map(|p|p.id)).bind(profile).fetch_one(&mut *tx).await?;
        if let Some(previous) = predecessor {
            sqlx::query("update document_upload set successor_key=$2, acknowledged_at=clock_timestamp() where id=$1").bind(previous.id).bind(key).execute(&mut *tx).await?;
        }
        tx.commit().await?;
        tracing::info!(operation_id=%id, space_id=%space.id, actor_uid=%user.uid, bytes=file.size, outcome="reserved", "document upload");
        Ok((true, row))
    }

    async fn publish(
        &self,
        user: &CurrentUser,
        upload: &UploadRow,
        processing: Option<&crate::processing::Processing>,
    ) -> AppResult<UploadReceipt> {
        let mut tx = self.writer(user, upload.receipt.space_id).await?;
        let row: UploadRow = sqlx::query_as("select * from document_upload where id=$1 for update")
            .bind(upload.id)
            .fetch_one(&mut *tx)
            .await?;
        if row.receipt.status != UploadStatus::Pending || row.expires_at <= Utc::now() {
            return Err(conflict(
                "upload_expired",
                "This upload can no longer be published",
            ));
        }
        db::folder(&mut *tx, row.receipt.folder_id).await?;
        sqlx::query("insert into document (id,space_id,folder_id,name,mime,size,sha256,created_by,object_key,quota_owner) values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)")
            .bind(row.id).bind(row.receipt.space_id).bind(row.receipt.folder_id).bind(&row.receipt.name).bind(&row.receipt.mime).bind(row.receipt.size).bind(&row.receipt.sha256).bind(&row.actor).bind(&row.object_key).bind(row.quota_owner).execute(&mut *tx).await?;
        let receipt = sqlx::query_as("update document_upload set status='stored',document_id=id,completed_at=clock_timestamp() where id=$1 and status='pending' and expires_at>clock_timestamp() returning *")
            .bind(row.id).fetch_one(&mut *tx).await?;
        if let Some(profile) = row.receipt.processing_profile {
            processing
                .ok_or_else(crate::processing::unavailable)?
                .admit(
                    &mut tx,
                    &row.actor,
                    row.receipt.request_key,
                    row.id,
                    row.organization_id,
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

    pub(crate) async fn fail(&self, id: Uuid, code: &str) -> AppResult<()> {
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
