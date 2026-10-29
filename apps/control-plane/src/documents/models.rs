// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use crate::domain::{Document, Folder};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// `pending` while the file is transferred and verified, then `stored` once published,
/// or `failed` with an `error_code`.
#[derive(
    Clone, Copy, Debug, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum UploadStatus {
    Pending,
    Stored,
    Failed,
}

/// Durable outcome of one upload request, readable by its request key.
#[derive(Clone, Debug, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct UploadReceipt {
    /// The `Idempotency-Key` that identifies this receipt.
    pub request_key: Uuid,
    pub space_id: Uuid,
    pub folder_id: Uuid,
    /// NFC-normalized filename.
    pub name: String,
    /// MIME type reported by the client; metadata, not verified.
    pub mime: String,
    /// Bytes received.
    pub size: i64,
    /// Hex SHA-256 of the received bytes.
    pub sha256: String,
    pub status: UploadStatus,
    /// Set once `stored`.
    pub document_id: Option<Uuid>,
    /// Failure code when `failed`.
    pub error_code: Option<String>,
    pub created_at: DateTime<Utc>,
    /// When the upload became `stored` or `failed`.
    pub completed_at: Option<DateTime<Utc>>,
    /// When the receipt was dismissed or superseded.
    pub acknowledged_at: Option<DateTime<Utc>>,
    /// Request key of the retry that replaced this failed upload.
    pub successor_key: Option<Uuid>,
    /// Profile requested with the upload, if any.
    pub processing_profile: Option<crate::processing::models::Profile>,
    /// Latest processing attempt of the stored document.
    #[sqlx(skip)]
    pub processing: Option<crate::processing::models::Summary>,
}

#[derive(Clone, sqlx::FromRow)]
pub(super) struct UploadRow {
    pub id: Uuid,
    pub actor: String,
    pub quota_owner: Uuid,
    pub object_key: String,
    pub expires_at: DateTime<Utc>,
    #[sqlx(flatten)]
    pub receipt: UploadReceipt,
}

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Preflight {
    /// 1..200 files to check.
    pub files: Vec<Candidate>,
}
#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Candidate {
    /// Filename as it will be uploaded.
    pub name: String,
    /// Size in bytes.
    pub size: u64,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct PreflightResult {
    /// Requested names already stored or being uploaded in the folder.
    pub conflicts: Vec<String>,
    pub storage: StorageSummary,
}
/// Storage usage of a space; a project counts against its team's quota.
#[derive(Serialize, utoipa::ToSchema)]
pub struct StorageSummary {
    /// Quota shared by the space and, for a team, its projects.
    pub quota_bytes: i64,
    /// Published bytes counted against that quota.
    pub used_bytes: i64,
    /// Bytes reserved by uploads in progress, also counted against the quota.
    pub reserved_bytes: i64,
    /// Largest accepted file.
    pub max_file_bytes: u64,
    pub uploads_enabled: bool,
    /// Whether processing can be requested.
    pub processing_enabled: bool,
    /// Documents in this space alone.
    pub documents: i64,
    /// Total size of those documents.
    pub bytes: i64,
    /// Usage by reported MIME type: the 20 largest, then `other`.
    pub types: Vec<TypeUsage>,
}
#[derive(Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct TypeUsage {
    /// Reported MIME type, or `other`.
    pub mime: String,
    pub documents: i64,
    pub bytes: i64,
}

#[derive(Serialize, utoipa::ToSchema)]
#[serde(tag = "kind", content = "data", rename_all = "snake_case")]
pub enum Entry {
    Folder(Folder),
    Document(Document),
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct Directory {
    pub items: Vec<Entry>,
    pub ancestors: Vec<Folder>,
    pub total: i64,
    pub offset: i64,
    pub limit: i64,
    pub can_write: bool,
    pub processing_enabled: bool,
    pub processing: std::collections::HashMap<Uuid, crate::processing::models::Summary>,
    /// Display names of the listed documents' `created_by`; unknown users are absent.
    pub uploaders: std::collections::HashMap<String, String>,
}

#[derive(Deserialize, Default, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReceiptQuery {
    pub before: Option<DateTime<Utc>>,
    pub before_key: Option<Uuid>,
    pub limit: Option<i64>,
}

#[derive(Clone, Copy, Deserialize, Default, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UploadQuery {
    pub retry_of: Option<Uuid>,
    /// Omitted means upload only; a profile atomically requests processing after storage.
    pub profile: Option<crate::processing::models::Profile>,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum EntryOrder {
    #[default]
    NameAsc,
    NameDesc,
    CreatedAsc,
    CreatedDesc,
    SizeAsc,
    SizeDesc,
}
#[derive(Default, Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EntryQuery {
    pub parent_id: Option<Uuid>,
    pub search: Option<String>,
    pub order: Option<EntryOrder>,
    pub offset: Option<i64>,
    pub limit: Option<i64>,
}
