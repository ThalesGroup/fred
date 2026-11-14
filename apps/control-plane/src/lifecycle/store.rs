// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::policy::{Catalog, LifecycleConfig};
use crate::{
    authorization, bootstrap, db,
    domain::{Permission, Role, Space, SpaceKind},
    error::{AppError, AppResult},
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
    Folder,
    Session,
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

pub async fn status(pool: &PgPool, actor: &str, id: Uuid) -> AppResult<Receipt> {
    authorization::require_platform(pool, actor, PlatformPermission::DeleteSpace).await?;
    Ok(sqlx::query_as("select * from deletion where id = $1")
        .bind(id)
        .fetch_one(pool)
        .await?)
}

/// Read a project receipt belonging to the caller without initiating or replaying deletion.
pub async fn project_status(pool: &PgPool, actor: &str, target: Uuid) -> AppResult<Receipt> {
    authorization::require_platform(pool, actor, PlatformPermission::DeleteSpace).await?;
    Ok(sqlx::query_as("select * from deletion where target_id = $1 and target_kind = 'project' and actor_subject = $2")
        .bind(target)
        .bind(actor)
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
/// Root placement stays reserved until the SQL deletion manifest is drained.
pub(crate) async fn reserved<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    parent: Uuid,
    name: &str,
) -> AppResult<bool> {
    Ok(sqlx::query_scalar(concat!(
        "select exists(select 1 from deletion d join space s on s.id = d.target_id where ",
        space_target!(),
        " and d.status <> 'completed' and d.target_parent_id = $1 and s.name = $2)"
    ))
    .bind(parent)
    .bind(name)
    .fetch_one(ex)
    .await?)
}
impl Lifecycle {
    /// Retire an empty live subtree without taking ownership of document or
    /// child-folder deletions already in progress. Names are released at commit.
    pub async fn accept_folder(
        &self,
        pool: &PgPool,
        actor: &str,
        id: Uuid,
        empty_only: bool,
    ) -> AppResult<Receipt> {
        // Resolve by identity, including receipts after physical purge. The
        // parent in a folder receipt is its owning space, as for documents.
        let space_id: Uuid = sqlx::query_scalar(
            "select space_id from folder where id=$1
             union select target_parent_id from deletion where target_kind='folder' and target_id=$1",
        )
        .bind(id)
        .fetch_one(pool)
        .await?;
        let (mut tx, space) =
            spaces::governance_mutation(pool, actor, space_id, Permission::Write).await?;
        // Recheck after the exclusive organization lock: another request may
        // have retired this folder (or its ancestor) while we were waiting.
        if let Some(receipt) = sqlx::query_as::<_, Receipt>(
            "select * from deletion where (target_kind='folder' and target_id=$1)
             or id=(select deletion_id from folder where id=$1)",
        )
        .bind(id)
        .fetch_optional(&mut *tx)
        .await?
        {
            return Ok(receipt);
        }
        db::folder(&mut *tx, id).await?;
        if !self.config.enabled {
            return Err(AppError::Unavailable(
                "folder deletion is disabled by configuration".into(),
            ));
        }
        // All content writers use the shared organization guard. No upload,
        // move or child creation can enter this subtree until retirement commits.
        let (documents, uploads, children): (bool, bool, bool) = sqlx::query_as(
            "with recursive subtree as (
                select id,space_id from folder where id=$1
                union all select f.id,f.space_id from folder f join subtree p on f.parent_id=p.id
             ) select
                exists(select 1 from document d join subtree f on f.id=d.folder_id and f.space_id=d.space_id where d.deletion_id is null),
                exists(select 1 from document_upload u join subtree f on f.id=u.folder_id where u.status='pending'),
                exists(select 1 from folder where parent_id=$1 and deletion_id is null)",
        )
        .bind(id)
        .fetch_one(&mut *tx)
        .await?;
        if uploads {
            return Err(AppError::Conflict(
                "folder has pending document uploads".into(),
            ));
        }
        if documents || (empty_only && children) {
            return Err(AppError::Conflict("folder is not empty".into()));
        }
        let requested_at = Utc::now();
        let (due_at, rule) = self.deadline(&space, requested_at, false)?;
        let operation = Uuid::new_v4();
        let receipt = sqlx::query_as(
            "insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id)
             values ($1,$2,'folder',$3,$4,$5,$6,$7,$8) returning *",
        )
        .bind(operation).bind(id).bind(space_id).bind(space.organization).bind(actor)
        .bind(requested_at).bind(due_at).bind(rule).fetch_one(&mut *tx).await?;
        sqlx::query(
            "with recursive subtree as (
                select id from folder where id=$1 and deletion_id is null
                union all select f.id from folder f join subtree p on f.parent_id=p.id where f.deletion_id is null
             ) update folder set deletion_id=$2 where id in (select id from subtree)",
        )
        .bind(id).bind(operation).execute(&mut *tx).await?;
        tx.commit().await?;
        tracing::info!(target: "fred.security.audit", audit_event="deletion.accepted", target_kind="folder", operation_id=%operation, folder_id=%id, space_id=%space_id, actor_uid=actor, "Folder deletion accepted");
        Ok(receipt)
    }

    fn deadline(
        &self,
        space: &Space,
        requested_at: DateTime<Utc>,
        immediate: bool,
    ) -> AppResult<(DateTime<Utc>, Option<&str>)> {
        if immediate {
            return Ok((requested_at, None));
        }
        let (action, rule) = self.catalog.resolve(space.id, space.kind);
        Ok((action.retention.after(requested_at)?, rule))
    }

    /// `conversation` is `(space_id, session_id)` for an attachment, which only its
    /// conversation owner deletes; each route answers 404 for the other kind of document.
    pub async fn accept_document(
        &self,
        pool: &PgPool,
        actor: &str,
        document_id: Uuid,
        conversation: Option<(Uuid, Uuid)>,
        immediate: bool,
    ) -> AppResult<Receipt> {
        if immediate && conversation.is_some() {
            return Err(AppError::Forbidden);
        }
        let session = conversation.map(|(_, session)| session);
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
            // Until purge the route must match the placement; after it, only the deleter replays.
            let placed: Option<Option<Uuid>> =
                sqlx::query_scalar("select session_id from document where id = $1")
                    .bind(document_id)
                    .fetch_optional(pool)
                    .await?;
            let visible = match placed {
                Some(placed) => placed == session,
                None => receipt.actor_subject == actor,
            };
            if !visible || (immediate && receipt.actor_subject != actor) {
                return Err(AppError::NotFound);
            }
            if conversation.is_some_and(|(space, _)| space != space_id) {
                return Err(AppError::NotFound);
            }
            let (mut tx, _) = spaces::governance_mutation(
                pool,
                actor,
                space_id,
                if session.is_some() {
                    Permission::Read
                } else {
                    Permission::Write
                },
            )
            .await?;
            if immediate {
                authorization::require_platform(&mut *tx, actor, PlatformPermission::DeleteSpace)
                    .await?;
            }
            if let Some(session) = session {
                crate::sessions::owned(&mut *tx, space_id, actor, session).await?;
            }
            tx.commit().await?;
            return Ok(receipt);
        }
        if !self.config.enabled {
            return Err(AppError::Unavailable(
                "document deletion is disabled by configuration".into(),
            ));
        }
        let space_id: Uuid = sqlx::query_scalar(
            "select space_id from document where id = $1 and deletion_id is null and session_id is not distinct from $2",
        )
        .bind(document_id)
        .bind(session)
        .fetch_one(pool)
        .await?;
        if conversation.is_some_and(|(space, _)| space != space_id) {
            return Err(AppError::NotFound);
        }
        let (mut tx, space) = spaces::governance_mutation(
            pool,
            actor,
            space_id,
            if session.is_some() {
                Permission::Read
            } else {
                Permission::Write
            },
        )
        .await?;
        if immediate {
            authorization::require_platform(&mut *tx, actor, PlatformPermission::DeleteSpace)
                .await?;
        }
        if let Some(session) = session {
            crate::sessions::owned(&mut *tx, space_id, actor, session).await?;
        }
        let creator: Option<String> = sqlx::query_scalar(
            "select created_by from document where id = $1 and deletion_id is null for update",
        )
        .bind(document_id)
        .fetch_optional(&mut *tx)
        .await?;
        // A concurrent acceptance may have retired the row while we waited for the lock.
        if let Some(receipt) = sqlx::query_as::<_, Receipt>(
            "select * from deletion where target_id = $1 and target_kind = 'document'",
        )
        .bind(document_id)
        .fetch_optional(&mut *tx)
        .await?
        {
            if immediate && receipt.actor_subject != actor {
                return Err(AppError::NotFound);
            }
            tx.commit().await?;
            return Ok(receipt);
        }
        let creator = creator.ok_or(AppError::NotFound)?;
        if immediate && creator != actor {
            return Err(AppError::Forbidden);
        }
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
        let requested_at = Utc::now();
        let (due_at, rule) = self.deadline(&space, requested_at, immediate)?;
        let operation = Uuid::new_v4();
        let receipt = sqlx::query_as("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id) values ($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *")
            .bind(operation).bind(document_id).bind(TargetKind::Document).bind(space_id).bind(space.organization).bind(actor).bind(requested_at).bind(due_at).bind(rule).fetch_one(&mut *tx).await?;
        // The database adjusts used storage bytes and schedules obsolete content cleanup.
        sqlx::query(
            "update document set deletion_id = $2, purge_after = clock_timestamp() where id = $1",
        )
        .bind(document_id)
        .bind(operation)
        .execute(&mut *tx)
        .await?;
        tx.commit().await?;
        tracing::info!(target: "fred.security.audit", audit_event="deletion.accepted", target_kind="document", operation_id=%operation, document_id=%document_id, space_id=%space_id, actor_uid=actor, "Document deletion accepted");
        Ok(receipt)
    }

    /// Only the owner deletes a session; its row answers replays until purge.
    pub async fn accept_session(
        &self,
        pool: &PgPool,
        actor: &str,
        space_id: Uuid,
        session_id: Uuid,
        immediate: bool,
    ) -> AppResult<Receipt> {
        let (mut tx, space) =
            spaces::governance_mutation(pool, actor, space_id, Permission::Read).await?;
        if immediate {
            authorization::require_platform(&mut *tx, actor, PlatformPermission::DeleteSpace)
                .await?;
        }
        let retired: Option<(Option<Uuid>, String)> = sqlx::query_as(
            "select deletion_id, runtime_id from session_metadata where space_id = $1 and user_id = $2 and session_id = $3 for update",
        )
        .bind(space_id)
        .bind(actor)
        .bind(session_id)
        .fetch_optional(&mut *tx)
        .await?;
        let (deletion, runtime) = retired.ok_or(AppError::NotFound)?;
        if let Some(operation) = deletion {
            let receipt = sqlx::query_as("select * from deletion where id = $1")
                .bind(operation)
                .fetch_one(&mut *tx)
                .await?;
            tx.commit().await?;
            return Ok(receipt);
        }
        if !self.config.enabled {
            return Err(AppError::Unavailable(
                "session deletion is disabled by configuration".into(),
            ));
        }
        let requested_at = Utc::now();
        let (due_at, rule) = self.deadline(&space, requested_at, immediate)?;
        let operation = Uuid::new_v4();
        let receipt = sqlx::query_as("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id) values ($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *")
            .bind(operation).bind(session_id).bind(TargetKind::Session).bind(space_id).bind(space.organization).bind(actor).bind(requested_at).bind(due_at).bind(rule).fetch_one(&mut *tx).await?;
        sqlx::query("update session_metadata set deletion_id = $2 where session_id = $1")
            .bind(session_id)
            .bind(operation)
            .execute(&mut *tx)
            .await?;
        // Its attachments retire with it and free their quota; cleanup purges them as documents.
        // The database adjusts used storage bytes and schedules obsolete content cleanup.
        sqlx::query("update document set deletion_id = $3, purge_after = clock_timestamp() where session_id = $1 and space_id = $2 and deletion_id is null")
            .bind(session_id)
            .bind(space_id)
            .bind(operation)
            .execute(&mut *tx)
            .await?;

        tx.commit().await?;
        super::audit::session(&receipt, &runtime);
        Ok(receipt)
    }

    pub async fn accept(
        &self,
        pool: &PgPool,
        actor: &str,
        id: Uuid,
        immediate: bool,
    ) -> AppResult<Receipt> {
        // Repeat requests never require a target row or a running scheduler.
        const REPLAY: &str = concat!(
            "select * from deletion where target_id = $1 and ",
            space_target!()
        );
        if let Some(receipt) = sqlx::query_as::<_, Receipt>(REPLAY)
            .bind(id)
            .fetch_optional(pool)
            .await?
        {
            authorization::require_platform(pool, actor, PlatformPermission::DeleteSpace).await?;
            if immediate && receipt.actor_subject != actor {
                return Err(AppError::NotFound);
            }
            return Ok(receipt);
        }
        if !self.config.enabled {
            authorization::require_platform(pool, actor, PlatformPermission::DeleteSpace).await?;
            return Err(AppError::Unavailable("space deletion is disabled".into()));
        }
        let mut tx = bootstrap::locked(pool).await?;
        authorization::require_platform(&mut *tx, actor, PlatformPermission::ManagePlatform)
            .await?;
        if let Some(receipt) = sqlx::query_as::<_, Receipt>(REPLAY)
            .bind(id)
            .fetch_optional(&mut *tx)
            .await?
        {
            if immediate && receipt.actor_subject != actor {
                return Err(AppError::NotFound);
            }
            return Ok(receipt);
        }
        require_active(&mut *tx, id).await?;
        let root = Space::from(db::space(&mut *tx, id).await?);
        spaces::lock_organization(&mut tx, &root).await?;
        require_active(&mut *tx, id).await?;
        let target_kind = TargetKind::try_from(root.kind)?;
        if immediate {
            if !matches!(root.kind, SpaceKind::Team | SpaceKind::Project)
                || !authorization::direct_roles_on(&mut *tx, actor, id)
                    .await?
                    .contains(&Role::Owner)
            {
                return Err(AppError::Forbidden);
            }
            let descendants: bool = sqlx::query_scalar(
                "select exists(select 1 from space where parent_id=$1)
                    or exists(select 1 from session_metadata where space_id=$1)",
            )
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
            if descendants {
                return Err(AppError::Conflict(
                    "immediate deletion requires a space without children or sessions".into(),
                ));
            }
        }

        // Session and folder jobs drain their own manifests before the parent
        // space can disappear; accepting the space must not steal those jobs.
        let overlaps: bool = sqlx::query_scalar(concat!("select exists(select 1 from deletion where status <> 'completed' and target_kind not in ('session','folder') and organization_id = $1 and ($2 = 'organization' or (", space_target!(), " and target_id = $3) or target_parent_id = $3))"))
            .bind(root.organization).bind(match root.kind { SpaceKind::Organization => "organization", _ => "child" }).bind(id).fetch_one(&mut *tx).await?;
        if overlaps {
            return Err(AppError::Conflict("overlapping space deletion".into()));
        }
        let requested_at = Utc::now();
        let (due_at, rule) = self.deadline(&root, requested_at, immediate)?;
        let operation = Uuid::new_v4();
        sqlx::query("insert into deletion (id,target_id,target_kind,target_parent_id,organization_id,actor_subject,requested_at,due_at,rule_id) values ($1,$2,$3,$4,$5,$6,$7,$8,$9)")
            .bind(operation).bind(id).bind(target_kind).bind(root.parent_id).bind(root.organization).bind(actor).bind(requested_at).bind(due_at).bind(rule).execute(&mut *tx).await?;
        mark(&mut tx, id, operation).await?;
        if root.kind != SpaceKind::Project {
            discover(&mut tx, &root, operation).await?;
        }

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
        sqlx::query_scalar("select exists(select 1 from document where space_id = $1 and session_id is null) or exists(select 1 from document_upload where space_id = $1 and session_id is null and status = 'pending')")
            .bind(id)
            .fetch_one(&mut **tx)
            .await?;
    if has_documents {
        return Err(AppError::Conflict(
            "document-bearing scopes cannot be deleted".into(),
        ));
    }
    // Attachments retire with the space and release quota immediately. Existing
    // document/session receipts keep their own retention and cleanup ownership.
    // The database adjusts used storage bytes and schedules obsolete content cleanup.
    sqlx::query("update document set deletion_id = $1, purge_after = clock_timestamp() where space_id = $2 and session_id is not null and deletion_id is null")
        .bind(operation).bind(id).execute(&mut **tx).await?;
    sqlx::query("update space set deletion_id = $1 where id = $2")
        .bind(operation)
        .bind(id)
        .execute(&mut **tx)
        .await?;
    Ok(())
}
async fn mark_children(
    tx: &mut Transaction<'_, Postgres>,
    parent: Uuid,
    personal: bool,
    operation: Uuid,
) -> AppResult<()> {
    let ids: Vec<Uuid> = sqlx::query_scalar(if personal {
        "select id from space where organization_id=$1 and kind='personal'"
    } else {
        "select id from space where parent_id=$1"
    })
    .bind(parent)
    .fetch_all(&mut **tx)
    .await?;
    for id in ids {
        mark(tx, id, operation).await?;
    }

    Ok(())
}
async fn discover(
    tx: &mut Transaction<'_, Postgres>,
    root: &Space,
    operation: Uuid,
) -> AppResult<()> {
    mark_children(tx, root.id, false, operation).await?;
    if root.kind == SpaceKind::Organization {
        mark_children(tx, root.id, true, operation).await?;
        let mut cursor = Uuid::nil();
        loop {
            let teams: Vec<Uuid> = sqlx::query_scalar("select id from space where deletion_id = $1 and kind = 'team' and id > $2 order by id limit 96")
                .bind(operation).bind(cursor).fetch_all(&mut **tx).await?;
            if teams.is_empty() {
                break;
            }
            for team in teams {
                mark_children(tx, team, false, operation).await?;
                cursor = team;
            }
        }
    }
    Ok(())
}
