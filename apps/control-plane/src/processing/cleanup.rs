// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! Two indexed queues: obsolete generations, then retired documents to purge. A row
//! leaves its queue once done, so an idle platform scans nothing.
use super::{
    Processing, conflict,
    models::*,
    store::{self, Generation, latest},
};
use crate::error::AppResult;
use chrono::Utc;
use uuid::Uuid;

/// Ordinals and objects swept per call.
const BATCH: u32 = 200;

/// Expired generations of live documents; a published one only for its excess ordinals.
macro_rules! generation_due {
    () => {
        "g.cleaned_at is null and g.expires_at < clock_timestamp() - interval '60 seconds' and d.deletion_id is null and (p.status in ('succeeded', 'failed') or g.committed_at is null) and (d.published_generation is distinct from g.id or cardinality(g.vector_ordinals) < g.chunks)"
    };
}
/// Retired documents with no active request and no unexpired lease.
macro_rules! purge_due {
    () => {
        "d.deletion_id is not null and d.purged_at is null and not exists (select 1 from document_processing a where a.document_id = d.id and a.status in ('pending', 'running')) and not exists (select 1 from document_processing lp join generation lg on lg.processing_id = lp.id where lp.document_id = d.id and lg.expires_at >= clock_timestamp() - interval '60 seconds')"
    };
}

#[derive(serde::Serialize, serde::Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct VectorPlan {
    pub work: Work,
    pub generation: Uuid,
    pub count: u32,
}
#[derive(serde::Serialize, utoipa::ToSchema)]
pub struct Cleanup {
    pub work: Work,
    pub generation: Uuid,
    pub output_prefix: String,
    pub chunks: u32,
    pub cursor: u32,
    pub batch: u32,
    pub preserve_objects: bool,
    pub protected_ordinals: Vec<u32>,
    pub purge_document: bool,
}
#[derive(serde::Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Cleaned {
    pub work: Work,
    pub generation: Uuid,
    pub cursor: u32,
    pub next_cursor: u32,
    pub objects_empty: bool,
    #[serde(default)]
    pub purge_document: bool,
}
#[derive(sqlx::FromRow)]
struct DueGeneration {
    #[sqlx(flatten)]
    generation: Generation,
    document_id: Uuid,
    profile: Profile,
    original_sha256: String,
    published: bool,
}
#[derive(sqlx::FromRow)]
struct DuePurge {
    document_id: Uuid,
    processing_id: Uuid,
    profile: Profile,
    original_sha256: String,
    generation: Uuid,
}

impl Processing {
    pub async fn plan_vectors(&self, plan: VectorPlan) -> AppResult<()> {
        let mut tx = self.pool.begin().await?;
        let r = store::locked(&mut tx, plan.work.processing_id).await?;
        r.bind(self.installation, &plan.work)?;
        let g = latest(&mut *tx, r.summary.id).await?.ok_or_else(invalid)?;
        if r.summary.status.terminal()
            || g.id != plan.generation
            || g.stage != Stage::Indexing
            || g.committed_at.is_some()
            || g.expires_at <= Utc::now()
            || plan.count == 0
            || plan.count > self.config.limits.chunks
            || plan.count < g.chunks as u32
        {
            return Err(conflict("stale_generation"));
        }
        sqlx::query("update generation set chunks=$2 where id=$1")
            .bind(g.id)
            .bind(plan.count as i32)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(())
    }
    pub async fn cleanup_candidates(&self) -> AppResult<Vec<Cleanup>> {
        let limit = i64::from(self.config.limits.batch);
        let work = |processing_id, document_id, original_sha256, profile| Work {
            contract_version: 1,
            installation_id: self.installation,
            processing_id,
            document_id,
            original_sha256,
            profile,
        };
        let due: Vec<DueGeneration> = sqlx::query_as(concat!(
            "select g.*, p.document_id, p.profile, d.sha256 as original_sha256, d.published_generation is not distinct from g.id as published from generation g join document_processing p on p.id = g.processing_id join document d on d.id = p.document_id where ",
            generation_due!(),
            " order by g.expires_at, g.id limit $1"
        ))
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;
        let mut result: Vec<Cleanup> = due
            .into_iter()
            .map(|c| {
                let g = c.generation;
                let cursor = g.cleanup_cursor as u32;
                let protected_ordinals = match (&g.vector_ordinals, c.published) {
                    (Some(ordinals), true) => ordinals
                        .iter()
                        .map(|v| *v as u32)
                        .filter(|v| *v >= cursor && *v < cursor.saturating_add(BATCH))
                        .collect(),
                    _ => Vec::new(),
                };
                Cleanup {
                    work: work(g.processing_id, c.document_id, c.original_sha256, c.profile),
                    generation: g.id,
                    output_prefix: g.prefix,
                    chunks: g.chunks as u32,
                    cursor,
                    batch: BATCH,
                    preserve_objects: c.published,
                    protected_ordinals,
                    purge_document: false,
                }
            })
            .collect();
        let purges: Vec<DuePurge> = sqlx::query_as(concat!(
            "select d.id as document_id, latest.processing_id, latest.profile, d.sha256 as original_sha256, latest.generation from document d cross join lateral (select p.id as processing_id, p.profile, g.id as generation from document_processing p join generation g on g.processing_id = p.id where p.document_id = d.id order by g.created_at desc, g.id desc limit 1) latest where ",
            purge_due!(),
            " order by d.id limit $1"
        ))
        .bind(limit)
        .fetch_all(&self.pool)
        .await?;
        result.extend(purges.into_iter().map(|c| Cleanup {
            work: work(c.processing_id, c.document_id, c.original_sha256, c.profile),
            generation: c.generation,
            output_prefix: store::document_output(&self.config.derived.prefix, c.document_id),
            chunks: 0,
            cursor: 0,
            batch: BATCH,
            preserve_objects: false,
            protected_ordinals: Vec::new(),
            purge_document: true,
        }));
        Ok(result)
    }
    pub async fn cleaned(&self, cleaned: Cleaned) -> AppResult<()> {
        let mut tx = self.pool.begin().await?;
        let r = store::locked(&mut tx, cleaned.work.processing_id).await?;
        r.bind(self.installation, &cleaned.work)?;
        if cleaned.purge_document != r.retired {
            return Err(conflict("stale_generation"));
        }
        let g: Generation =
            sqlx::query_as("select * from generation where id=$1 and processing_id=$2")
                .bind(cleaned.generation)
                .bind(r.summary.id)
                .fetch_optional(&mut *tx)
                .await?
                .ok_or_else(invalid)?;
        if cleaned.purge_document {
            if cleaned.cursor != 0 || cleaned.next_cursor != 0 {
                return Err(conflict("cleanup_cursor"));
            }
            if cleaned.objects_empty {
                let purged = sqlx::query(concat!(
                    "update document d set purged_at = clock_timestamp() where d.id = $1 and ",
                    purge_due!()
                ))
                .bind(r.summary.document_id)
                .execute(&mut *tx)
                .await?
                .rows_affected();
                if purged == 0 {
                    return Err(conflict("protected_generation"));
                }
            }
        } else {
            let due: bool = sqlx::query_scalar(concat!(
                "select exists(select 1 from generation g join document_processing p on p.id = g.processing_id join document d on d.id = p.document_id where g.id = $1 and ",
                generation_due!(),
                ")"
            ))
            .bind(g.id)
            .fetch_one(&mut *tx)
            .await?;
            if !due {
                return Err(conflict("protected_generation"));
            }
            let chunks = g.chunks as u32;
            if g.cleanup_cursor as u32 != cleaned.cursor
                || cleaned.next_cursor != chunks.min(cleaned.cursor.saturating_add(BATCH))
            {
                return Err(conflict("cleanup_cursor"));
            }
            // A full pass restarts at zero until the objects are gone; a published
            // generation keeps its objects, so one full pass finishes it.
            let complete = cleaned.next_cursor == chunks;
            let published = r.published_generation == Some(g.id);
            sqlx::query("update generation set cleanup_cursor=$2,cleaned_at=case when $3 then clock_timestamp() end where id=$1")
                .bind(g.id)
                .bind(if complete { 0 } else { cleaned.next_cursor as i32 })
                .bind(complete && (published || cleaned.objects_empty))
                .execute(&mut *tx)
                .await?;
        }
        tx.commit().await?;
        Ok(())
    }
}
