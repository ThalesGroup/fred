// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use sqlx::PgPool;
use uuid::Uuid;

use crate::{
    domain::SpaceKind,
    error::{AppError, AppResult},
    processing::models::{ProcessingStatus, Stage},
};

#[derive(sqlx::FromRow)]
pub(super) struct Scope {
    pub id: Uuid,
    pub kind: SpaceKind,
    pub parent_id: Option<Uuid>,
    pub active: bool,
}

#[derive(sqlx::FromRow)]
pub(super) struct Team {
    pub id: Uuid,
    pub name: String,
}

#[derive(sqlx::FromRow)]
pub(super) struct Counts {
    pub space_id: Uuid,
    pub documents: i64,
    pub bytes: i64,
    pub purge_documents: i64,
    pub purge_bytes: i64,
    pub published_documents: i64,
    pub chunks: i64,
    pub vectors: i64,
    pub datasets: i64,
    pub known_rows: i64,
    pub unknown_datasets: i64,
}

#[derive(sqlx::FromRow)]
pub(super) struct Processing {
    pub space_id: Uuid,
    pub status: ProcessingStatus,
    pub stage: Stage,
    pub documents: i64,
}

pub(super) struct Snapshot {
    pub scopes: Vec<Scope>,
    pub teams: Vec<Team>,
    pub counts: Vec<Counts>,
    pub processing: Vec<Processing>,
}

/// SQL only: the transaction is closed before any OpenFGA enumeration.
pub(super) async fn load(
    pool: &PgPool,
    organization: Uuid,
    team: Option<Uuid>,
    after: Option<Uuid>,
) -> AppResult<Snapshot> {
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    // Recheck lifecycle inside the snapshot: the guards precede this transaction.
    crate::lifecycle::store::require_active(&mut *tx, organization).await?;
    if let Some(id) = team {
        let valid: bool = sqlx::query_scalar(
            "select exists(select 1 from space where id=$1 and organization_id=$2 and kind='team')",
        )
        .bind(id)
        .bind(organization)
        .fetch_one(&mut *tx)
        .await?;
        if !valid {
            return Err(AppError::NotFound);
        }
        crate::lifecycle::store::require_active(&mut *tx, id).await?;
    }
    let scopes = sqlx::query_as(
        "select id, kind, parent_id, deletion_id is null as active from space
         where organization_id=$1 and ($2::uuid is null or id=$2 or parent_id=$2)",
    )
    .bind(organization)
    .bind(team)
    .fetch_all(&mut *tx)
    .await?;
    let teams = sqlx::query_as(
        "select id, name from space where organization_id=$1 and kind='team'
         and deletion_id is null and ($2::uuid is null or id=$2)
         and ($3::uuid is null or id>$3) order by id limit 101",
    )
    .bind(organization)
    .bind(team)
    .bind(after)
    .fetch_all(&mut *tx)
    .await?;
    let counts = sqlx::query_as(include_str!("counts.sql"))
        .bind(organization)
        .bind(team)
        .fetch_all(&mut *tx)
        .await?;
    let processing = sqlx::query_as(
        "with latest as (
             select distinct on (p.document_id) d.space_id, p.status, p.stage
             from document_processing p join document d on d.id=p.document_id
             join space s on s.id=d.space_id
             where s.organization_id=$1 and s.deletion_id is null and d.deletion_id is null
               and d.session_id is null and ($2::uuid is null or s.id=$2 or s.parent_id=$2)
             order by p.document_id, p.created_at desc, p.id desc
         ) select space_id, status, stage, count(*) as documents
           from latest where status in ('pending','running','failed')
           group by space_id, status, stage order by space_id, status, stage",
    )
    .bind(organization)
    .bind(team)
    .fetch_all(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(Snapshot {
        scopes,
        teams,
        counts,
        processing,
    })
}
