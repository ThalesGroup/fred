// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Immutable document copies share the upload journal, quota and content cleanup.
//! Their owning domain checks access and binds the published document in its transaction.
use super::{Storage, conflict, invalid, models::FileMetadata};
use crate::{domain::Space, error::AppResult};
use sqlx::{Postgres, Transaction};
use uuid::Uuid;

pub(crate) struct CopyContent {
    pub id: Uuid,
    pub object_key: String,
    pub file: FileMetadata,
}

impl Storage {
    /// Reserve before transfer. Preview callers reserve zero bytes explicitly.
    #[allow(clippy::too_many_arguments)]
    pub(crate) async fn reserve_copy(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        actor: &str,
        space: &Space,
        key: Uuid,
        purpose: &str,
        reserved_bytes: i64,
        fingerprint: Option<&str>,
        file: &FileMetadata,
    ) -> AppResult<Option<CopyContent>> {
        self.ensure_budgets(tx, space).await?;
        self.require_cleanup_capacity(&mut **tx).await?;
        let (owner, _) = self.quota(space)?;
        let id = Uuid::new_v4();
        let object_key = format!("{}{id}/input/{}", self.prefix, file.name);
        if object_key.len() > 1024 {
            return Err(invalid(
                "The encoded file name exceeds the object-store key limit.",
            ));
        }
        let inserted = sqlx::query("insert into document_upload(id,request_key,actor,organization_id,space_id,quota_owner,name,mime,size,sha256,object_key,status,expires_at,put_pending,purpose,reserved_bytes,request_fingerprint) values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,'pending',clock_timestamp()+make_interval(secs=>$12),true,$13,$14,$15) on conflict (actor,request_key) do nothing")
            .bind(id).bind(key).bind(actor).bind(space.organization).bind(space.id).bind(owner)
            .bind(&file.name).bind(&file.mime).bind(file.size).bind(&file.sha256).bind(&object_key)
            .bind(self.config.limits.lease_seconds() as f64).bind(purpose).bind(reserved_bytes).bind(fingerprint)
            .execute(&mut **tx).await?.rows_affected();
        Ok((inserted != 0).then(|| CopyContent {
            id,
            object_key,
            file: file.clone(),
        }))
    }

    /// Accept one verified primary copy and its optional previews atomically with its owner.
    pub(crate) async fn publish_copy(
        &self,
        tx: &mut Transaction<'_, Postgres>,
        actor: &str,
        space: &Space,
        purpose: &str,
        copies: &[&CopyContent],
    ) -> AppResult<Uuid> {
        let primary = copies.first().ok_or_else(super::unavailable)?;
        let id = primary.id;
        let ids: Vec<_> = copies.iter().map(|copy| copy.id).collect();
        let stored = sqlx::query("update document_upload set status='stored',completed_at=clock_timestamp() where id=any($1) and status='pending' and not put_pending and expires_at>clock_timestamp()")
            .bind(&ids).execute(&mut **tx).await?.rows_affected();
        if stored != ids.len() as u64 {
            return Err(conflict(
                "upload_expired",
                "This copy can no longer be published",
            ));
        }
        let (owner, _) = self.quota(space)?;
        sqlx::query("insert into document(id,space_id,name,created_by,quota_owner,purpose) values($1,$2,$3,$4,$5,$6)")
            .bind(id).bind(space.id).bind(&primary.file.name).bind(actor).bind(owner).bind(purpose)
            .execute(&mut **tx).await?;
        for copy in copies {
            let preview = (copy.id != id).then_some(id);
            sqlx::query("insert into document_content(id,document_id,kind,source_content_id,object_key,mime,size,sha256,published_at) values($1,$2,case when $3::uuid is null then 'primary' else 'preview' end,$3,$4,$5,$6,$7,clock_timestamp())")
                .bind(copy.id).bind(id).bind(preview).bind(&copy.object_key).bind(&copy.file.mime)
                .bind(copy.file.size).bind(&copy.file.sha256).execute(&mut **tx).await?;
        }
        // SQL transfers reservations to used bytes and enforces both quota ceilings.
        sqlx::query("update document set current_content_id=$1 where id=$1")
            .bind(id)
            .execute(&mut **tx)
            .await?;
        sqlx::query(
            "update document_upload set target_document_id=$2,content_id=id where id=any($1)",
        )
        .bind(&ids)
        .bind(id)
        .execute(&mut **tx)
        .await?;
        Ok(id)
    }
}
