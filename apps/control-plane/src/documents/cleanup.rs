// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::Storage;
use anyhow::{Result, ensure};
use uuid::Uuid;

impl Storage {
    /// Keep each manifest until its original is absent. Retirement prevents new
    /// reservations; an admitted PUT must acknowledge before any DELETE is sent.
    pub async fn purge_retired_originals(&self, deletion: Uuid) -> Result<()> {
        let ready: bool = sqlx::query_scalar("select exists(select 1 from deletion where id=$1 and status<>'completed' and due_at<=clock_timestamp())")
            .bind(deletion).fetch_one(&self.pool).await?;
        if !ready {
            return Ok(());
        }
        // Revoke publication of admitted uploads, without pretending their PUT ended.
        sqlx::query("update document_upload u set status='failed',error_code='destination_deleted',completed_at=clock_timestamp() where status='pending' and (exists(select 1 from session_metadata s where s.session_id=u.session_id and s.deletion_id=$1) or exists(select 1 from space s where s.id=u.space_id and s.deletion_id=$1))")
            .bind(deletion).execute(&self.pool).await?;
        self.cleanup_contents(Some(deletion), None).await?;
        sqlx::query("update document d set original_cleaned_at=clock_timestamp() where d.deletion_id=$1 and d.original_cleaned_at is null and not exists(select 1 from document_content c where c.document_id=d.id and c.cleaned_at is null) and not exists(select 1 from document_upload u where u.target_document_id=d.id and u.put_pending)")
            .bind(deletion).execute(&self.pool).await?;
        let uploads: Vec<(Uuid, String)> = sqlx::query_as("select u.id,u.object_key from document_upload u where u.status='failed' and not u.put_pending and u.cleaned_at is null and (exists(select 1 from session_metadata s where s.session_id=u.session_id and s.deletion_id=$1) or exists(select 1 from space s where s.id=u.space_id and s.deletion_id=$1)) order by u.id limit $2")
            .bind(deletion).bind(i64::from(self.config.limits.cleanup_batch)).fetch_all(&self.pool).await?;
        for (upload, key) in uploads {
            self.objects.delete(&key).await?;
            ensure!(
                self.objects.absent(&key).await?,
                "upload cleanup incomplete"
            );
            sqlx::query("update document_upload set cleaned_at=clock_timestamp() where id=$1 and not put_pending")
                .bind(upload).execute(&self.pool).await?;
        }
        Ok(())
    }

    /// Immutable superseded content can never become current again through the write API.
    async fn cleanup_contents(&self, deletion: Option<Uuid>, lease: Option<Uuid>) -> Result<()> {
        let due: Vec<(Uuid,String)> = sqlx::query_as("select c.id,c.object_key from document_content c join document d on d.id=c.document_id where c.cleaned_at is null and c.cleanup_after<=clock_timestamp() and (($1::uuid is not null and d.deletion_id=$1) or ($1::uuid is null and d.deletion_id is null and c.id is distinct from d.current_content_id and c.source_content_id is distinct from d.current_content_id)) and not exists(select 1 from document_upload u where u.content_id=c.id and u.put_pending) order by c.cleanup_after,c.id limit $2")
            .bind(deletion).bind(i64::from(self.config.limits.cleanup_batch)).fetch_all(&self.pool).await?;
        for (id, key) in due {
            if let Some(owner) = lease {
                self.renew(owner).await?;
            }
            let removed = match self.objects.delete(&key).await {
                Ok(()) => self.objects.absent(&key).await.unwrap_or(false),
                Err(_) => false,
            };
            sqlx::query("update document_content set cleaned_at=case when $2 then clock_timestamp() end,cleanup_after=clock_timestamp()+interval '30 seconds' where id=$1 and cleaned_at is null")
                .bind(id).bind(removed).execute(&self.pool).await?;
        }
        Ok(())
    }

    /// One replica advances a bounded page. Deletes remain safe after lease loss:
    /// only terminal attempts or unreferenced immutable keys are eligible.
    pub async fn cleanup_tick(&self) -> Result<()> {
        if !self.config.cleanup_enabled {
            return Ok(());
        }
        let owner = Uuid::new_v4();
        let claimed = sqlx::query("update document_storage set lease_owner=$1,lease_until=clock_timestamp()+make_interval(secs=>$2) where singleton and (lease_until is null or lease_until<clock_timestamp())")
            .bind(owner).bind((self.config.limits.s3_seconds+30) as f64).execute(&self.pool).await?.rows_affected();
        if claimed == 0 {
            return Ok(());
        }
        let result = self.cleanup_page(owner).await;
        sqlx::query("update document_storage set lease_owner=null,lease_until=null where singleton and lease_owner=$1")
            .bind(owner).execute(&self.pool).await?;
        result
    }

    async fn renew(&self, owner: Uuid) -> Result<()> {
        let updated=sqlx::query("update document_storage set lease_until=clock_timestamp()+make_interval(secs=>$2) where singleton and lease_owner=$1 and lease_until>clock_timestamp()")
            .bind(owner).bind((self.config.limits.s3_seconds+30) as f64).execute(&self.pool).await?.rows_affected();
        ensure!(updated == 1, "document cleanup lease lost");
        Ok(())
    }

    async fn cleanup_page(&self, owner: Uuid) -> Result<()> {
        self.cleanup_contents(None, Some(owner)).await?;
        let batch = i64::from(self.config.limits.cleanup_batch);
        let expired: Vec<(Uuid,Uuid)> = sqlx::query_as("select id,organization_id from document_upload where status='pending' and expires_at<=clock_timestamp() and cleanup_due_at<=clock_timestamp() order by cleanup_due_at,expires_at,id limit $1")
            .bind(batch).fetch_all(&self.pool).await?;
        for (id, org) in expired {
            self.renew(owner).await?;
            self.expire_or_defer(id, org).await?;
        }
        // Publication and expiry arbitrate on the same row; retirement is terminal.
        sqlx::query("update powerpoint_file set status='retired',error_code='upload_expired' where id in (select id from powerpoint_file where status='pending' and expires_at<=clock_timestamp() order by cleanup_due_at,id limit $1 for update skip locked)")
            .bind(batch).execute(&self.pool).await?;
        let files: Vec<(Uuid, String)> = sqlx::query_as("select id,object_key from powerpoint_file where status='retired' and cleaned_at is null and cleanup_due_at<=clock_timestamp() order by cleanup_due_at,id limit $1")
            .bind(batch).fetch_all(&self.pool).await?;
        for (id, key) in files {
            self.renew(owner).await?;
            ensure!(
                self.original_id(&key) == Some(id),
                "cleanup key outside content namespace"
            );
            let deleted = match self.objects.owns_original(&key).await {
                Ok(false) => true,
                Ok(true) => self.objects.delete(&key).await.is_ok(),
                Err(_) => false,
            };
            sqlx::query("update powerpoint_file set cleaned_at=case when $2 then clock_timestamp() else null end,error_code=case when $2 then null else 'cleanup_failed' end,cleanup_attempts=cleanup_attempts+1,cleanup_due_at=clock_timestamp()+make_interval(secs=>least(3600,30*power(2,least(cleanup_attempts,7)))) where id=$1 and status='retired'")
                .bind(id).bind(deleted).execute(&self.pool).await?;
        }
        let failed: Vec<(Uuid,String)> = sqlx::query_as("select id,object_key from document_upload where status='failed' and not put_pending and cleaned_at is null and cleanup_due_at<=clock_timestamp() order by cleanup_due_at,id limit $1")
            .bind(batch).fetch_all(&self.pool).await?;
        for (id, key) in failed {
            self.renew(owner).await?;
            ensure!(
                self.original_id(&key) == Some(id),
                "cleanup key outside content namespace"
            );
            let deleted = match self.objects.owns_original(&key).await {
                Ok(false) => true,
                Ok(true) => self.objects.delete(&key).await.is_ok(),
                Err(_) => false,
            };
            sqlx::query("update document_upload set cleaned_at=case when $2 then clock_timestamp() else null end,cleanup_attempts=cleanup_attempts+1,cleanup_due_at=clock_timestamp()+make_interval(secs=>least(3600,30*power(2,least(cleanup_attempts,7)))) where id=$1 and status='failed'")
                .bind(id).bind(deleted).execute(&self.pool).await?;
            tracing::info!(operation_id=%id,outcome=if deleted {"cleaned"}else{"retry"},"document cleanup");
        }
        // Receipts bound the technical retention window; there is no user revision archive.
        sqlx::query("delete from document_upload where id in (select u.id from document_upload u join document_content c on c.id=u.content_id where u.purpose<>'source' and u.status='stored' and c.cleaned_at is not null and c.published_at<clock_timestamp()-make_interval(days=>$1) order by c.published_at,c.id limit $2)")
            .bind(self.config.limits.receipt_retention_days as i32).bind(batch).execute(&self.pool).await?;
        sqlx::query("delete from document_content where id in (select c.id from document_content c join document d on d.id=c.document_id where c.cleaned_at is not null and c.id is distinct from d.current_content_id and not exists(select 1 from document_upload u where u.content_id=c.id) and not exists(select 1 from document_content p where p.source_content_id=c.id) order by c.cleanup_after,c.id limit $1)")
            .bind(batch).execute(&self.pool).await?;
        self.renew(owner).await?;
        let cursor: Option<String> = sqlx::query_scalar(
            "select inventory_cursor from document_storage where singleton and lease_owner=$1",
        )
        .bind(owner)
        .fetch_one(&self.pool)
        .await?;
        let page = self
            .objects
            .list(
                &self.prefix,
                cursor,
                self.config.limits.cleanup_batch as i32,
            )
            .await?;
        let mut retained_orphans = 0_i64;
        for (key, size, _) in page.objects {
            if self.original_id(&key).is_none() {
                continue;
            }
            self.renew(owner).await?;
            let pending: Option<(Uuid,Uuid)> = sqlx::query_as("select id,organization_id from document_upload where object_key=$1 and status='pending' and expires_at<=clock_timestamp() and cleanup_due_at<=clock_timestamp()")
                .bind(&key).fetch_optional(&self.pool).await?;
            if let Some((id, org)) = pending {
                self.expire_or_defer(id, org).await?;
            }
            let live: bool=sqlx::query_scalar("select exists(select 1 from document_content where object_key=$1 and cleaned_at is null) or exists(select 1 from document_upload where object_key=$1 and (status='pending' or put_pending)) or exists(select 1 from powerpoint_file where object_key=$1 and (status in ('pending','stored') or cleanup_due_at>clock_timestamp()))")
                .bind(&key).fetch_one(&self.pool).await?;
            // Unknown ownership never authorizes deletion. Count inaccessible
            // candidates conservatively and advance so one key cannot starve a sweep.
            let retained = if live {
                false
            } else {
                match self.objects.owns_original(&key).await {
                    Ok(false) => false,
                    Ok(true) => self.objects.delete(&key).await.is_err(),
                    Err(_) => true,
                }
            };
            if retained {
                retained_orphans = retained_orphans.saturating_add(size.max(0));
            }
        }
        self.renew(owner).await?;
        // A complete rescan is essential: a timed-out Put can finish after Delete.
        sqlx::query("update document_storage set inventory_cursor=$2,inventory_bytes=case when $2::text is null then 0 else inventory_bytes+$3 end,orphan_bytes=case when $2::text is null then inventory_bytes+$3 else greatest(orphan_bytes,inventory_bytes+$3) end,inventory_completed_at=case when $2::text is null then clock_timestamp() else inventory_completed_at end where singleton and lease_owner=$1")
            .bind(owner).bind(page.next).bind(retained_orphans).execute(&self.pool).await?;
        sqlx::query("delete from document_upload where id in (select id from document_upload where status='failed' and not put_pending and session_id is null and cleaned_at is not null and completed_at<clock_timestamp()-make_interval(days=>$1) order by completed_at,id limit $2)")
            .bind(self.config.limits.receipt_retention_days as i32).bind(batch).execute(&self.pool).await?;
        Ok(())
    }

    async fn expire_or_defer(&self, id: Uuid, organization: Uuid) -> Result<()> {
        if let Err(error) = self.expire(id, organization).await {
            let contention=error.chain().filter_map(|e|e.downcast_ref::<sqlx::Error>()).any(|e| {
                matches!(e,sqlx::Error::Database(db) if matches!(db.code().as_deref(),Some("55P03"|"57014")))
            });
            if !contention {
                return Err(error);
            }
            sqlx::query("update document_upload set cleanup_due_at=clock_timestamp()+interval '30 seconds' where id=$1 and status='pending'")
                .bind(id).execute(&self.pool).await?;
            tracing::warn!(operation_id=%id,outcome="deferred", "document expiration lock contention");
        }
        Ok(())
    }

    async fn expire(&self, id: Uuid, organization: Uuid) -> Result<()> {
        let mut tx = self.pool.begin().await?;
        sqlx::query("set local lock_timeout='5s'")
            .execute(&mut *tx)
            .await?;
        sqlx::query("set local statement_timeout='15s'")
            .execute(&mut *tx)
            .await?;
        crate::spaces::lock_organization_id(&mut tx, organization).await?;
        sqlx::query("update document_upload set status='failed',error_code='upload_expired',completed_at=clock_timestamp() where id=$1 and status='pending' and expires_at<=clock_timestamp() and cleanup_due_at<=clock_timestamp()")
            .bind(id).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(())
    }
}
