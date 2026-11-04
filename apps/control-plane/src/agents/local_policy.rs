// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Local ceilings on pod offers. Direct space owners manage only their own row;
//! the same decision applies to tools and instruction skills at admission.

use super::{
    catalog, enablement,
    inventory::{self, PodCapabilityDescriptor},
};
use crate::{
    api::AppState,
    authorization,
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};
use anyhow::Context;
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::PgConnection;
use std::collections::BTreeSet;
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Serialize, ToSchema)]
pub struct LocalOffer {
    pub capability_id: String,
    pub descriptor: PodCapabilityDescriptor,
    pub advertised: bool,
    pub parent_permitted: bool,
    pub permitted: bool,
}

#[derive(Serialize, ToSchema)]
pub struct SpaceCapabilityPolicy {
    pub runtime_id: String,
    pub revision: i64,
    pub restricted: bool,
    pub permitted_ids: Vec<String>,
    pub source_enabled: bool,
    pub reachable: bool,
    pub skills_supported: bool,
    pub skills_availability: Option<String>,
    pub offers: Vec<LocalOffer>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ReplaceSpaceCapabilityPolicy {
    pub expected_revision: i64,
    pub restricted: bool,
    #[schema(max_items = 4096)]
    pub permitted_ids: Vec<String>,
}

fn require_local(kind: SpaceKind) -> AppResult<()> {
    if matches!(kind, SpaceKind::Team | SpaceKind::Project) {
        Ok(())
    } else {
        Err(AppError::Unprocessable(
            "Local offer restrictions require a team or project.".into(),
        ))
    }
}

async fn stored(
    conn: &mut PgConnection,
    space: Uuid,
    runtime: &str,
) -> AppResult<(i64, bool, Vec<String>)> {
    let row: Option<(i64, bool)> = sqlx::query_as("select revision, restricted from space_capability_policy where space_id=$1 and runtime_id=$2")
        .bind(space).bind(runtime).fetch_optional(&mut *conn).await?;
    let ids = sqlx::query_scalar("select capability_id from space_capability_permission where space_id=$1 and runtime_id=$2 order by capability_id")
        .bind(space).bind(runtime).fetch_all(conn).await?;
    let (revision, restricted) = row.unwrap_or((0, false));
    Ok((revision, restricted, ids))
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(
        space_capability_policies,
        replace_space_capability_policy
    ))
}

#[utoipa::path(get, path="/spaces/{space_id}/capability-policies", params(("space_id"=Uuid, Path)), responses((status=200, body=[SpaceCapabilityPolicy]), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn space_capability_policies(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Vec<SpaceCapabilityPolicy>>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, &user.uid, id, Permission::Manage).await?;
    require_local(space.kind)?;
    let policy = enablement::Policy::load_for_space(&mut *tx, &space).await?;
    let mut parent = space.clone();
    parent.path.pop();
    let mut result = Vec::new();
    for source in &s.agent_catalog.runtime_catalog_sources {
        let (revision, restricted, permitted_ids) = stored(&mut tx, id, &source.runtime_id).await?;
        let observation = catalog::observation(&mut *tx, &source.runtime_id).await?;
        let mut offers = Vec::new();
        for offer in catalog::capabilities(&mut *tx, &source.runtime_id).await? {
            offers.push(LocalOffer {
                parent_permitted: enablement::usable(
                    &policy,
                    &parent,
                    &source.runtime_id,
                    &offer.capability_id,
                ),
                permitted: enablement::usable(
                    &policy,
                    &space,
                    &source.runtime_id,
                    &offer.capability_id,
                ),
                capability_id: offer.capability_id,
                advertised: offer.advertised,
                descriptor: serde_json::from_value(offer.descriptor.0)
                    .context("invalid stored offer description")?,
            });
        }
        result.push(SpaceCapabilityPolicy {
            runtime_id: source.runtime_id.clone(),
            revision,
            restricted,
            permitted_ids,
            source_enabled: source.enabled,
            reachable: observation.as_ref().is_some_and(|v| v.reachable),
            skills_supported: observation
                .as_ref()
                .is_some_and(|v| v.skills_availability.is_some()),
            skills_availability: observation.and_then(|v| v.skills_availability),
            offers,
        });
    }
    tx.commit().await?;
    Ok(Json(result))
}

#[utoipa::path(put, path="/spaces/{space_id}/capability-policies/{runtime_id}", params(("space_id"=Uuid, Path), ("runtime_id"=String, Path)), request_body=ReplaceSpaceCapabilityPolicy, responses((status=204), (status=403, body=crate::error::ErrorBody), (status=404, body=crate::error::ErrorBody), (status=409, body=crate::error::ErrorBody), (status=422, body=crate::error::ErrorBody)))]
async fn replace_space_capability_policy(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((id, runtime)): ApiPath<(Uuid, String)>,
    ApiJson(body): ApiJson<ReplaceSpaceCapabilityPolicy>,
) -> AppResult<StatusCode> {
    let ids: BTreeSet<_> = body.permitted_ids.iter().collect();
    if body.expected_revision < 0
        || ids.len() != body.permitted_ids.len()
        || ids.len() > 4096
        || (!body.restricted && !ids.is_empty())
    {
        return Err(AppError::Unprocessable(
            "Invalid local offer policy.".into(),
        ));
    }
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, id, Permission::Manage).await?;
    require_local(space.kind)?;
    inventory::require_source(&s, &runtime)?;
    if catalog::observation(&mut *tx, &runtime).await?.is_none() {
        return Err(AppError::Conflict(
            "The pod inventory has not been observed.".into(),
        ));
    }
    let (revision, _, previous) = stored(&mut tx, id, &runtime).await?;
    if revision != body.expected_revision {
        return Err(AppError::Conflict(
            "The offer policy changed; refresh before saving.".into(),
        ));
    }
    // Keep discovery stable through the write. No network call under this lock.
    let offers: Vec<(String, bool)> = sqlx::query_as(
        "select capability_id, advertised from runtime_capability where runtime_id=$1 for share",
    )
    .bind(&runtime)
    .fetch_all(&mut *tx)
    .await?;
    for id in &ids {
        let advertised = offers
            .iter()
            .find(|(key, _)| key == *id)
            .map(|(_, advertised)| *advertised)
            .ok_or_else(|| AppError::Unprocessable("Unknown pod offer.".into()))?;
        if !advertised && !previous.contains(id) {
            return Err(AppError::Conflict(
                "A withdrawn offer cannot be newly selected.".into(),
            ));
        }
    }
    sqlx::query("insert into space_capability_policy(space_id,runtime_id,revision,restricted,updated_by) values($1,$2,1,$3,$4) on conflict(space_id,runtime_id) do update set revision=space_capability_policy.revision+1, restricted=excluded.restricted, updated_by=excluded.updated_by, updated_at=clock_timestamp()")
        .bind(id).bind(&runtime).bind(body.restricted).bind(&user.uid).execute(&mut *tx).await?;
    sqlx::query("delete from space_capability_permission where space_id=$1 and runtime_id=$2")
        .bind(id)
        .bind(&runtime)
        .execute(&mut *tx)
        .await?;
    sqlx::query("insert into space_capability_permission(space_id,runtime_id,capability_id) select $1,$2,unnest($3::text[])")
        .bind(id).bind(&runtime).bind(&body.permitted_ids).execute(&mut *tx).await?;
    tx.commit().await?;
    tracing::info!(target:"fred.security.audit", audit_event="capability.local_policy_changed", actor_uid=%user.uid, space_id=%id, runtime_id=%runtime, revision=revision+1);
    Ok(StatusCode::NO_CONTENT)
}
