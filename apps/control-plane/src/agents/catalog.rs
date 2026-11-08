// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Pod-scoped catalog observations. Callers resolve the configured runtime before
//! writing; this store neither grants access nor establishes execution readiness.

use std::collections::HashSet;

use anyhow::{Result, ensure};
use chrono::{DateTime, Utc};
use serde_json::Value;
use sqlx::{PgConnection, types::Json};

pub struct CapabilityOffer {
    pub capability_id: String,
    pub version: String,
    /// Public pod descriptor; identity columns, not metadata, own provenance.
    pub descriptor: Value,
}

pub struct TemplateCapability {
    pub source_agent_id: String,
    pub capability_id: String,
    pub default_selected: bool,
}

/// Complete inventory for one logical pod, including capabilities without consumers.
/// A union of template pickers is not necessarily a complete pod inventory.
pub struct CatalogSnapshot {
    pub capabilities: Vec<CapabilityOffer>,
    pub template_capabilities: Vec<TemplateCapability>,
}

#[derive(sqlx::FromRow)]
pub struct CatalogObservation {
    pub runtime_id: String,
    pub reachable: bool,
    pub checked_at: DateTime<Utc>,
    pub observed_at: Option<DateTime<Utc>>,
}

#[derive(sqlx::FromRow)]
pub struct StoredCapability {
    pub runtime_id: String,
    pub capability_id: String,
    pub version: String,
    pub descriptor: Json<Value>,
    /// False means absent from the last successful inventory, not an access denial.
    pub advertised: bool,
}

#[derive(sqlx::FromRow)]
pub struct StoredTemplateCapability {
    pub runtime_id: String,
    pub source_agent_id: String,
    pub capability_id: String,
    pub default_selected: bool,
}

fn valid_key(value: &str) -> bool {
    !value.is_empty() && value.trim() == value
}

impl CatalogSnapshot {
    pub(super) fn validate(&self, runtime_id: &str) -> Result<()> {
        ensure!(valid_key(runtime_id), "invalid catalog runtime identity");
        let mut ids = HashSet::new();
        for offer in &self.capabilities {
            ensure!(
                valid_key(&offer.capability_id) && valid_key(&offer.version),
                "invalid capability identity or version"
            );
            ensure!(
                ids.insert(offer.capability_id.as_str()),
                "duplicate capability offering"
            );
            ensure!(
                offer.descriptor.is_object(),
                "capability descriptor must be an object"
            );
            // The existing pod wire descriptor repeats these optional identity fields.
            for (key, expected) in [
                ("id", offer.capability_id.as_str()),
                ("source_id", offer.capability_id.as_str()),
                ("version", offer.version.as_str()),
                ("runtime_id", runtime_id),
            ] {
                if let Some(value) = offer.descriptor.get(key).filter(|value| !value.is_null()) {
                    ensure!(
                        value.as_str() == Some(expected),
                        "conflicting capability provenance"
                    );
                }
            }
        }
        let mut links = HashSet::new();
        for link in &self.template_capabilities {
            ensure!(
                valid_key(&link.source_agent_id),
                "invalid template identity"
            );
            ensure!(
                ids.contains(link.capability_id.as_str()),
                "template capability absent from owning pod"
            );
            ensure!(
                links.insert((link.source_agent_id.as_str(), link.capability_id.as_str())),
                "duplicate template capability"
            );
        }
        Ok(())
    }
}

/// Persist only a complete successful observation. Fetch and normalize outside SQL.
/// Caller owns the transaction; the runtime row serializes replacements within it.
pub async fn replace(
    conn: &mut PgConnection,
    runtime_id: &str,
    snapshot: &CatalogSnapshot,
) -> Result<()> {
    snapshot.validate(runtime_id)?;
    sqlx::query(
        "insert into runtime_catalog (runtime_id, reachable, observed_at)
         values ($1, true, clock_timestamp())
         on conflict (runtime_id) do update set reachable = true,
             checked_at = clock_timestamp(), observed_at = clock_timestamp()",
    )
    .bind(runtime_id)
    .execute(&mut *conn)
    .await?;
    sqlx::query("delete from runtime_template_capability where runtime_id = $1")
        .bind(runtime_id)
        .execute(&mut *conn)
        .await?;
    sqlx::query("update runtime_capability set advertised = false where runtime_id = $1")
        .bind(runtime_id)
        .execute(&mut *conn)
        .await?;
    for offer in &snapshot.capabilities {
        sqlx::query(
            "insert into runtime_capability (runtime_id, capability_id, version, descriptor, advertised)
             values ($1, $2, $3, $4, true)
             on conflict (runtime_id, capability_id) do update set
                 version = excluded.version, descriptor = excluded.descriptor, advertised = true",
        )
        .bind(runtime_id)
        .bind(&offer.capability_id)
        .bind(&offer.version)
        .bind(Json(&offer.descriptor))
        .execute(&mut *conn)
        .await?;
    }
    for link in &snapshot.template_capabilities {
        sqlx::query(
            "insert into runtime_template_capability
                 (runtime_id, source_agent_id, capability_id, default_selected)
             values ($1, $2, $3, $4)",
        )
        .bind(runtime_id)
        .bind(&link.source_agent_id)
        .bind(&link.capability_id)
        .bind(link.default_selected)
        .execute(&mut *conn)
        .await?;
    }
    Ok(())
}

/// Retain the last successful inventory on discovery failure, including first contact.
pub async fn mark_unreachable(conn: &mut PgConnection, runtime_id: &str) -> Result<()> {
    ensure!(valid_key(runtime_id), "invalid catalog runtime identity");
    sqlx::query(
        "insert into runtime_catalog (runtime_id, reachable) values ($1, false)
         on conflict (runtime_id) do update set reachable = false, checked_at = clock_timestamp()",
    )
    .bind(runtime_id)
    .execute(conn)
    .await?;
    Ok(())
}

pub async fn observation<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    runtime_id: &str,
) -> sqlx::Result<Option<CatalogObservation>> {
    sqlx::query_as(
        "select runtime_id, reachable, checked_at, observed_at from runtime_catalog where runtime_id = $1",
    )
    .bind(runtime_id)
    .fetch_optional(ex)
    .await
}

/// Includes withdrawn entries so saved configurations can identify missing offers.
pub async fn capabilities<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    runtime_id: &str,
) -> sqlx::Result<Vec<StoredCapability>> {
    sqlx::query_as(
        "select runtime_id, capability_id, version, descriptor, advertised
         from runtime_capability where runtime_id = $1 order by capability_id",
    )
    .bind(runtime_id)
    .fetch_all(ex)
    .await
}

pub async fn template_capabilities<'e>(
    ex: impl sqlx::PgExecutor<'e>,
    runtime_id: &str,
) -> sqlx::Result<Vec<StoredTemplateCapability>> {
    sqlx::query_as(
        "select runtime_id, source_agent_id, capability_id, default_selected
         from runtime_template_capability where runtime_id = $1 order by source_agent_id, capability_id",
    )
    .bind(runtime_id)
    .fetch_all(ex)
    .await
}
