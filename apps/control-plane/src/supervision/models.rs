// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use chrono::{DateTime, Utc};
use serde::Serialize;
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    domain::Role,
    processing::models::{ProcessingStatus, Stage},
};

#[derive(Default, Serialize, ToSchema)]
pub struct DocumentCounts {
    pub documents: i64,
    /// Logical original bytes recorded in SQL, not physical storage usage.
    pub bytes: i64,
}

#[derive(Serialize, ToSchema)]
pub struct ProcessingCount {
    pub status: ProcessingStatus,
    pub stage: Stage,
    pub documents: i64,
}

#[derive(Default, Serialize, ToSchema)]
pub struct PublicationCounts {
    pub documents: i64,
    /// Committed manifest counts; no OpenSearch presence check.
    pub chunks: i64,
    pub vectors: i64,
    /// Published datasets/*.parquet artifacts, not SQL tables.
    pub tabular_datasets: i64,
    pub known_rows: i64,
    pub datasets_with_unknown_rows: i64,
    /// Null when at least one dataset has no attributable row count.
    #[schema(required = true)]
    pub total_rows: Option<i64>,
}

#[derive(Serialize, ToSchema)]
pub struct RoleAssignments {
    pub role: Role,
    /// Direct (user, space, role) tuples, never effective/inherited grants.
    pub assignments: u64,
}

#[derive(Default, Serialize, ToSchema)]
pub struct SupervisionCounts {
    pub active: DocumentCounts,
    /// Remaining SQL documents retired directly or through their owning space.
    pub pending_purge: DocumentCounts,
    /// Latest attempt per active document. Missing status/stage pairs mean zero.
    pub processing: Vec<ProcessingCount>,
    pub failed_documents: i64,
    pub published: PublicationCounts,
    /// Union of direct subjects; never sum role columns or child distinct counts.
    pub distinct_users: u64,
    /// Roles with no direct attribution are omitted (zero).
    pub direct_roles: Vec<RoleAssignments>,
}

#[derive(Serialize, ToSchema)]
pub struct TeamSupervision {
    pub id: Uuid,
    pub name: String,
    /// Includes the team's projects, without inherited organization roles.
    pub counts: SupervisionCounts,
}

#[derive(Serialize, ToSchema)]
pub struct SupervisionTeamsPage {
    pub items: Vec<TeamSupervision>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Serialize, ToSchema)]
pub struct OrganizationSupervision {
    pub organization_id: Uuid,
    pub collection_started_at: DateTime<Utc>,
    /// Collection bounds, not an atomic SQL/OpenFGA snapshot.
    pub collection_finished_at: DateTime<Utc>,
    pub active_teams: u64,
    pub totals: SupervisionCounts,
    pub organization_direct: SupervisionCounts,
    pub teams_total: SupervisionCounts,
    /// All personal spaces aggregated; no personal identity or space is exposed.
    pub personal_total: SupervisionCounts,
    /// UUID ascending, at most 100 teams. Totals never depend on this page.
    pub teams: SupervisionTeamsPage,
}

#[derive(Serialize, ToSchema)]
pub struct TeamSupervisionDetail {
    pub organization_id: Uuid,
    pub collection_started_at: DateTime<Utc>,
    pub collection_finished_at: DateTime<Utc>,
    pub team: TeamSupervision,
}
