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
use sqlx::types::Json;
use std::time::Duration;
use uuid::Uuid;

#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetRetrievable {
    /// null restores an untouched legacy publication from its verified metadata and chunks.
    #[schema(required = true)]
    #[serde(deserialize_with = "Option::<bool>::deserialize")]
    pub retrievable: Option<bool>,
}
#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Command {
    id: Uuid,
    actor: String,
    target: Option<bool>,
    confirmed: bool,
    #[serde(default)]
    phase: ProjectionPhase,
}
// Missing phase belongs to an old command whose writer completion is unknown.
#[derive(Clone, Copy, Default, PartialEq, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ProjectionPhase {
    #[default]
    Uncertain,
    Ready,
    Writing,
    Applied,
}
#[derive(Default, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum RetrievalStep {
    Claim,
    Applied,
    #[default]
    Confirm,
}
#[derive(Serialize, utoipa::ToSchema)]
pub struct RetrievalWork {
    pub document_id: Uuid,
    pub operation_id: Uuid,
    pub manifest: Manifest,
    pub retrievable: bool,
    pub restore: bool,
    pub confirmed: bool,
    pub phase: ProjectionPhase,
}
#[derive(Deserialize, utoipa::ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RetrievalConfirmation {
    #[serde(default)]
    pub step: RetrievalStep,
    pub operation_id: Uuid,
    pub retrievable: bool,
}

impl Processing {
    pub async fn published_retrievable(
        &self,
        row: &store::Row,
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
        let key = format!(
            "{}metadata.json",
            row.prefix(&self.config.derived.prefix, manifest.generation)
        );
        let object = self
            .derived
            .get(&key)
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
        if metadata["identity"]["document_uid"].as_str()
            != Some(row.summary.document_id.to_string().as_str())
        {
            return Err(invalid());
        }
        let value = metadata["source"]["retrievable"]
            .as_bool()
            .ok_or_else(invalid)?;
        if value != (manifest.vectors > 0) {
            return Err(invalid());
        }
        if value && metadata["processing"]["stages"]["vector"].as_str() != Some("done") {
            return Err(invalid());
        }
        Ok(value)
    }

    async fn retrieval_command(&self, id: Uuid) -> AppResult<Command> {
        let command: Option<Json<Command>> =
            sqlx::query_scalar("select retrieval_command from document where id=$1")
                .bind(id)
                .fetch_optional(&self.pool)
                .await?
                .ok_or(AppError::NotFound)?;
        command
            .map(|c| c.0)
            .ok_or_else(|| conflict("retrieval_command_missing"))
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
        let document: Document = sqlx::query_as("select * from document where id=$1 for update")
            .bind(id)
            .fetch_one(&mut *tx)
            .await?;
        let row: store::Row = sqlx::query_as(
            "select * from document_processing where document_id=$1 and status='succeeded'",
        )
        .bind(id)
        .fetch_optional(&mut *tx)
        .await?
        .ok_or_else(|| conflict("document_not_vectorized"))?;
        if input.retrievable.is_some() && row.summary.vectors == 0 {
            return Err(conflict("document_not_vectorized"));
        }
        let previous: Option<Json<Command>> =
            sqlx::query_scalar("select retrieval_command from document where id=$1")
                .bind(id)
                .fetch_one(&mut *tx)
                .await?;
        let command = match previous {
            Some(c) if c.confirmed && c.target == input.retrievable => {
                return Ok(document);
            }
            Some(c) if !c.confirmed => {
                if c.target != input.retrievable || c.actor != actor {
                    return Err(conflict("retrieval_pending"));
                }
                c.0
            }
            previous => {
                if input.retrievable.is_none() && previous.is_some() {
                    return Err(conflict("retrieval_already_managed"));
                }
                // Even an equal value is projected: pre-migration SQL defaults are not evidence.
                Command {
                    id: Uuid::new_v4(),
                    actor: actor.to_owned(),
                    target: input.retrievable,
                    confirmed: false,
                    phase: ProjectionPhase::Ready,
                }
            }
        };
        sqlx::query("update document set retrieval_command=$2 where id=$1")
            .bind(id)
            .bind(Json(&command))
            .execute(&mut *tx)
            .await?;
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
        let document = db::document(&self.pool, id).await?;
        spaces::authorize(
            &self.pool,
            &self.fga,
            &c.actor,
            document.space_id,
            crate::domain::Permission::Write,
        )
        .await?;
        onboarding::require_accepted(&self.pool, self.terms.as_deref(), &c.actor).await?;
        let row: store::Row = sqlx::query_as(
            "select * from document_processing where document_id=$1 and status='succeeded'",
        )
        .bind(id)
        .fetch_one(&self.pool)
        .await?;
        if row.installation_id != self.installation {
            return Err(AppError::NotFound);
        }
        let manifest = row.manifest.as_ref().ok_or_else(invalid)?.0.clone();
        let value = match c.target {
            Some(value) => value,
            None => self.published_retrievable(&row, &manifest).await?,
        };
        Ok(RetrievalWork {
            document_id: id,
            operation_id: operation,
            manifest,
            retrievable: value,
            restore: c.target.is_none(),
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
        let document = db::document(&self.pool, id).await?;
        let c = self.retrieval_command(id).await?;
        let mut tx =
            spaces::authorized_write(&self.pool, &self.fga, &c.actor, document.space_id).await?;
        onboarding::require_accepted(&mut *tx, self.terms.as_deref(), &c.actor).await?;
        // The atomic phase fence survives worker/API restarts and Temporal history expiry.
        let changed = match input.step {
            RetrievalStep::Claim => sqlx::query("update document set retrieval_command=jsonb_set(retrieval_command,'{phase}','\"writing\"') where id=$1 and retrieval_command->>'id'=$2 and retrieval_command->>'phase'='ready' and retrieval_command->>'confirmed'='false'")
                .bind(id).bind(input.operation_id.to_string()).execute(&mut *tx).await?.rows_affected(),
            RetrievalStep::Applied => sqlx::query("update document set retrieval_command=jsonb_set(retrieval_command,'{phase}','\"applied\"') where id=$1 and retrieval_command->>'id'=$2 and retrieval_command->>'phase' in ('writing','applied')")
                .bind(id).bind(input.operation_id.to_string()).execute(&mut *tx).await?.rows_affected(),
            RetrievalStep::Confirm => sqlx::query("update document set retrievable=$3,retrieval_command=jsonb_set(retrieval_command,'{confirmed}','true') where id=$1 and retrieval_command->>'id'=$2 and retrieval_command->>'phase'='applied'")
                .bind(id).bind(input.operation_id.to_string()).bind(input.retrievable).execute(&mut *tx).await?.rows_affected(),
        };
        if changed != 1 {
            return Err(conflict("retrieval_projection_uncertain"));
        }
        tx.commit().await?;
        tracing::info!(document_id=%id,operation_id=%input.operation_id,retrievable=input.retrievable,"Document search inclusion callback persisted");
        Ok(())
    }
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
    #[test]
    fn legacy_commands_never_grant_a_new_writer() {
        let c: Command = serde_json::from_value(serde_json::json!({
            "id": Uuid::new_v4(), "actor": "writer", "target": false, "confirmed": false
        }))
        .unwrap();
        assert!(c.phase == ProjectionPhase::Uncertain);
    }
    #[test]
    fn restoration_requires_an_explicit_null_and_rejects_unknown_fields() {
        assert!(serde_json::from_str::<SetRetrievable>("{}").is_err());
        assert!(
            serde_json::from_str::<SetRetrievable>(r#"{"retrievable":true,"actor":"other"}"#)
                .is_err()
        );
        assert!(
            serde_json::from_str::<SetRetrievable>(r#"{"retrievable":null}"#)
                .unwrap()
                .retrievable
                .is_none()
        );
    }
}
