// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Administrative observations of configured pods, never execution readiness.

use std::{collections::BTreeMap, sync::OnceLock};

use anyhow::{Context, Result, ensure};
use axum::{Json, extract::State, http::StatusCode};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use sqlx::{Postgres, Transaction};

use super::{RuntimeCatalogSource, SetDefaultOnRequest, catalog, enablement};
use crate::{
    agent_instances::{self, SelectingInstance},
    api::AppState,
    domain::{Permission, Space, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};

#[derive(Default, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum PodCapabilityKind {
    #[default]
    Tool,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityFieldType {
    String,
    Text,
    #[serde(rename = "text-multiline")]
    TextMultiline,
    Number,
    Integer,
    Boolean,
    Select,
    Array,
    Object,
    Prompt,
    Secret,
    Url,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityExecutionModel {
    React,
    Graph,
}

fn default_execution_models() -> Vec<CapabilityExecutionModel> {
    vec![
        CapabilityExecutionModel::React,
        CapabilityExecutionModel::Graph,
    ]
}

/// Public declaration only. Values, endpoints, schemas and arbitrary metadata are excluded.
#[derive(Deserialize, Serialize, ToSchema)]
pub struct CapabilityFieldDescription {
    pub key: String,
    #[serde(rename = "type")]
    pub field_type: CapabilityFieldType,
    pub title: String,
    pub description: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    #[schema(nullable = false)]
    pub description_by_lang: Option<BTreeMap<String, String>>,
    #[serde(default)]
    pub required: bool,
    pub item_type: Option<CapabilityFieldType>,
    pub min: Option<f64>,
    pub max: Option<f64>,
    pub scope_private: Option<bool>,
}

#[derive(Deserialize, Serialize, ToSchema)]
pub struct PodCapabilityDescriptor {
    pub id: String,
    pub source_id: Option<String>,
    pub runtime_id: Option<String>,
    pub version: String,
    pub public_version: Option<String>,
    pub name: String,
    pub description: String,
    pub icon: String,
    #[serde(default)]
    pub kind: PodCapabilityKind,
    #[serde(default)]
    pub config_fields: Vec<CapabilityFieldDescription>,
    #[serde(default)]
    pub team_settings_fields: Vec<CapabilityFieldDescription>,
    #[serde(default = "default_execution_models")]
    pub execution_models: Vec<CapabilityExecutionModel>,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PodTemplateCapability {
    pub source_agent_id: String,
    pub capability_id: String,
    pub default_selected: bool,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PodInventory {
    complete: bool,
    capabilities: Vec<PodCapabilityDescriptor>,
    template_capabilities: Vec<PodTemplateCapability>,
}

impl PodInventory {
    fn snapshot(self, runtime_id: &str) -> Result<catalog::CatalogSnapshot> {
        ensure!(self.complete, "incomplete inventory");
        for entry in &self.capabilities {
            ensure!(
                !entry.name.trim().is_empty()
                    && !entry.description.trim().is_empty()
                    && !entry.icon.trim().is_empty(),
                "invalid capability description"
            );
            for fields in [&entry.config_fields, &entry.team_settings_fields] {
                let mut keys = std::collections::HashSet::new();
                for field in fields {
                    ensure!(
                        !field.key.trim().is_empty()
                            && !field.title.trim().is_empty()
                            && keys.insert(&field.key),
                        "invalid configuration field"
                    );
                }
            }
        }
        let snapshot = catalog::CatalogSnapshot {
            capabilities: self
                .capabilities
                .into_iter()
                .map(|entry| {
                    Ok(catalog::CapabilityOffer {
                        capability_id: entry.id.clone(),
                        version: entry.version.clone(),
                        descriptor: serde_json::to_value(entry)?,
                    })
                })
                .collect::<Result<_>>()?,
            template_capabilities: self
                .template_capabilities
                .into_iter()
                .map(|link| catalog::TemplateCapability {
                    source_agent_id: link.source_agent_id,
                    capability_id: link.capability_id,
                    default_selected: link.default_selected,
                })
                .collect(),
        };
        snapshot.validate(runtime_id)?;
        Ok(snapshot)
    }
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CatalogObservationState {
    NotObserved,
    Observed,
    Unavailable,
}

#[derive(Serialize, ToSchema)]
pub struct CapabilityInventoryOffer {
    pub runtime_id: String,
    pub capability_id: String,
    pub version: String,
    /// Present in the last successful snapshot; independent of observation state.
    pub advertised: bool,
    /// Enabled for every space of this organization.
    pub default_on: bool,
    /// Instances that select this offer and may no longer use it.
    pub unusable_instances: Vec<AffectedAgentInstance>,
    pub descriptor: PodCapabilityDescriptor,
}

/// An agent instance an offer's authorization affects, with its space for display.
#[derive(Serialize, ToSchema)]
pub struct AffectedAgentInstance {
    pub agent_instance_id: Uuid,
    pub display_name: String,
    pub space_id: Uuid,
    pub space_name: String,
    pub space_kind: SpaceKind,
    /// Display name of a personal space's owner; null for other spaces.
    #[schema(required = true)]
    pub owner_name: Option<String>,
}

impl From<&SelectingInstance> for AffectedAgentInstance {
    fn from(instance: &SelectingInstance) -> Self {
        Self {
            agent_instance_id: instance.agent_instance_id,
            display_name: instance.display_name.clone(),
            space_id: instance.space.id,
            space_name: instance.space.name.clone(),
            space_kind: instance.space.kind,
            owner_name: instance.owner_name.clone(),
        }
    }
}

#[derive(Serialize, ToSchema)]
pub struct PodCapabilityInventory {
    pub runtime_id: String,
    pub enabled: bool,
    pub observation: CatalogObservationState,
    pub checked_at: Option<DateTime<Utc>>,
    pub observed_at: Option<DateTime<Utc>>,
    pub capabilities: Vec<CapabilityInventoryOffer>,
    /// Links from the last successful snapshot, all scoped to this runtime.
    pub template_capabilities: Vec<PodTemplateCapability>,
}

/// One read-only snapshot for administration views; no lock, no network call.
async fn read_snapshot(s: &AppState) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    Ok(tx)
}

async fn read_inventory(
    s: &AppState,
    organization_id: Uuid,
) -> AppResult<Vec<PodCapabilityInventory>> {
    let mut tx = read_snapshot(s).await?;
    let policy = enablement::Policy::load(&mut *tx, organization_id).await?;
    let instances = agent_instances::selecting_in_organization(&mut *tx, organization_id).await?;
    let mut items = Vec::new();
    for source in &s.agent_catalog.runtime_catalog_sources {
        let observation = catalog::observation(&mut *tx, &source.runtime_id).await?;
        let offers = catalog::capabilities(&mut *tx, &source.runtime_id).await?;
        let links = catalog::template_capabilities(&mut *tx, &source.runtime_id).await?;
        items.push(PodCapabilityInventory {
            runtime_id: source.runtime_id.clone(),
            enabled: source.enabled,
            observation: match &observation {
                None => CatalogObservationState::NotObserved,
                Some(value) if value.reachable => CatalogObservationState::Observed,
                Some(_) => CatalogObservationState::Unavailable,
            },
            checked_at: observation.as_ref().map(|value| value.checked_at),
            observed_at: observation.and_then(|value| value.observed_at),
            capabilities: offers
                .into_iter()
                .map(|offer| {
                    Ok(CapabilityInventoryOffer {
                        default_on: policy.default_on(&offer.runtime_id, &offer.capability_id),
                        unusable_instances: instances
                            .iter()
                            .filter(|instance| {
                                instance.source_runtime_id == offer.runtime_id
                                    && instance.selected.contains(&offer.capability_id)
                                    && !enablement::usable(
                                        &policy,
                                        &instance.space,
                                        &offer.runtime_id,
                                        &offer.capability_id,
                                    )
                            })
                            .map(AffectedAgentInstance::from)
                            .collect(),
                        runtime_id: offer.runtime_id,
                        capability_id: offer.capability_id,
                        version: offer.version,
                        advertised: offer.advertised,
                        descriptor: serde_json::from_value(offer.descriptor.0)
                            .context("invalid stored capability description")?,
                    })
                })
                .collect::<Result<_>>()?,
            template_capabilities: links
                .into_iter()
                .map(|link| PodTemplateCapability {
                    source_agent_id: link.source_agent_id,
                    capability_id: link.capability_id,
                    default_selected: link.default_selected,
                })
                .collect(),
        });
    }
    tx.commit().await?;
    Ok(items)
}

async fn authorize(s: &AppState, uid: &str, organization_id: Uuid) -> AppResult<Space> {
    let org = spaces::authorize(&s.pool, &s.fga, uid, organization_id, Permission::Manage).await?;
    if org.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    Ok(org)
}

fn require_source(s: &AppState, runtime_id: &str) -> AppResult<()> {
    if s.agent_catalog
        .runtime_catalog_sources
        .iter()
        .any(|source| source.runtime_id == runtime_id)
    {
        Ok(())
    } else {
        Err(AppError::NotFound)
    }
}

/// Organization lock, Manage recheck on the locked connection, then the FGA fence.
async fn authorized_transaction(
    s: &AppState,
    uid: &str,
    org: &Space,
) -> AppResult<Transaction<'static, Postgres>> {
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, org).await?;
    spaces::authorize_locked(&mut tx, &s.fga, uid, org.id, Permission::Manage).await?;
    s.fga.fence(&mut guard).await?;
    Ok(tx)
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(organization_capabilities))
        .routes(utoipa_axum::routes!(refresh_organization_capabilities))
        .routes(utoipa_axum::routes!(set_organization_capability_default))
        .routes(utoipa_axum::routes!(organization_capability_revoke_impact))
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/capabilities",
    params(("organization_id" = Uuid, Path)),
    responses(
        (status = 200, body = [PodCapabilityInventory]),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn organization_capabilities(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
) -> AppResult<Json<Vec<PodCapabilityInventory>>> {
    authorize(&s, &user.uid, organization_id).await?;
    let inventory = read_inventory(&s, organization_id).await?;
    authorize(&s, &user.uid, organization_id).await?;
    Ok(Json(inventory))
}

async fn fetch(source: &RuntimeCatalogSource) -> AppResult<catalog::CatalogSnapshot> {
    static CLIENT: OnceLock<reqwest::Client> = OnceLock::new();
    let client = if let Some(client) = CLIENT.get() {
        client.clone()
    } else {
        let client = super::catalog_client()?;
        let _ = CLIENT.set(client.clone());
        client
    };
    let mut response = client
        .get(format!(
            "{}/agents/capabilities",
            source.base_url.trim_end_matches('/')
        ))
        .send()
        .await
        .map_err(|_| AppError::Unavailable("pod inventory unavailable".into()))?;
    if !response.status().is_success() {
        return Err(AppError::Unavailable("pod inventory unavailable".into()));
    }
    let invalid = || {
        AppError::problem(
            StatusCode::BAD_GATEWAY,
            "invalid_pod_inventory",
            "Pod returned an invalid or incomplete capability inventory.",
        )
    };
    const MAX_BYTES: usize = 2 * 1024 * 1024;
    if response
        .content_length()
        .is_some_and(|size| size > MAX_BYTES as u64)
    {
        return Err(invalid());
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| AppError::Unavailable("pod inventory unavailable".into()))?
    {
        if bytes.len() + chunk.len() > MAX_BYTES {
            return Err(invalid());
        }
        bytes.extend_from_slice(&chunk);
    }
    serde_json::from_slice::<PodInventory>(&bytes)
        .map_err(|_| invalid())?
        .snapshot(&source.runtime_id)
        .map_err(|_| invalid())
}

#[utoipa::path(
    post, path = "/organizations/{organization_id}/capabilities/{runtime_id}/refresh",
    params(("organization_id" = Uuid, Path), ("runtime_id" = String, Path)),
    responses(
        (status = 204, description = "Complete pod inventory persisted; read the catalog for observation and offers"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 502, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn refresh_organization_capabilities(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, runtime_id)): ApiPath<(Uuid, String)>,
) -> AppResult<StatusCode> {
    let org = authorize(&s, &user.uid, organization_id).await?;
    let source = s
        .agent_catalog
        .runtime_catalog_sources
        .iter()
        .find(|source| source.runtime_id == runtime_id)
        .ok_or(AppError::NotFound)?;
    if !source.enabled {
        return Err(AppError::Conflict("pod catalog source is disabled".into()));
    }
    // No SQL connection or organization lock survives the bounded pod request.
    let snapshot = fetch(source).await;
    let mut tx = authorized_transaction(&s, &user.uid, &org).await?;
    match &snapshot {
        Ok(snapshot) => catalog::replace(&mut tx, &source.runtime_id, snapshot).await?,
        Err(_) => catalog::mark_unreachable(&mut tx, &source.runtime_id).await?,
    }
    tx.commit().await?;
    snapshot?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    put, path = "/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/default-on",
    params(
        ("organization_id" = Uuid, Path),
        ("runtime_id" = String, Path),
        ("capability_id" = String, Path)
    ),
    request_body = SetDefaultOnRequest,
    responses(
        (status = 204, description = "Organization decision stored"),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, description = "Unknown organization, pod source or offer", body = crate::error::ErrorBody),
        (status = 409, description = "Enabling an offer the pod no longer advertises", body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn set_organization_capability_default(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, runtime_id, capability_id)): ApiPath<(Uuid, String, String)>,
    ApiJson(body): ApiJson<SetDefaultOnRequest>,
) -> AppResult<StatusCode> {
    let org = authorize(&s, &user.uid, organization_id).await?;
    require_source(&s, &runtime_id)?;
    let mut tx = authorized_transaction(&s, &user.uid, &org).await?;
    let changed = enablement::set_default_on(
        &mut tx,
        organization_id,
        &runtime_id,
        &capability_id,
        body.default_on,
        &user.uid,
    )
    .await?;
    tx.commit().await?;
    if changed {
        tracing::info!(target: "fred.security.audit", audit_event="capability.default_changed",
            actor_uid=%user.uid, organization_id=%organization_id, runtime_id=%runtime_id,
            capability_id=%capability_id, default_on=body.default_on,
            "Organization capability default changed");
    }
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/capabilities/{runtime_id}/{capability_id}/revoke-impact",
    params(
        ("organization_id" = Uuid, Path),
        ("runtime_id" = String, Path),
        ("capability_id" = String, Path)
    ),
    responses(
        (status = 200, description = "Instances usable now that disabling this offer would stop", body = [AffectedAgentInstance]),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, description = "Unknown organization, pod source or offer", body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn organization_capability_revoke_impact(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, runtime_id, capability_id)): ApiPath<(Uuid, String, String)>,
) -> AppResult<Json<Vec<AffectedAgentInstance>>> {
    authorize(&s, &user.uid, organization_id).await?;
    require_source(&s, &runtime_id)?;
    let mut tx = read_snapshot(&s).await?;
    if !catalog::capabilities(&mut *tx, &runtime_id)
        .await?
        .iter()
        .any(|offer| offer.capability_id == capability_id)
    {
        return Err(AppError::NotFound);
    }
    let policy = enablement::Policy::load(&mut *tx, organization_id).await?;
    let instances = agent_instances::selecting_in_organization(&mut *tx, organization_id).await?;
    tx.commit().await?;
    let revoked = policy.without(&runtime_id, &capability_id);
    let affected = instances
        .iter()
        .filter(|instance| {
            let usable_under = |policy| {
                enablement::first_unusable(
                    policy,
                    &instance.space,
                    &instance.source_runtime_id,
                    &instance.selected,
                )
                .is_none()
            };
            usable_under(&policy) && !usable_under(&revoked)
        })
        .map(AffectedAgentInstance::from)
        .collect();
    authorize(&s, &user.uid, organization_id).await?;
    Ok(Json(affected))
}
