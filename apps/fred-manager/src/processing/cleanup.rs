// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{Processing, conflict, models::*, store::Row};
use crate::error::AppResult;
use chrono::Utc;
use uuid::Uuid;

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
}
#[derive(serde::Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct Cleaned {
    pub work: Work,
    pub generation: Uuid,
    pub cursor: u32,
    pub next_cursor: u32,
    pub objects_empty: bool,
}
impl Processing {
    pub async fn plan_vectors(&self, plan: VectorPlan) -> AppResult<()> {
        let mut tx = self.pool.begin().await?;
        let mut r: Row = sqlx::query_as("select * from document_processing where id=$1 for update")
            .bind(plan.work.processing_id)
            .fetch_one(&mut *tx)
            .await?;
        r.bind(&plan.work)?;
        let g = r.generations.last_mut().ok_or_else(invalid)?;
        if r.summary.status.terminal()
            || g.id != plan.generation
            || g.stage != Stage::Indexing
            || g.manifest.is_some()
            || g.expires_at <= Utc::now()
            || plan.count == 0
            || plan.count > self.config.limits.chunks
            || plan.count < g.chunks
        {
            return Err(conflict("stale_generation"));
        }
        g.chunks = plan.count;
        sqlx::query("update document_processing set generations=$2 where id=$1")
            .bind(r.summary.id)
            .bind(&r.generations)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(())
    }
    pub async fn cleanup_candidates(&self) -> AppResult<Vec<Cleanup>> {
        let mut tx = self.pool.begin().await?;
        let rows:Vec<Row>=sqlx::query_as("select * from document_processing where cleanup_due_at<=clock_timestamp() order by cleanup_due_at,id for update skip locked limit $1")
            .bind(self.config.limits.batch as i64).fetch_all(&mut *tx).await?;
        let mut result = Vec::new();
        for mut r in rows {
            // One generation per operation per sweep, ordered fairly within that operation.
            let selected = r
                .generations
                .iter()
                .filter(|g| eligible(&r, g.id))
                .min_by_key(|g| g.cleanup_at)
                .map(|g| g.id);
            if let Some(id) = selected {
                let g = r.generations.iter().find(|g| g.id == id).unwrap();
                let published = r.manifest.as_ref().filter(|m| m.generation == id);
                result.push(Cleanup {
                    work: r.work(),
                    generation: id,
                    output_prefix: r.prefix(&self.config.derived.prefix, id),
                    chunks: g.chunks,
                    cursor: g.cleanup_cursor,
                    batch: 200,
                    preserve_objects: published.is_some(),
                    protected_ordinals: published.map_or_else(Vec::new, |m| {
                        m.vector_ordinals
                            .iter()
                            .copied()
                            .filter(|i| {
                                *i >= g.cleanup_cursor && *i < g.cleanup_cursor.saturating_add(200)
                            })
                            .collect()
                    }),
                });
                r.generations
                    .iter_mut()
                    .find(|g| g.id == id)
                    .unwrap()
                    .cleanup_at = Some(Utc::now());
            }
            sqlx::query("update document_processing set generations=$2,cleanup_due_at=clock_timestamp()+interval '5 minutes' where id=$1").bind(r.summary.id).bind(&r.generations).execute(&mut *tx).await?;
        }
        tx.commit().await?;
        Ok(result)
    }
    pub async fn cleaned(&self, cleaned: Cleaned) -> AppResult<()> {
        let mut tx = self.pool.begin().await?;
        let mut r: Row = sqlx::query_as("select * from document_processing where id=$1 for update")
            .bind(cleaned.work.processing_id)
            .fetch_one(&mut *tx)
            .await?;
        r.bind(&cleaned.work)?;
        if !eligible(&r, cleaned.generation) {
            return Err(conflict("protected_generation"));
        }
        let published = r
            .manifest
            .as_ref()
            .is_some_and(|m| m.generation == cleaned.generation);
        let g = r
            .generations
            .iter_mut()
            .find(|g| g.id == cleaned.generation)
            .ok_or_else(invalid)?;
        if g.cleanup_cursor != cleaned.cursor
            || cleaned.next_cursor != g.chunks.min(cleaned.cursor.saturating_add(200))
        {
            return Err(conflict("cleanup_cursor"));
        }
        g.cleanup_cursor = if cleaned.next_cursor == g.chunks {
            0
        } else {
            cleaned.next_cursor
        };
        if !published && cleaned.objects_empty && cleaned.next_cursor == g.chunks {
            g.cleaned = true;
            g.reserved_bytes = 0;
        }
        let reserved: i64 = r.generations.iter().map(|g| g.reserved_bytes).sum();
        sqlx::query("update document_processing set generations=$2,reserved_bytes=$3,cleanup_due_at=clock_timestamp()+interval '30 seconds' where id=$1").bind(r.summary.id).bind(&r.generations).bind(reserved).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(())
    }
}
fn eligible(r: &Row, id: Uuid) -> bool {
    r.generations.iter().find(|g| g.id == id).is_some_and(|g| {
        g.expires_at + chrono::Duration::seconds(60) < Utc::now()
            && (r.summary.status.terminal() || g.manifest.is_none())
            && r.manifest
                .as_ref()
                .is_none_or(|m| m.generation != id || m.vectors < g.chunks as i64)
    })
}
