// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! One bounded batch under SQL locks and FGA revisions; metadata is removed last.
use super::{Receipt, Status, TargetKind};
use crate::{
    bootstrap,
    domain::{Space, SpaceKind, SpaceRow},
    error::AppResult,
    fga::{Fga, Scope},
    spaces,
};
use chrono::Utc;
use sqlx::{PgPool, Postgres, Transaction};
use uuid::Uuid;

pub async fn candidates(pool: &PgPool, limit: u32) -> AppResult<Vec<Uuid>> {
    Ok(sqlx::query_scalar("with selected as (select id from deletion where status <> 'completed' and due_at <= now() order by last_visit nulls first, due_at, id limit $1 for update skip locked) update deletion d set last_visit = now() from selected where d.id = selected.id returning d.id")
        .bind(i64::from(limit)).fetch_all(pool).await?)
}
/// Recording failure is separate because a failed batch must roll back its SQL progress.
pub async fn retrying(pool: &PgPool, id: Uuid) -> AppResult<()> {
    sqlx::query("update deletion set status = 'retrying', error_code = 'dependency_unavailable', last_visit = now() where id = $1 and status <> 'completed'")
        .bind(id).execute(pool).await?;
    Ok(())
}
pub async fn batch(pool: &PgPool, fga: &Fga, id: Uuid) -> AppResult<()> {
    let mut tx = pool.begin().await?;
    // Server-side bounds also release a statement if its Rust future is cancelled.
    sqlx::query("set local lock_timeout = '5s'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '45s'")
        .execute(&mut *tx)
        .await?;
    sqlx::query("select pg_advisory_xact_lock($1)")
        .bind(bootstrap::LOCK_KEY)
        .execute(&mut *tx)
        .await?;
    let receipt: Receipt = sqlx::query_as("select * from deletion where id = $1")
        .bind(id)
        .fetch_one(&mut *tx)
        .await?;
    let target_kind = serde_json::json!(receipt.target_kind);
    tracing::Span::current().record("target_kind", target_kind.as_str());
    if receipt.status == Status::Completed || receipt.due_at > Utc::now() {
        return Ok(());
    }
    let organization = Space::from(SpaceRow {
        id: receipt.organization_id,
        kind: SpaceKind::Organization,
        name: String::new(),
        personal_owner: None,
        parent_id: None,
        organization_id: receipt.organization_id,
    });
    spaces::lock_organization(&mut tx, &organization).await?;
    let mut guard = fga.guard(&[Scope::Platform]).await?;
    sqlx::query("update deletion set status = 'running', last_visit = now(), error_code = null where id = $1").bind(id).execute(&mut *tx).await?;
    let guard_present = fga
        .organization_guard_present(receipt.organization_id)
        .await?;
    if guard_present {
        guard.extend(
            fga.guard(&[Scope::Organization(receipt.organization_id)])
                .await?,
        )?;
    }
    let docs: bool = sqlx::query_scalar("select exists(select 1 from document where deletion_id is distinct from $1 and space_id in (select id from space where deletion_id = $1)) or exists(select 1 from document_upload where status = 'pending' and space_id in (select id from space where deletion_id = $1))").bind(id).fetch_one(&mut *tx).await?;
    if docs {
        sqlx::query("update deletion set status = 'blocked', error_code = 'unsupported_documents' where id = $1")
            .bind(id).execute(&mut *tx).await?;
        tx.commit().await?;
        return Ok(());
    }
    let remaining: i64 = sqlx::query_scalar("select count(*) from document where deletion_id = $1")
        .bind(id)
        .fetch_one(&mut *tx)
        .await?;
    if remaining > 0 {
        if !guard_present {
            sqlx::query("update deletion set status = 'blocked', error_code = 'missing_organization_guard' where id = $1")
                .bind(id).execute(&mut *tx).await?;
            tx.commit().await?;
            return Ok(());
        }
        let ready: Vec<Uuid> = sqlx::query_scalar(
            "select d.id from document d
             where d.deletion_id = $1
               and not exists (
                   select 1 from document_processing p
                   where p.document_id = d.id
                     and (p.status in ('pending', 'running') or exists (
                         select 1 from jsonb_array_elements(p.generations) g
                         where (g->>'cleaned')::boolean is distinct from true
                     ))
               )
             order by d.id limit 100 for update of d skip locked",
        )
        .bind(id)
        .fetch_all(&mut *tx)
        .await?;
        if ready.is_empty() {
            tracing::info!(remaining, "waiting for derived cleanup");
        } else {
            // Delete all attempts together so retry_of references disappear in the same statement.
            sqlx::query("delete from document_processing where document_id = any($1)")
                .bind(&ready)
                .execute(&mut *tx)
                .await?;
            sqlx::query(
                "delete from document_upload where document_id = any($1) and status = 'stored'",
            )
            .bind(&ready)
            .execute(&mut *tx)
            .await?;
            let deleted =
                sqlx::query("delete from document where id = any($1) and deletion_id = $2")
                    .bind(&ready)
                    .bind(id)
                    .execute(&mut *tx)
                    .await?
                    .rows_affected();
            fga.fence(&mut guard).await?;
            sqlx::query(
                "update deletion set documents_deleted = documents_deleted + $2 where id = $1",
            )
            .bind(id)
            .bind(deleted as i64)
            .execute(&mut *tx)
            .await?;
            tracing::info!(documents_deleted = deleted, "Documents purged");
        }
        if receipt.target_kind != TargetKind::Document {
            tx.commit().await?;
            return Ok(());
        }
    }
    if receipt.target_kind == TargetKind::Document {
        let remaining: bool =
            sqlx::query_scalar("select exists(select 1 from document where deletion_id = $1)")
                .bind(id)
                .fetch_one(&mut *tx)
                .await?;
        if !remaining {
            sqlx::query("update deletion set status = 'completed', completed_at = now(), error_code = null where id = $1")
                .bind(id).execute(&mut *tx).await?;
        }
        tx.commit().await?;
        if !remaining {
            tracing::info!(target: "fred.security.audit", audit_event="deletion.completed", target_kind="document", operation_id=%id, document_id=%receipt.target_id, space_id=?receipt.target_parent_id, actor_uid=receipt.actor_subject, "Document deletion completed");
        }
        return Ok(());
    }
    let row: Option<(Uuid, SpaceKind, bool)> = sqlx::query_as(
        "select id, kind, kind = 'personal' from space where deletion_id = $1 order by kind desc, id limit 1",
    )
    .bind(id)
    .fetch_optional(&mut *tx)
    .await?;
    let Some((space, kind, personal)) = row else {
        return Err(anyhow::anyhow!("incomplete deletion lost its manifest").into());
    };
    let refs = fga.references(space).await?;
    let manifest_count: i64 =
        sqlx::query_scalar("select count(*) from space where deletion_id = $1")
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
    if !guard_present
        && !(kind == SpaceKind::Organization && manifest_count == 1 && refs.keys.is_empty())
    {
        sqlx::query("update deletion set status = 'blocked', error_code = 'missing_organization_guard' where id = $1")
            .bind(id).execute(&mut *tx).await?;
        tx.commit().await?;
        return Ok(());
    }
    if !refs.incoming.is_empty() {
        match orphan_batch(&mut tx, fga, id, space, kind, personal, refs).await? {
            OrphanBatch::Delete(keys) => fga.delete_references(&mut guard, keys).await?,
            OrphanBatch::Blocked(code) => {
                sqlx::query(
                    "update deletion set status = 'blocked', error_code = $2 where id = $1",
                )
                .bind(id)
                .bind(code)
                .execute(&mut *tx)
                .await?;
            }
        }
        tx.commit().await?;
        return Ok(());
    }
    let mut completed = false;
    let deleted = sqlx::query("delete from folder where id in (select f.id from folder f where f.space_id = $1 and not exists(select 1 from folder child where child.parent_id = f.id) order by f.id limit 1000)").bind(space).execute(&mut *tx).await?.rows_affected();
    if deleted > 0 {
        // Even SQL-only effects fence late producers before their transaction commits.
        fga.fence(&mut guard).await?;
        sqlx::query("update deletion set folders_deleted = folders_deleted + $2 where id = $1")
            .bind(id)
            .bind(deleted as i64)
            .execute(&mut *tx)
            .await?;
    } else if !refs.keys.is_empty() {
        fga.delete_references(&mut guard, refs.keys).await?;
    } else {
        let folders: bool =
            sqlx::query_scalar("select exists(select 1 from folder where space_id = $1)")
                .bind(space)
                .fetch_one(&mut *tx)
                .await?;
        if folders {
            return Err(anyhow::anyhow!("folder tree has no leaf").into());
        }
        if kind == SpaceKind::Organization {
            if manifest_count != 1 {
                return Err(anyhow::anyhow!("organization is not last").into());
            }
            // A previous attempt may have deleted this guard but lost its SQL commit.
            let mut platform = fga.guard(&[Scope::Platform]).await?;
            if guard_present {
                fga.finish_organization_guard(&mut platform, space).await?;
            } else {
                fga.fence(&mut platform).await?;
            }
        } else {
            fga.fence(&mut guard).await?;
        }
        sqlx::query("delete from agent_instance where space_id = $1")
            .bind(space)
            .execute(&mut *tx)
            .await?;
        sqlx::query("delete from space where id = $1 and deletion_id = $2")
            .bind(space)
            .bind(id)
            .execute(&mut *tx)
            .await?;
        sqlx::query("update deletion set spaces_deleted = spaces_deleted + 1 where id = $1")
            .bind(id)
            .execute(&mut *tx)
            .await?;
        if manifest_count == 1 {
            completed = true;
            sqlx::query("update deletion set status = 'completed', completed_at = now(), error_code = null where id = $1").bind(id).execute(&mut *tx).await?;
        }
    }
    tx.commit().await?;
    if completed {
        tracing::info!(target:"fred.security.audit", audit_event="deletion.completed", operation_id=%id, space_id=%receipt.target_id, actor_uid=receipt.actor_subject, "Space deletion completed");
    }
    Ok(())
}

enum OrphanBatch {
    Delete(Vec<serde_json::Value>),
    Blocked(&'static str),
}

/// Keep each parent link until its SQL-absent subtree is empty, so retries can
/// rediscover work after either store loses an acknowledgment. No global scan.
async fn orphan_batch(
    tx: &mut Transaction<'_, Postgres>,
    fga: &Fga,
    operation: Uuid,
    mut parent: Uuid,
    mut kind: SpaceKind,
    mut personal: bool,
    mut refs: crate::fga::References,
) -> AppResult<OrphanBatch> {
    loop {
        let ids: Vec<_> = refs.incoming.iter().map(|(id, _)| *id).collect();
        let committed: Vec<Option<Uuid>> =
            sqlx::query_scalar("select deletion_id from space where id = any($1)")
                .bind(&ids)
                .fetch_all(&mut **tx)
                .await?;
        if !committed.is_empty() {
            return Ok(OrphanBatch::Blocked(
                if committed.iter().any(|id| *id != Some(operation)) {
                    "unexpected_reference"
                } else {
                    "unexpected_hierarchy"
                },
            ));
        }
        // The supported hierarchy bounds this loop to team then project. Personal
        // spaces and projects cannot have children; cycles fail closed here too.
        if personal
            || matches!(kind, SpaceKind::Project | SpaceKind::Personal)
            || (kind == SpaceKind::Team && refs.incoming.iter().any(|(_, personal)| *personal))
        {
            return Ok(OrphanBatch::Blocked("unexpected_hierarchy"));
        }
        let (child, is_personal) = refs.incoming[0];
        if !fga.orphan_link_matches(child, parent, is_personal).await? {
            return Ok(OrphanBatch::Blocked("unexpected_hierarchy"));
        }
        refs = fga.references(child).await?;
        if refs.incoming.is_empty() {
            let anchor = serde_json::json!({"object":format!("space:{child}"),
                "relation":if is_personal {"organization"} else {"parent"},
                "user":format!("space:{parent}")});
            let keys: Vec<_> = refs.keys.into_iter().filter(|key| *key != anchor).collect();
            // Removing the anchor last preserves reachability through arbitrarily
            // many grant pages, including after a committed write times out.
            return Ok(OrphanBatch::Delete(if keys.is_empty() {
                vec![anchor]
            } else {
                keys
            }));
        }
        kind = match kind {
            SpaceKind::Organization => SpaceKind::Team,
            _ => SpaceKind::Project,
        };
        parent = child;
        personal = is_personal;
    }
}
