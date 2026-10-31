// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Manager-owned processing admission and results; computation belongs to KF workers.
pub mod cleanup;
pub mod config;
pub mod dispatch;
pub mod http;
pub mod models;
pub mod preview;
pub mod publication;
pub mod retrievable;
pub mod store;
pub mod worker_contract;

use crate::{
    auth::Authenticator,
    authorization::Authorization,
    documents::{Storage, object_store::ObjectStore},
    error::AppError,
};
use std::sync::Arc;
use uuid::Uuid;
pub struct Processing {
    pub pool: sqlx::PgPool,
    pub authorization: Authorization,
    pub terms: Option<String>,
    pub installation: Uuid,
    pub config: config::ProcessingConfig,
    pub auth: Authenticator,
    pub originals: Arc<Storage>,
    pub derived: ObjectStore,
    pub contract: worker_contract::WorkerContract,
}
pub fn conflict(code: &'static str) -> AppError {
    AppError::problem(
        axum::http::StatusCode::CONFLICT,
        code,
        "Document processing state changed; refresh its status",
    )
}
pub fn unavailable() -> AppError {
    AppError::problem(
        axum::http::StatusCode::SERVICE_UNAVAILABLE,
        "processing_unavailable",
        "Document processing is unavailable",
    )
}
pub fn capacity() -> AppError {
    AppError::problem(
        axum::http::StatusCode::TOO_MANY_REQUESTS,
        "processing_capacity",
        "Document processing capacity is exhausted",
    )
}

impl Processing {
    pub async fn configured(
        config: config::ProcessingConfig,
        originals: Arc<Storage>,
        mut security: crate::auth::SecuritySettings,
    ) -> anyhow::Result<Arc<Self>> {
        use anyhow::{Context, ensure};
        config.validate(&originals.config)?;
        let contract = worker_contract::WorkerContract::load(
            &config.worker_contract_file,
            &config.temporal.task_queue,
        )?;
        security.enabled = true;
        security.realm_url = config.worker.issuer.clone();
        security.audience = Some(config.worker.audience.clone());
        security.m2m_realm_url = None;
        security.jwks_url = None;
        security.provider = crate::auth::Provider::Keycloak;
        security.claims = Default::default();
        let auth = Authenticator::start(security).await?;
        let derived = ObjectStore::new(
            &config.derived,
            std::env::var(&config.derived.access_key_env_var)
                .context("missing processing storage access key")?,
            std::env::var(&config.derived.secret_key_env_var)
                .context("missing processing storage secret key")?,
        )?;
        // Availability is checked on processing admission, independently of original reads.
        let pool = originals.pool.clone();
        sqlx::query("update document_storage set derived_endpoint=$1,derived_bucket=$2,derived_prefix=$3 where singleton and derived_endpoint is null")
            .bind(&config.derived.endpoint).bind(&config.derived.bucket).bind(&config.derived.prefix).execute(&pool).await?;
        let (installation,endpoint,bucket,prefix):(Uuid,String,String,String)=sqlx::query_as("select namespace,derived_endpoint,derived_bucket,derived_prefix from document_storage where singleton").fetch_one(&pool).await?;
        ensure!(
            endpoint == config.derived.endpoint
                && bucket == config.derived.bucket
                && prefix == config.derived.prefix,
            "processing storage does not match the database installation"
        );
        Ok(Arc::new(Self {
            pool,
            authorization: originals.authorization.clone(),
            terms: originals.terms.clone(),
            installation,
            config,
            auth,
            originals,
            derived,
            contract,
        }))
    }
}
