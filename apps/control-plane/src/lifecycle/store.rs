// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::policy::{Catalog, LifecycleConfig};
use crate::{
    bootstrap, db,
    domain::{Space, SpaceKind},
    error::{AppError, AppResult},
    fga::{Fga, Scope},
    roles::PlatformPermission,
    spaces,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use uuid::Uuid;

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum Status {
    Queued,
    Running,
    Retrying,
    Blocked,
    Completed,
}

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum TargetKind {
    Organization,
    Team,
    Project,
    Document,
}
impl TryFrom<SpaceKind> for TargetKind {
    type Error = AppError;

    fn try_from(kind: SpaceKind) -> AppResult<Self> {
        match kind {
            SpaceKind::Organization => Ok(Self::Organization),
            SpaceKind::Team => Ok(Self::Team),
            SpaceKind::Project => Ok(Self::Project),
            SpaceKind::Personal => Err(AppError::Conflict(
                "standalone personal-space deletion is not supported".into(),
            )),
        }
    }
}

#[derive(Debug, Clone, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct Receipt {
    pub id: Uuid,
    pub target_id: Uuid,
    pub target_kind: TargetKind,
    pub target_parent_id: Option<Uuid>,
    pub organization_id: Uuid,
    pub actor_subject: String,
    pub requested_at: DateTime<Utc>,
    pub due_at: DateTime<Utc>,
    pub rule_id: Option<String>,
    pub status: Status,
    pub completed_at: Option<DateTime<Utc>>,
    pub error_code: Option<String>,
    pub documents_deleted: i64,
    pub folders_deleted: i64,
    pub spaces_deleted: i64,
}
#[derive(Clone, Default)]
pub struct Lifecycle {
    pub config: LifecycleConfig,
    pub catalog: Catalog,
}

async fn permitted(fga: &Fga, actor: &str) -> AppResult<()> {
    if fga
        .check_platform(actor, PlatformPermission::DeleteSpace)
        .await?
    {
        Ok(())
    } else {
        Err(AppError::Forbidden)
    }
}
pub async fn status(pool: &PgPool, fga: &Fga, actor: &str, id: Uuid) -> AppResult<Receipt> {
    permitted(fga, actor).await?;
    Ok(sqlx::query_as("select * from deletion where id = $1")
        .bind(id)
        .fetch_one(pool)
        .await?)
}

/// Use after mutation locks, and before any permission decision for reads.
/// Error code of a retired space, which authorization probes answer as not allowed.
pub const PENDING_DELETION: &str = "space_pending_deletion";

pub async fn require_active<'e>(ex: impl sqlx::PgExecutor<'e>, id: Uuid) -> AppResult<()> {
    let deletion: Option<Uuid> = sqlx::query_scalar("select deletion_id from space where id = $1")
        .bind(id)
        .fetch_one(ex)
        .await?;
    if deletion.is_some() {
        return Err(AppError::problem(
            axum::http::StatusCode::CONFLICT,
            PENDING_DELETION,
            "space is pending deletion",
        ));
    }
    Ok(())
}
/// Root placement survives loss of its FGA link until the SQL manifest is drained.
pub(crate) async fn reserved<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    parent: Uuid,
    name: &str,
) -> AppResult<bool> {
    Ok(sqlx::query_scalar("select exists(select 1 from deletion d join space s on s.id = d.target_id where d.status <> 'completed' and d.target_parent_id = $1 and s.name = $2)")
        .bind(parent).bind(name).fetch_one(ex).await?)
}
impl Lifecycle {
    pub async fn accept_document(
        &self,
        pool: &PgPool,
        fga: &Fga,
        actor: &str,
        document_id: Uuid,
    ) -> AppResult<Receipt> {
        if let Some(receipt) = sqlx::query_as::<_, Receipt>(
            "select * from deletion where target_id = $1 and target_kind = 'document'",
        )
        .bind(document_id)
        .fetch_optional(pool)
        .await?
        {
            let space_id = receipt
                .target_parent_id
                .ok_or_else(|| anyhow::anyhow!("document deletion has no parent"))?;
            let tx = spaces::authorized_write(pool, fga, actor, space_id).await?;
            tx.commit().await?;
            return Ok(receipt);
        }
        if !self.config.enabled {
            return Err(AppError::Unavailable(
                "document deletion is disabled by configuration".into(),
            ));
        }
        let space_id: Uuid = sqlx::query_scalar(
            "select space_id from document where id = $1 and deletion_id is null",
        )
        .bind(document_id)
        .fetch_one(pool)
        .await?;
        let mut tx = spaces::authorized_write(pool, fga, actor, space_id).await?;
        let document: Option<Uuid> = sqlx::query_scalar(
            "select id from document where id = $1 and deletion_id is null for update",
        )
        .bind(document_id)
        .fetch_optional(&mut *tx)
        .await?;
        // A concurrent acceptance may have retired the row while we waited for the lock.
        if let Some(receipt) = sqlx::query_as(
            "select * from deletion where target_id = $1 and target_kind = 'document'",
        )
        .bind(document_id)
        .fetch_optional(&mut *tx)
        .await?
        {
            tx.commit().await?;
            return Ok(receipt);
        }
        document.ok_or(AppError::NotFound)?;
        let active: bool = sqlx::query_scalar(
            "select exists(select 1 from document_processing where document_id = $1 and status in ('pending', 'running'))",
        )
        .bind(document_id)
        .fetch_one(&mut *tx)
        .await?;
        if active {
            return Err(AppError::problem(
                axum::http::StatusCode::CONFLICT,
                "processing_active",
                "document processing is active",
            ));
        }
        let space = Space::from(db::space(&mut *tx, space_id).await?);
        let (action, rule) = self.catalog.resolve(space_id, space.kind);
        let requested_at = Utc::now();
        let due_at = action.retention.after(requested_at)?;
        let operation = Uuid::new_v4();
        let receipt = sqlx::query_as("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id) values ($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *")
            .bind(operation).bind(document_id).bind(TargetKind::Document).bind(space_id).bind(space.organization).bind(actor).bind(requested_at).bind(due_at).bind(rule).fetch_one(&mut *tx).await?;
        sqlx::query("update document set deletion_id = $2 where id = $1")
            .bind(document_id)
            .bind(operation)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        tracing::info!(target: "fred.security.audit", audit_event="deletion.accepted", target_kind="document", operation_id=%operation, document_id=%document_id, space_id=%space_id, actor_uid=actor, "Document deletion accepted");
        Ok(receipt)
    }

    pub async fn accept(
        &self,
        pool: &PgPool,
        fga: &Fga,
        actor: &str,
        id: Uuid,
    ) -> AppResult<Receipt> {
        // Repeat requests never require a target row or a running scheduler.
        if let Some(receipt) = sqlx::query_as("select * from deletion where target_id = $1")
            .bind(id)
            .fetch_optional(pool)
            .await?
        {
            permitted(fga, actor).await?;
            return Ok(receipt);
        }
        if !self.config.enabled {
            permitted(fga, actor).await?;
            return Err(AppError::Unavailable("space deletion is disabled".into()));
        }
        let mut tx = bootstrap::locked(pool).await?;
        let mut platform_guard = fga.guard(&[Scope::Platform]).await?;
        permitted(fga, actor).await?;
        if let Some(receipt) = sqlx::query_as("select * from deletion where target_id = $1")
            .bind(id)
            .fetch_optional(&mut *tx)
            .await?
        {
            return Ok(receipt);
        }
        require_active(&mut *tx, id).await?;
        let root = Space::from(db::space(&mut *tx, id).await?);
        spaces::lock_organization(&mut tx, &root).await?;
        require_active(&mut *tx, id).await?;
        let target_kind = TargetKind::try_from(root.kind)?;
        let org_guard = fga.guard(&[Scope::Organization(root.organization)]).await?;
        platform_guard.extend(org_guard)?;
        let overlaps: bool = sqlx::query_scalar("select exists(select 1 from deletion where status <> 'completed' and organization_id = $1 and ($2 = 'organization' or target_id = $3 or target_parent_id = $3))")
            .bind(root.organization).bind(match root.kind { SpaceKind::Organization => "organization", _ => "child" }).bind(id).fetch_one(&mut *tx).await?;
        if overlaps {
            return Err(AppError::Conflict("overlapping space deletion".into()));
        }
        let (action, rule) = self.catalog.resolve(id, root.kind);
        let requested_at = Utc::now();
        let due_at = action.retention.after(requested_at)?;
        let operation = Uuid::new_v4();
        sqlx::query("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)")
            .bind(operation).bind(id).bind(target_kind).bind(root.parent_id).bind(root.organization).bind(actor).bind(requested_at).bind(due_at).bind(rule).execute(&mut *tx).await?;
        mark(&mut tx, id, operation).await?;
        if root.kind != SpaceKind::Project {
            discover(&mut tx, fga, &root, operation).await?;
        }
        fga.fence(&mut platform_guard).await?;
        let receipt = sqlx::query_as("select * from deletion where id = $1")
            .bind(operation)
            .fetch_one(&mut *tx)
            .await?;
        tx.commit().await?;
        let target_kind = serde_json::json!(root.kind);
        tracing::info!(target: "fred.security.audit", audit_event="deletion.accepted", target_kind=target_kind.as_str(), actor_uid=actor, operation_id=%operation, space_id=%id, organization_id=%root.organization, "Space deletion accepted");
        Ok(receipt)
    }
}
async fn mark(tx: &mut Transaction<'_, Postgres>, id: Uuid, operation: Uuid) -> AppResult<()> {
    require_active(&mut **tx, id).await?;
    let has_documents: bool =
        sqlx::query_scalar("select exists(select 1 from document where space_id = $1) or exists(select 1 from document_upload where space_id = $1 and status = 'pending')")
            .bind(id)
            .fetch_one(&mut **tx)
            .await?;
    if has_documents {
        return Err(AppError::Conflict(
            "document-bearing scopes cannot be deleted".into(),
        ));
    }
    sqlx::query("update space set deletion_id = $1 where id = $2")
        .bind(operation)
        .bind(id)
        .execute(&mut **tx)
        .await?;
    Ok(())
}
async fn mark_children(
    tx: &mut Transaction<'_, Postgres>,
    fga: &Fga,
    parent: Uuid,
    personal: bool,
    operation: Uuid,
) -> AppResult<()> {
    let mut token = String::new();
    loop {
        let (ids, next) = fga.linked_page(parent, personal, &token).await?;
        for child in db::spaces(&mut **tx, &ids).await? {
            mark(tx, child.id, operation).await?;
        }
        if next.is_empty() {
            break;
        }
        if next == token {
            return Err(anyhow::anyhow!("repeated hierarchy page").into());
        }
        token = next;
    }
    Ok(())
}
async fn discover(
    tx: &mut Transaction<'_, Postgres>,
    fga: &Fga,
    root: &Space,
    operation: Uuid,
) -> AppResult<()> {
    mark_children(tx, fga, root.id, false, operation).await?;
    if root.kind == SpaceKind::Organization {
        mark_children(tx, fga, root.id, true, operation).await?;
        let mut cursor = Uuid::nil();
        loop {
            let teams: Vec<Uuid> = sqlx::query_scalar("select id from space where deletion_id = $1 and kind = 'team' and id > $2 order by id limit 96")
                .bind(operation).bind(cursor).fetch_all(&mut **tx).await?;
            if teams.is_empty() {
                break;
            }
            for team in teams {
                mark_children(tx, fga, team, false, operation).await?;
                cursor = team;
            }
        }
    }
    Ok(())
}
