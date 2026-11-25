// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Platform observations, explicit organization assignments and model policy.
//! Deployment adds sources and seeds policies once; admissions read current SQL facts.

mod access;
pub mod config;
mod discovery;
pub(crate) mod http;
pub mod initialization;
pub(crate) mod instance;
mod local_policy;
mod metadata;
mod policy;
pub(crate) mod sources;
mod store;

pub use discovery::{ChatProvenance, DiscoveryFailure, ModelMetadata};
pub use store::{
    ModelInventory, ModelObservation, RefreshResult, StoredModelOffer, configure_sources,
    inventory, refresh,
};

/// Trusted operator assignment using deployment credentials, not browser authority.
/// Affects only source visibility: no discovery, policy change or initialization receipt.
pub async fn assign_source(
    pool: &sqlx::PgPool,
    organization: uuid::Uuid,
    source_id: &str,
) -> crate::error::AppResult<()> {
    let mut tx = pool.begin().await?;
    crate::spaces::lock_organization_id(&mut tx, organization).await?;
    crate::spaces::load_organization(&mut *tx, organization).await?;
    crate::lifecycle::store::require_active(&mut *tx, organization).await?;
    policy::assign_sources(&mut tx, organization, &[source_id.to_owned()]).await?;
    tx.commit().await?;
    Ok(())
}
