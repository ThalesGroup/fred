// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use crate::domain::{Document, Folder};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

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

#[derive(Clone, Debug, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct UploadReceipt {
    pub request_key: Uuid,
    pub space_id: Uuid,
    pub folder_id: Uuid,
    pub name: String,
    pub mime: String,
    pub size: i64,
    pub sha256: String,
    pub status: UploadStatus,
    pub document_id: Option<Uuid>,
    pub error_code: Option<String>,
    pub created_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
    pub acknowledged_at: Option<DateTime<Utc>>,
    pub successor_key: Option<Uuid>,
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
    pub files: Vec<Candidate>,
}
#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Candidate {
    pub name: String,
    pub size: u64,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct PreflightResult {
    pub conflicts: Vec<String>,
    pub storage: StorageSummary,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct StorageSummary {
    pub quota_bytes: i64,
    pub used_bytes: i64,
    pub reserved_bytes: i64,
    pub max_file_bytes: u64,
    pub uploads_enabled: bool,
    pub documents: i64,
    pub bytes: i64,
    pub types: Vec<TypeUsage>,
}
#[derive(Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct TypeUsage {
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
}

#[derive(Deserialize, Default, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReceiptQuery {
    pub before: Option<DateTime<Utc>>,
    pub before_key: Option<Uuid>,
    pub limit: Option<i64>,
}

#[derive(Deserialize, Default, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct UploadQuery {
    pub retry_of: Option<Uuid>,
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
