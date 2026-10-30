// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! SQL owns inclusion; the existing KF worker confirms the published vector projection.
use super::{Processing, conflict, models::*, store};
use crate::{
    db,
    domain::Document,
    error::{AppError, AppResult},
    onboarding, spaces,
};
use serde::{Deserialize, Serialize};
use std::time::Duration;
use uuid::Uuid;

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetRetrievable {
    pub retrievable: bool,
}
/// The document's last inclusion command, stored in its `retrieval_*` columns.
struct Command {
    id: Uuid,
    actor: String,
    target: bool,
    phase: ProjectionPhase,
    confirmed: bool,
}
type Columns = (
    Option<Uuid>,
    Option<String>,
    Option<bool>,
    Option<ProjectionPhase>,
    Option<bool>,
);
const COMMAND: &str = "select retrieval_id, retrieval_actor, retrieval_target, retrieval_phase, retrieval_confirmed from document where id=$1";
fn command(columns: Columns) -> Option<Command> {
    let (Some(id), Some(actor), Some(target), Some(phase), Some(confirmed)) = columns else {
        return None;
    };
    Some(Command {
        id,
        actor,
        target,
        phase,
        confirmed,
    })
}
#[derive(Clone, Copy, PartialEq, Serialize, Deserialize, sqlx::Type, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum ProjectionPhase {
    Ready,
    Writing,
    Applied,
}
#[derive(Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalStep {
    Claim,
    Applied,
    Confirm,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct RetrievalWork {
    pub document_id: Uuid,
    pub operation_id: Uuid,
    pub manifest: Manifest,
    pub retrievable: bool,
    pub confirmed: bool,
    pub phase: ProjectionPhase,
}
#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RetrievalConfirmation {
    pub step: RetrievalStep,
    pub operation_id: Uuid,
    pub retrievable: bool,
}

impl Processing {
    pub async fn published_retrievable(
        &self,
        document_id: Uuid,
        prefix: &str,
        manifest: &Manifest,
    ) -> AppResult<bool> {
        use sha2::{Digest, Sha256};
        use tokio::io::AsyncReadExt;
        let artifact = manifest
            .artifacts
            .iter()
            .find(|a| a.path == "metadata.json")
            .ok_or_else(invalid)?;
        if !(1..=2_097_152).contains(&artifact.size) {
            return Err(invalid());
        }
        let object = self
            .derived
            .get(&format!("{prefix}metadata.json"))
            .await
            .map_err(|_| super::unavailable())?;
        let mut bytes = Vec::new();
        tokio::time::timeout(
            Duration::from_secs(30),
            object
                .body
                .into_async_read()
                .take(artifact.size as u64 + 1)
                .read_to_end(&mut bytes),
        )
        .await
        .map_err(|_| super::unavailable())?
        .map_err(|_| super::unavailable())?;
        if bytes.len() as i64 != artifact.size
            || format!("{:x}", Sha256::digest(&bytes)) != artifact.sha256
        {
            return Err(invalid());
        }
        let metadata: serde_json::Value = serde_json::from_slice(&bytes).map_err(|_| invalid())?;
        if metadata["identity"]["document_uid"].as_str() != Some(document_id.to_string().as_str()) {
            return Err(invalid());
        }
        let value = metadata["source"]["retrievable"]
            .as_bool()
            .ok_or_else(invalid)?;
        let tabular = published_tabular(&metadata, manifest)?;
        if value != (manifest.vectors > 0 || tabular) {
            return Err(invalid());
        }
        if manifest.vectors > 0
            && metadata["processing"]["stages"]["vector"].as_str() != Some("done")
        {
            return Err(invalid());
        }
        Ok(value)
    }

    async fn retrieval_command(&self, id: Uuid) -> AppResult<Command> {
        let columns: Columns = sqlx::query_as(COMMAND)
            .bind(id)
            .fetch_optional(&self.pool)
            .await?
            .ok_or(AppError::NotFound)?;
        command(columns).ok_or_else(|| conflict("retrieval_command_missing"))
    }

    pub async fn set_retrievable(
        &self,
        actor: &str,
        id: Uuid,
        input: SetRetrievable,
    ) -> AppResult<Document> {
        let document = db::document(&self.pool, id).await?;
        let mut tx =
            spaces::authorized_write(&self.pool, &self.fga, actor, document.space_id).await?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), actor).await?;
        let document: Document =
            sqlx::query_as("select * from document where id=$1 and deletion_id is null for update")
                .bind(id)
                .fetch_one(&mut *tx)
                .await?;
        let vectors: i64 = sqlx::query_scalar("select coalesce(cardinality(g.vector_ordinals),0)::bigint from document d left join generation g on g.id=d.published_generation where d.id=$1")
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
        if vectors == 0 {
            // Publication already verified these generation-scoped Parquet descriptors.
            // With no vector projection, SQL inclusion is the complete operation.
            if document.retrievable_pending {
                return Err(conflict("retrieval_pending"));
            }
            let tabular: bool = sqlx::query_scalar("select exists(select 1 from document d join generation g on g.id=d.published_generation join artifact a on a.generation_id=g.id where d.id=$1 and g.rows is not null and a.path like 'datasets/%.parquet')")
                .bind(id).fetch_one(&mut *tx).await?;
            if !tabular {
                return Err(conflict("document_not_indexed"));
            }
            let updated = sqlx::query_as("update document set retrievable=$2,retrieval_id=null,retrieval_actor=null,retrieval_target=null,retrieval_phase=null,retrieval_confirmed=null where id=$1 returning *")
                .bind(id).bind(input.retrievable).fetch_one(&mut *tx).await?;
            tx.commit().await?;
            tracing::info!(document_id=%id,retrievable=input.retrievable,"Tabular inclusion updated");
            return Ok(updated);
        }
        let previous: Columns = sqlx::query_as(COMMAND).bind(id).fetch_one(&mut *tx).await?;
        let command = match command(previous) {
            Some(c) if !c.confirmed => {
                if c.target != input.retrievable || c.actor != actor {
                    return Err(conflict("retrieval_pending"));
                }
                c
            }
            // Publication and confirmation both record verified projection state.
            _ if document.retrievable == input.retrievable => return Ok(document),
            _ => {
                let c = Command {
                    id: Uuid::new_v4(),
                    actor: actor.to_owned(),
                    target: input.retrievable,
                    phase: ProjectionPhase::Ready,
                    confirmed: false,
                };
                sqlx::query("update document set retrieval_id=$2,retrieval_actor=$3,retrieval_target=$4,retrieval_phase=$5,retrieval_confirmed=false where id=$1")
                    .bind(id).bind(c.id).bind(&c.actor).bind(c.target).bind(c.phase).execute(&mut *tx).await?;
                c
            }
        };
        tx.commit().await?;
        super::dispatch::deliver_retrieval(&self.config, self.installation, id, command.id)
            .await
            .map_err(|_| pending())?;
        // No connection or authorization lock is held while KF applies the projection.
        for _ in 0..50 {
            let current = self.retrieval_command(id).await?;
            if current.id != command.id {
                return Err(conflict("retrieval_changed"));
            }
            if current.confirmed {
                return Ok(db::document(&self.pool, document.id).await?);
            }
            tokio::time::sleep(Duration::from_millis(500)).await;
        }
        Err(pending())
    }

    pub async fn retrieval_work(&self, id: Uuid, operation: Uuid) -> AppResult<RetrievalWork> {
        let c = self.retrieval_command(id).await?;
        if c.id != operation {
            return Err(conflict("retrieval_changed"));
        }
        let document = db::pipeline_document(&self.pool, id).await?;
        spaces::authorize(
            &self.pool,
            &self.fga,
            &c.actor,
            document.space_id,
            crate::domain::Permission::Write,
        )
        .await?;
        onboarding::require_accepted(&self.pool, self.terms.as_deref(), &c.actor).await?;
        let published: store::Generation = sqlx::query_as(
            "select g.* from document d join generation g on g.id=d.published_generation where d.id=$1",
        )
        .bind(id)
        .fetch_optional(&self.pool)
        .await?
        .ok_or(AppError::NotFound)?;
        Ok(RetrievalWork {
            document_id: id,
            operation_id: operation,
            manifest: store::manifest(&self.pool, &published).await?,
            retrievable: c.target,
            confirmed: c.confirmed,
            phase: c.phase,
        })
    }

    pub async fn confirm_retrievable(
        &self,
        id: Uuid,
        input: RetrievalConfirmation,
    ) -> AppResult<()> {
        let work = self.retrieval_work(id, input.operation_id).await?;
        if input.retrievable != work.retrievable {
            return Err(invalid());
        }
        let document = db::pipeline_document(&self.pool, id).await?;
        let c = self.retrieval_command(id).await?;
        let mut tx =
            spaces::authorized_write(&self.pool, &self.fga, &c.actor, document.space_id).await?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &c.actor).await?;
        // The atomic phase fence survives worker/API restarts and Temporal history expiry.
        let changed = match input.step {
            RetrievalStep::Claim => sqlx::query("update document set retrieval_phase='writing' where id=$1 and retrieval_id=$2 and retrieval_phase='ready' and not retrieval_confirmed")
                .bind(id).bind(input.operation_id).execute(&mut *tx).await?.rows_affected(),
            RetrievalStep::Applied => sqlx::query("update document set retrieval_phase='applied' where id=$1 and retrieval_id=$2 and retrieval_phase in ('writing','applied')")
                .bind(id).bind(input.operation_id).execute(&mut *tx).await?.rows_affected(),
            RetrievalStep::Confirm => sqlx::query("update document set retrievable=$3,retrieval_confirmed=true where id=$1 and retrieval_id=$2 and retrieval_phase='applied'")
                .bind(id).bind(input.operation_id).bind(input.retrievable).execute(&mut *tx).await?.rows_affected(),
        };
        if changed != 1 {
            return Err(conflict("retrieval_projection_uncertain"));
        }
        tx.commit().await?;
        tracing::info!(document_id=%id,operation_id=%input.operation_id,retrievable=input.retrievable,"Document search inclusion callback persisted");
        Ok(())
    }
}
/// Tabular inclusion requires descriptors pointing only to verified manifest objects.
fn published_tabular(metadata: &serde_json::Value, manifest: &Manifest) -> AppResult<bool> {
    let extensions = &metadata["extensions"];
    let single = extensions.get("tabular_v1");
    let multi = extensions.get("tabular_multi_v1");
    let tables: Vec<&serde_json::Value> = match (single, multi) {
        (None, None) if manifest.rows.is_none() => return Ok(false),
        (Some(table), None) => vec![table],
        (None, Some(multi)) => multi["tables"]
            .as_array()
            .ok_or_else(invalid)?
            .iter()
            .collect(),
        _ => return Err(invalid()),
    };
    if tables.is_empty() || metadata["processing"]["stages"]["sql"].as_str() != Some("done") {
        return Err(invalid());
    }
    let uid = metadata["identity"]["document_uid"]
        .as_str()
        .ok_or_else(invalid)?;
    let revision = metadata["file"]["sha256"].as_str().ok_or_else(invalid)?;
    let mut rows = 0_i64;
    for table in tables {
        let path = table["object_key"].as_str().ok_or_else(invalid)?;
        let count = table["row_count"]
            .as_i64()
            .filter(|n| *n >= 0)
            .ok_or_else(invalid)?;
        rows = rows.checked_add(count).ok_or_else(invalid)?;
        if !path.starts_with("datasets/")
            || !path.ends_with(".parquet")
            || table["format"].as_str() != Some("parquet")
            || table["dataset_uid"].as_str() != Some(uid)
            || table["source_revision"].as_str() != Some(revision)
            || !manifest
                .artifacts
                .iter()
                .any(|a| a.path == path && Some(a.size) == table["file_size_bytes"].as_i64())
        {
            return Err(invalid());
        }
    }
    if manifest.rows != Some(rows) || metadata["file"]["row_count"].as_i64() != Some(rows) {
        return Err(invalid());
    }
    Ok(true)
}

fn pending() -> AppError {
    AppError::problem(
        axum::http::StatusCode::SERVICE_UNAVAILABLE,
        "retrieval_pending",
        "Search inclusion is not confirmed. Refresh or repeat the same request; an opposite change is blocked while the projection is unconfirmed. An uncertain writer requires investigation; repeating never starts a second writer.",
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    fn table_publication(multi: bool) -> (serde_json::Value, Manifest) {
        let uid = Uuid::new_v4().to_string();
        let table = serde_json::json!({"dataset_uid":uid,"object_key":"datasets/table.parquet",
            "format":"parquet","source_revision":"a".repeat(64),"file_size_bytes":100,"row_count":2});
        let extensions = if multi {
            // Identical sheets may legitimately share a content-addressed artifact.
            serde_json::json!({"tabular_multi_v1":{"tables":[table.clone(),table]}})
        } else {
            serde_json::json!({"tabular_v1":table})
        };
        let rows = if multi { 4 } else { 2 };
        let metadata = serde_json::json!({"identity":{"document_uid":uid},
            "file":{"sha256":"a".repeat(64),"row_count":rows},
            "processing":{"stages":{"sql":"done"}},"extensions":extensions});
        let manifest = Manifest {
            generation: Uuid::new_v4(),
            chunks: 0,
            vectors: 0,
            vector_ordinals: vec![],
            rows: Some(rows),
            artifacts: vec![Artifact {
                path: "datasets/table.parquet".into(),
                size: 100,
                sha256: "b".repeat(64),
            }],
        };
        (metadata, manifest)
    }

    #[test]
    fn verified_csv_and_workbook_tables_are_retrievable_without_vectors() {
        for multi in [false, true] {
            let (metadata, manifest) = table_publication(multi);
            assert!(published_tabular(&metadata, &manifest).unwrap());
        }
    }

    #[test]
    fn table_publication_rejects_unfinished_or_foreign_artifacts() {
        let (metadata, manifest) = table_publication(false);
        for (key, value) in [
            ("object_key", serde_json::json!("datasets/foreign.parquet")),
            ("dataset_uid", serde_json::json!(Uuid::new_v4().to_string())),
            ("source_revision", serde_json::json!("c".repeat(64))),
            ("format", serde_json::json!("csv")),
            ("file_size_bytes", serde_json::json!(99)),
            ("row_count", serde_json::json!(3)),
        ] {
            let mut changed = metadata.clone();
            changed["extensions"]["tabular_v1"][key] = value;
            assert!(published_tabular(&changed, &manifest).is_err(), "{key}");
        }
        let mut unfinished = metadata.clone();
        unfinished["processing"]["stages"]["sql"] = serde_json::json!("failed");
        assert!(published_tabular(&unfinished, &manifest).is_err());
        let mut unpublished = manifest.clone();
        unpublished.artifacts.clear();
        assert!(published_tabular(&metadata, &unpublished).is_err());
        let mut empty = metadata.clone();
        empty["extensions"] = serde_json::json!({"tabular_multi_v1":{"tables":[]}});
        assert!(published_tabular(&empty, &manifest).is_err());
        empty["extensions"] = serde_json::json!({});
        assert!(published_tabular(&empty, &manifest).is_err());
        let mut text_only = manifest;
        text_only.rows = None;
        assert!(!published_tabular(&empty, &text_only).unwrap());
    }

    #[test]
    fn inclusion_requires_an_explicit_boolean_and_rejects_unknown_fields() {
        for body in [
            "{}",
            r#"{"retrievable":null}"#,
            r#"{"retrievable":true,"actor":"other"}"#,
        ] {
            assert!(
                serde_json::from_str::<SetRetrievable>(body).is_err(),
                "{body}"
            );
        }
        assert!(
            serde_json::from_str::<SetRetrievable>(r#"{"retrievable":false}"#)
                .is_ok_and(|s| !s.retrievable)
        );
    }
    #[test]
    fn confirmation_requires_its_step() {
        let operation = Uuid::nil();
        assert!(
            serde_json::from_str::<RetrievalConfirmation>(&format!(
                r#"{{"operation_id":"{operation}","retrievable":true}}"#
            ))
            .is_err()
        );
        assert!(
            serde_json::from_str::<RetrievalConfirmation>(&format!(
                r#"{{"operation_id":"{operation}","retrievable":true,"step":"confirm"}}"#
            ))
            .is_ok_and(|c| matches!(c.step, RetrievalStep::Confirm))
        );
    }
}
