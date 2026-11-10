// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Deployment input only. SQL owns assignments and decisions after initialization.

use std::{collections::BTreeSet, time::Duration};

use anyhow::{Result, ensure};
use serde::Deserialize;
use sqlx::PgPool;
use utoipa::ToSchema;
use uuid::Uuid;

use super::{
    config::bounded_text,
    policy::{self, ModelOfferKey, ReplaceModelPolicy},
    store,
};
use crate::{agents::PlatformConfig, db, error::AppError, spaces};

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct OrganizationModels {
    /// Exact existing organization name, resolved using the provisioning SQL lookup.
    pub organization: String,
    #[schema(max_items = 64)]
    pub sources: Vec<String>,
    #[schema(max_items = 4096)]
    pub permitted: Vec<ModelOfferKey>,
    #[serde(default)]
    #[schema(max_items = 4096)]
    pub reasoning_enabled: Vec<ModelOfferKey>,
    pub default: Option<ModelOfferKey>,
    pub fallback: Option<ModelOfferKey>,
    /// Embedding model of the organization's documents, within its permitted offers.
    #[serde(default)]
    pub embedding: Option<ModelOfferKey>,
    /// Optional model describing document images, within its permitted chat offers.
    #[serde(default)]
    pub vision: Option<ModelOfferKey>,
}

impl OrganizationModels {
    fn policy(&self) -> ReplaceModelPolicy {
        ReplaceModelPolicy {
            title: None,
            expected_revision: 0,
            permitted: self.permitted.clone(),
            reasoning_enabled: self.reasoning_enabled.clone(),
            default: self.default.clone(),
            fallback: self.fallback.clone(),
            embedding: self.embedding.clone(),
            vision: self.vision.clone(),
        }
    }
}

pub fn validate(declarations: &[OrganizationModels]) -> Result<()> {
    ensure!(
        declarations.len() <= 64,
        "too many model organization declarations"
    );
    let mut organizations = BTreeSet::new();
    for declaration in declarations {
        ensure!(
            bounded_text(&declaration.organization, 256)
                && organizations.insert(&declaration.organization),
            "invalid or duplicate model organization name"
        );
        let sources: BTreeSet<_> = declaration.sources.iter().collect();
        ensure!(
            sources.len() == declaration.sources.len()
                && sources.len() <= 64
                && sources.iter().all(|s| bounded_text(s, 64)
                    && s.starts_with(|c: char| c.is_ascii_alphanumeric())
                    && s.bytes()
                        .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))),
            "invalid or duplicate organization model sources"
        );
        let permitted = declaration.policy().validate()?;
        ensure!(
            permitted.iter().all(|k| sources.contains(&k.source_id)),
            "initial model permissions require an explicitly assigned source"
        );
    }
    Ok(())
}

/// One bounded pass, after platform approvals and organization provisioning.
/// Startup/provisioning can defer organizations not created yet; the operator CLI
/// requires every declared organization. No polling and no implicit creation.
pub async fn initialize(pool: &PgPool, platform: &PlatformConfig, require_all: bool) -> Result<()> {
    validate(&platform.organization_models)?;
    tokio::time::timeout(Duration::from_secs(120), async {
        let mut resolved = Vec::new();
        for (index, declaration) in platform.organization_models.iter().enumerate() {
            let org = db::organization_named(pool, &declaration.organization).await
                .map_err(|_| failure(index, "organization_lookup_failed"))?;
            match org {
                Some(org) => resolved.push((index, org.id, declaration)),
                None if require_all => return Err(failure(index, "organization_missing: provision the exact organization name first")),
                None => tracing::warn!(declaration_index = index,
                    "Model initialization deferred: organization missing; provisioning will retry"),
            }
        }
        for (index, organization, declaration) in resolved {
            initialize_one(pool, platform, organization, declaration).await
                .map_err(|error| failure(index, reason(&error)))?;
        }
        // A migration never guesses historical mappings, including undeclared organizations.
        let missing: bool = sqlx::query_scalar(
            "select exists(select 1 from organization_model_permission p
             where not exists(select 1 from organization_model_source a
                 where (a.organization_id, a.source_id) = (p.organization_id, p.source_id)))",
        ).fetch_one(pool).await.map_err(|_| failure(0, "historical_mapping_check_failed"))?;
        ensure!(!missing, "model_source_assignment_missing: historical permissions are retained but denied; declare every organization's exact source mapping and replay initialize-models");
        Ok(())
    }).await.map_err(|_| anyhow::anyhow!("model_initialization_timeout: replay initialize-models; completed organizations are preserved"))?
}

fn failure(index: usize, reason: &str) -> anyhow::Error {
    anyhow::anyhow!(
        "organization_models[{index}]: {reason}; organization provisioning may already be committed; correct the declaration or dependency and replay initialize-models"
    )
}

fn reason(error: &AppError) -> &str {
    match error {
        AppError::Problem { code, .. } => code,
        AppError::Unprocessable(_) => "invalid_model_policy_or_reasoning",
        AppError::NotFound => "organization_missing_or_retired",
        _ => "model_initialization_database_unavailable",
    }
}

async fn initialize_one(
    pool: &PgPool,
    platform: &PlatformConfig,
    organization: Uuid,
    declaration: &OrganizationModels,
) -> Result<(), AppError> {
    let receipt: Option<Option<chrono::DateTime<chrono::Utc>>> = sqlx::query_scalar(
        "select completed_at from organization_model_initialization where organization_id = $1",
    )
    .bind(organization)
    .fetch_optional(pool)
    .await?;
    if receipt.as_ref().is_some_and(Option::is_some) {
        return Ok(());
    }
    // A retained receipt means a policy has already been administered, even if deleted.
    // Discovery is only necessary for a new policy; it grants nothing by itself.
    if receipt.is_none() {
        let needed: BTreeSet<_> = declaration.permitted.iter().map(|k| &k.source_id).collect();
        for id in needed {
            let source = platform
                .model_sources
                .iter()
                .find(|s| &s.source_id == id)
                .ok_or_else(|| problem("model_source_configuration_missing"))?;
            let outcome = store::refresh(pool, source)
                .await
                .map_err(|_| problem("model_source_refresh_failed"))?;
            match outcome {
                store::RefreshResult::Published => (),
                store::RefreshResult::Superseded => {
                    return Err(problem("model_refresh_superseded"));
                }
                store::RefreshResult::Failed(_) => return Err(problem("model_discovery_failed")),
            }
        }
    }
    apply(pool, organization, declaration).await
}

fn problem(code: &'static str) -> AppError {
    AppError::problem(axum::http::StatusCode::CONFLICT, code, code)
}

/// Format-independent publication: shared organization lock and policy validation.
/// All source assignments, initial decisions and completion commit together.
async fn apply(
    pool: &PgPool,
    organization: Uuid,
    declaration: &OrganizationModels,
) -> Result<(), AppError> {
    let mut tx = pool.begin().await?;
    spaces::lock_organization_id(&mut tx, organization).await?;
    let org = spaces::load_organization(&mut *tx, organization).await?;
    crate::lifecycle::store::require_active(&mut *tx, organization).await?;
    if org.name != declaration.organization {
        return Err(AppError::NotFound);
    }
    policy::initialize(
        &mut tx,
        organization,
        &declaration.sources,
        declaration.policy(),
    )
    .await?;
    tx.commit().await?;
    Ok(())
}
