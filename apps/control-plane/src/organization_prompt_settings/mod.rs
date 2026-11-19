// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Organization execution instructions; prompt-library resources have a separate lifecycle.
mod defaults;
mod http;
pub use http::routes;

use crate::{
    error::{AppError, AppResult},
    model_catalog::instance::ModelOfferKey,
};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, types::Json};
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Default, sqlx::FromRow)]
pub struct StoredPromptSettings {
    pub common_text: Option<String>,
    pub common_updated_by: Option<String>,
    pub common_updated_at: Option<DateTime<Utc>>,
    pub creation_text: Option<String>,
    pub creation_model: Option<Json<ModelOfferKey>>,
    pub creation_reasoning: bool,
    pub creation_text_updated_by: Option<String>,
    pub creation_text_updated_at: Option<DateTime<Utc>>,
    pub creation_updated_by: Option<String>,
    pub creation_updated_at: Option<DateTime<Utc>>,
}

/// Read within the caller's admission snapshot. Null preserves that runtime's own
/// default; an explicit empty common text suppresses the block. No network I/O.
pub async fn read<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    organization: Uuid,
) -> AppResult<StoredPromptSettings> {
    Ok(sqlx::query_as("select *, case when creation_model_source_id is null then null else jsonb_build_object('source_id',creation_model_source_id,'upstream_model_id',creation_model_upstream_id) end as creation_model from organization_prompt_settings where organization_id=$1")
        .bind(organization).fetch_optional(ex).await?.unwrap_or_default())
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetCommonPrompt {
    #[schema(max_length = 20000)]
    pub text: String,
}

#[derive(Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PatchCreationAssistant {
    /// Omitted: preserve; null: runtime default; string: save verbatim and date the text.
    #[serde(default, deserialize_with = "crate::extract::present")]
    #[schema(value_type=Option<String>, max_length=20000)]
    pub text: Option<Option<String>>,
    /// Stable Weaver model identity. Null follows organization model policy.
    #[serde(default, deserialize_with = "crate::extract::present")]
    #[schema(value_type=Option<ModelOfferKey>)]
    pub model: Option<Option<ModelOfferKey>>,
    pub reasoning: Option<bool>,
}

fn validate_text(text: &str, nonblank: bool) -> AppResult<()> {
    if text.chars().count() > 20000 || text.contains('\0') || (nonblank && text.trim().is_empty()) {
        return Err(AppError::Unprocessable("Prompt must contain at most 20000 Unicode characters, no NUL, and creation text must not be blank.".into()));
    }
    if crate::field_values::reserved_prompt_tag(text)? {
        return Err(AppError::Unprocessable(
            "Reserved system-prompt tags are not allowed.".into(),
        ));
    }
    Ok(())
}

/// Caller owns authorization and the organization mutation lock; each write touches
/// only its tab. PostgreSQL serializes competing writes without optimistic revisions.
pub async fn save_common(
    conn: &mut PgConnection,
    organization: Uuid,
    actor: &str,
    text: &str,
) -> AppResult<()> {
    validate_text(text, false)?;
    sqlx::query("insert into organization_prompt_settings(organization_id,common_text,common_updated_by,common_updated_at)
        values($1,$2,$3,clock_timestamp()) on conflict(organization_id) do update set
        common_text=excluded.common_text,common_updated_by=excluded.common_updated_by,common_updated_at=excluded.common_updated_at")
        .bind(organization).bind(text).bind(actor).execute(conn).await?;
    Ok(())
}

/// Atomic sparse update: explicit text saves acknowledge the current default revision
/// even when the text is unchanged. Model/reasoning edits leave the text date intact.
pub async fn save_creation(
    conn: &mut PgConnection,
    organization: Uuid,
    actor: &str,
    patch: &PatchCreationAssistant,
) -> AppResult<()> {
    if let Some(Some(text)) = &patch.text {
        validate_text(text, true)?;
    }
    if patch.text.is_none() && patch.model.is_none() && patch.reasoning.is_none() {
        return Ok(());
    }
    sqlx::query("insert into organization_prompt_settings(organization_id) values($1) on conflict do nothing")
        .bind(organization).execute(&mut *conn).await?;
    sqlx::query("update organization_prompt_settings set
        creation_text=case when $2 then $3 else creation_text end,
        creation_text_updated_by=case when $2 then $4 else creation_text_updated_by end,
        creation_text_updated_at=case when $2 then clock_timestamp() else creation_text_updated_at end,
        creation_model_source_id=case when $5 then $6 else creation_model_source_id end,
        creation_model_upstream_id=case when $5 then $8 else creation_model_upstream_id end,
        creation_reasoning=coalesce($7,creation_reasoning), creation_updated_by=$4, creation_updated_at=clock_timestamp()
        where organization_id=$1")
        .bind(organization).bind(patch.text.is_some()).bind(patch.text.as_ref().and_then(|v| v.as_deref()))
        .bind(actor).bind(patch.model.is_some()).bind(patch.model.as_ref().and_then(|v| v.as_ref()).map(|v| &v.source_id))
        .bind(patch.reasoning).bind(patch.model.as_ref().and_then(|v| v.as_ref()).map(|v| &v.upstream_model_id)).execute(conn).await?;
    Ok(())
}

#[derive(Serialize, ToSchema)]
pub struct CommonPromptSettings {
    #[schema(required = true)]
    pub text: Option<String>,
    pub updated_by: Option<String>,
    pub updated_at: Option<DateTime<Utc>>,
    pub defaults: Vec<defaults::RuntimePromptDefaults>,
}

#[derive(Serialize, ToSchema)]
pub struct CreationAssistantSettings {
    #[schema(required = true)]
    pub text: Option<String>,
    #[schema(required = true)]
    pub model: Option<ModelOfferKey>,
    pub reasoning: bool,
    pub text_updated_by: Option<String>,
    pub text_updated_at: Option<DateTime<Utc>>,
    pub updated_by: Option<String>,
    pub updated_at: Option<DateTime<Utc>>,
    pub missing_language_placeholder: bool,
    pub defaults: Vec<defaults::RuntimePromptDefaults>,
    pub models: crate::model_catalog::instance::RuntimeModels,
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn prompt_boundaries_and_sparse_patch() {
        assert!(validate_text("", false).is_ok());
        assert!(validate_text(&"é".repeat(20000), false).is_ok());
        assert!(validate_text(&"🦀".repeat(20001), false).is_err());
        for text in [
            "\0",
            "<platform_prompt>",
            "</TOOLS>",
            "<platform_İNSTRUCTıONS >",
        ] {
            assert!(validate_text(text, false).is_err());
        }
        assert!(validate_text(" \n", true).is_err());
        assert!(validate_text("Write in {language}", true).is_ok());
        let absent: PatchCreationAssistant = serde_json::from_str("{}").unwrap();
        let reset: PatchCreationAssistant = serde_json::from_str(r#"{"text":null}"#).unwrap();
        assert!(absent.text.is_none());
        assert_eq!(reset.text, Some(None));
        assert!(serde_json::from_str::<PatchCreationAssistant>(r#"{"title_model":"x"}"#).is_err());
    }
}
