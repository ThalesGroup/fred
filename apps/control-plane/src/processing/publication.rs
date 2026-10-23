// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{
    Processing, conflict,
    models::*,
    store::{Row, row},
};
use crate::{error::AppResult, onboarding, spaces};
use chrono::Utc;
use sqlx::types::Json;

impl Processing {
    /// Verify immutable staged bytes before acquiring the short publication lock.
    pub async fn commit(&self, commit: Commit) -> AppResult<Summary> {
        commit.manifest.validate(
            self.config.limits.output_bytes,
            self.config.limits.artifacts,
            self.config.limits.chunks,
        )?;
        let r = row(&self.pool, commit.work.processing_id).await?;
        r.bind(&commit.work)?;
        let generation = r
            .generations
            .iter()
            .find(|g| g.id == commit.manifest.generation && g.stage == commit.stage)
            .ok_or_else(|| conflict("stale_generation"))?;
        if let Some(saved) = &generation.manifest {
            if saved != &commit.manifest {
                return Err(conflict("manifest_conflict"));
            }
            return Ok(r.summary);
        }
        if r.summary.status.terminal()
            || generation.expires_at <= Utc::now()
            || r.generations.last().map(|g| g.id) != Some(generation.id)
        {
            return Err(conflict("stale_generation"));
        }
        let prefix = r.prefix(&self.config.derived.prefix, generation.id);
        for artifact in &commit.manifest.artifacts {
            let hash = decode_digest(&artifact.sha256)?;
            self.derived
                .verify(&format!("{prefix}{}", artifact.path), artifact.size, &hash)
                .await
                .map_err(|_| super::unavailable())?;
        }
        if commit.stage == Stage::Indexing {
            let document = crate::db::document(&self.pool, r.summary.document_id).await?;
            let names: std::collections::HashSet<&str> = commit
                .manifest
                .artifacts
                .iter()
                .map(|a| a.path.as_str())
                .collect();
            if commit.manifest.vectors > generation.chunks as i64
                || commit
                    .manifest
                    .vector_ordinals
                    .iter()
                    .any(|v| *v >= generation.chunks)
                || (commit.manifest.chunks > 0 && !names.contains("chunks.jsonl"))
                || !names.contains("metadata.json")
                || !names.contains("output.md")
                || (commit.manifest.rows.is_none()
                    && ((generation.chunks > 0 && commit.manifest.chunks == 0)
                        || commit.manifest.vectors != commit.manifest.chunks))
            {
                return Err(invalid());
            }
            let extension = document
                .name
                .rsplit('.')
                .next()
                .unwrap_or("")
                .to_lowercase();
            if matches!(extension.as_str(), "docx" | "doc" | "odt" | "pptx" | "ppt")
                && !names.contains("native.pdf")
            {
                return Err(invalid());
            }
        }
        let retrievable = if commit.stage == Stage::Indexing {
            Some(self.published_retrievable(&r, &commit.manifest).await?)
        } else {
            None
        };
        let mut tx = if commit.stage == Stage::Indexing {
            let mut tx =
                spaces::authorized_write(&self.pool, &self.fga, &r.actor, r.space_id).await?;
            onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &r.actor).await?;
            tx
        } else {
            self.pool.begin().await?
        };
        let mut current: Row =
            sqlx::query_as("select * from document_processing where id=$1 for update")
                .bind(r.summary.id)
                .fetch_one(&mut *tx)
                .await?;
        let g = current
            .generations
            .last_mut()
            .ok_or_else(|| conflict("stale_generation"))?;
        if g.id != commit.manifest.generation || g.stage != commit.stage {
            return Err(conflict("stale_generation"));
        }
        if let Some(saved) = &g.manifest {
            return if saved == &commit.manifest {
                Ok(current.summary)
            } else {
                Err(conflict("manifest_conflict"))
            };
        }
        if g.expires_at <= Utc::now()
            || current.deadline_at <= Utc::now()
            || current.summary.status.terminal()
        {
            return Err(conflict("stale_generation"));
        }
        g.reserved_bytes = commit.manifest.artifacts.iter().map(|a| a.size).sum();
        g.manifest = Some(commit.manifest.clone());
        let reserved: i64 = current.generations.iter().map(|g| g.reserved_bytes).sum();
        let summary = if commit.stage == Stage::Indexing {
            sqlx::query_as("update document_processing set generations=$2,reserved_bytes=$3,status='succeeded',stage='done',error_code=null,revision=revision+1,completed_at=clock_timestamp(),manifest=$4,chunks=$5,vectors=$6,rows=$7 where id=$1 returning *")
                .bind(r.summary.id).bind(&current.generations).bind(reserved).bind(Json(&commit.manifest)).bind(commit.manifest.chunks).bind(commit.manifest.vectors).bind(commit.manifest.rows).fetch_one(&mut *tx).await?
        } else {
            sqlx::query_as("update document_processing set generations=$2,reserved_bytes=$3,revision=revision+1 where id=$1 returning *")
                .bind(r.summary.id).bind(&current.generations).bind(reserved).fetch_one(&mut *tx).await?
        };
        if let Some(value) = retrievable {
            sqlx::query(
                "update document set retrievable=$2 where id=$1 and retrieval_command is null",
            )
            .bind(r.summary.document_id)
            .bind(value)
            .execute(&mut *tx)
            .await?;
        }
        tx.commit().await?;
        tracing::info!(operation_id=%r.summary.id,document_id=%r.summary.document_id,stage=?commit.stage,outcome="committed","Document processing output committed");
        Ok(summary)
    }
}
fn decode_digest(s: &str) -> AppResult<[u8; 32]> {
    if !digest(s) {
        return Err(invalid());
    }
    let mut bytes = [0; 32];
    for (i, b) in bytes.iter_mut().enumerate() {
        *b = u8::from_str_radix(&s[i * 2..i * 2 + 2], 16).map_err(|_| invalid())?;
    }
    Ok(bytes)
}
