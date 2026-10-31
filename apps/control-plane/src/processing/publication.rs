// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::{
    Processing, conflict,
    models::*,
    store::{self, generations, latest, row},
};
use crate::{documents, error::AppResult, onboarding};
use chrono::Utc;

impl Processing {
    /// Verify immutable staged bytes before acquiring the short publication lock.
    pub async fn commit(&self, commit: Commit) -> AppResult<Summary> {
        commit.manifest.validate(
            self.config.limits.output_bytes,
            self.config.limits.artifacts,
            self.config.limits.chunks,
        )?;
        let mut manifest = commit.manifest;
        manifest.artifacts.sort_by(|a, b| a.path.cmp(&b.path));
        let r = row(&self.pool, commit.work.processing_id).await?;
        r.bind(self.installation, &commit.work)?;
        let all = generations(&self.pool, r.summary.id).await?;
        let generation = all
            .iter()
            .find(|g| g.id == manifest.generation && g.stage == commit.stage)
            .ok_or_else(|| conflict("stale_generation"))?;
        if generation.committed_at.is_some() {
            if store::manifest(&self.pool, generation).await? != manifest {
                return Err(conflict("manifest_conflict"));
            }
            return Ok(r.summary);
        }
        if r.summary.status.terminal()
            || generation.expires_at <= Utc::now()
            || all.last().map(|g| g.id) != Some(generation.id)
        {
            return Err(conflict("stale_generation"));
        }
        for artifact in &manifest.artifacts {
            let hash = decode_digest(&artifact.sha256)?;
            self.derived
                .verify(
                    &format!("{}{}", generation.prefix, artifact.path),
                    artifact.size,
                    &hash,
                )
                .await
                .map_err(|_| super::unavailable())?;
        }
        let planned = generation.chunks as u32;
        if commit.stage == Stage::Indexing {
            let document = crate::db::pipeline_document(&self.pool, r.summary.document_id).await?;
            let names: std::collections::HashSet<&str> =
                manifest.artifacts.iter().map(|a| a.path.as_str()).collect();
            if manifest.vectors > i64::from(planned)
                || manifest.vector_ordinals.iter().any(|v| *v >= planned)
                || (manifest.chunks > 0 && !names.contains("chunks.jsonl"))
                || !names.contains("metadata.json")
                || !names.contains("output.md")
                || (manifest.rows.is_none() && planned > 0 && manifest.chunks == 0)
            {
                return Err(invalid());
            }
            let extension = document
                .name
                .rsplit('.')
                .next()
                .unwrap_or("")
                .to_lowercase();
            if matches!(extension.as_str(), "csv" | "xlsx" | "xls" | "xlsm")
                && (manifest.rows.is_none()
                    || (extension != "csv" && !names.contains("tables.json")))
            {
                return Err(invalid());
            }
            if matches!(extension.as_str(), "docx" | "doc" | "odt" | "pptx" | "ppt")
                && !names.contains("native.pdf")
            {
                return Err(invalid());
            }
        }
        let retrievable = if commit.stage == Stage::Indexing {
            Some(
                self.published_retrievable(r.summary.document_id, &generation.prefix, &manifest)
                    .await?,
            )
        } else {
            None
        };
        let mut tx = if commit.stage == Stage::Indexing {
            let mut tx =
                documents::authorized_mutation(&self.pool, &r.actor, r.space_id, r.session_id)
                    .await?;
            onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &r.actor).await?;
            tx
        } else {
            self.pool.begin().await?
        };
        let current = store::locked(&mut tx, r.summary.id).await?;
        let g = latest(&mut *tx, r.summary.id)
            .await?
            .ok_or_else(|| conflict("stale_generation"))?;
        if g.id != manifest.generation || g.stage != commit.stage {
            return Err(conflict("stale_generation"));
        }
        if g.committed_at.is_some() {
            return if store::manifest(&mut *tx, &g).await? == manifest {
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
        let (paths, (sizes, digests)): (Vec<&str>, (Vec<i64>, Vec<&str>)) = manifest
            .artifacts
            .iter()
            .map(|a| (a.path.as_str(), (a.size, a.sha256.as_str())))
            .unzip();
        sqlx::query("insert into artifact(generation_id,path,size,sha256) select $1,* from unnest($2::text[],$3::bigint[],$4::text[])")
            .bind(g.id).bind(&paths).bind(&sizes).bind(&digests).execute(&mut *tx).await?;
        let ordinals: Vec<i32> = manifest.vector_ordinals.iter().map(|v| *v as i32).collect();
        sqlx::query("update generation set committed_at=clock_timestamp(),vector_ordinals=$2,rows=$3 where id=$1")
            .bind(g.id).bind(&ordinals).bind(manifest.rows).execute(&mut *tx).await?;
        if let Some(value) = retrievable {
            // No ordinal beyond the published ones means nothing is left for cleanup to sweep.
            sqlx::query("update generation set cleaned_at=clock_timestamp() where id=$1 and cardinality(vector_ordinals)=chunks")
                .bind(g.id).execute(&mut *tx).await?;
            sqlx::query("update document_processing set status='succeeded',stage='done',error_code=null,revision=revision+1,completed_at=clock_timestamp() where id=$1")
                .bind(r.summary.id).execute(&mut *tx).await?;
            sqlx::query("update document set published_generation=$2,retrievable=case when retrieval_id is null then $3 else retrievable end where id=$1")
                .bind(r.summary.document_id).bind(g.id).bind(value).execute(&mut *tx).await?;
        } else {
            sqlx::query("update document_processing set revision=revision+1 where id=$1")
                .bind(r.summary.id)
                .execute(&mut *tx)
                .await?;
        }
        let summary = store::summary(&mut *tx, r.summary.id).await?;
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
