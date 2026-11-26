// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! A single revocable team link. Redemption uses the normal direct-role storage
//! and platform/organization lock order, with no rights on sibling or child spaces.
use axum::{Json, extract::State, http::StatusCode};
use chrono::{DateTime, Utc};
use serde::Serialize;
use sqlx::PgPool;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization, bootstrap,
    domain::{Role, Space, SpaceKind},
    error::{AppError, AppResult, ErrorBody},
    extract::ApiPath,
    onboarding::AdmittedUser,
    roles::SpacePermission,
    spaces,
};

#[derive(Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct TeamJoinLink {
    pub token: Uuid,
    pub expires_at: DateTime<Utc>,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct TeamJoinPreview {
    pub team_id: Uuid,
    pub team_name: String,
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(
            team_join_link,
            create_team_join_link,
            revoke_team_join_link
        ))
        .routes(routes!(preview_team_join_link, redeem_team_join_link))
}

fn require_team(space: &Space) -> AppResult<()> {
    if space.kind != SpaceKind::Team {
        return Err(AppError::NotFound);
    }
    Ok(())
}

#[utoipa::path(get, path="/spaces/{id}/join-link", params(("id"=Uuid, Path)),
 responses((status=200, body=Option<TeamJoinLink>), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn team_join_link(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Option<TeamJoinLink>>> {
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, id, SpacePermission::Manage).await?;
    require_team(&space)?;
    let row: Option<(Uuid, DateTime<Utc>, String)> = sqlx::query_as(
        "select token,expires_at,created_by from team_join_link where space_id=$1 and expires_at>clock_timestamp()",
    )
    .bind(id)
    .fetch_optional(&mut *tx)
    .await?;
    let link = if let Some((token, expires_at, issuer)) = row {
        match authorization::authorize(&mut *tx, &issuer, id, SpacePermission::Manage).await {
            Ok(_) => Some(TeamJoinLink { token, expires_at }),
            // Offer creation again instead of copying a former owner's unusable link.
            Err(AppError::Forbidden | AppError::NotFound) => None,
            Err(error) => return Err(error),
        }
    } else {
        None
    };
    tx.commit().await?;
    Ok(Json(link))
}

/// Rotation invalidates the previous token atomically. No durable raw URL is logged.
pub async fn create(pool: &PgPool, caller: &str, id: Uuid) -> AppResult<TeamJoinLink> {
    let (mut tx, space) =
        spaces::governance_mutation(pool, caller, id, SpacePermission::Manage).await?;
    require_team(&space)?;
    let link = sqlx::query_as("insert into team_join_link(space_id,token,created_by,expires_at) values($1,$2,$3,now()+interval '7 days') on conflict(space_id) do update set token=excluded.token, created_by=excluded.created_by, created_at=now(), expires_at=excluded.expires_at returning token,expires_at")
        .bind(id).bind(Uuid::new_v4()).bind(caller).fetch_one(&mut *tx).await?;
    tx.commit().await?;
    Ok(link)
}

#[utoipa::path(post, path="/spaces/{id}/join-link", params(("id"=Uuid, Path)),
 responses((status=200, body=TeamJoinLink), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn create_team_join_link(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<TeamJoinLink>> {
    Ok(Json(create(&s.pool, &user.uid, id).await?))
}

#[utoipa::path(delete, path="/spaces/{id}/join-link", params(("id"=Uuid, Path)),
 responses((status=204), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn revoke_team_join_link(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    let (mut tx, space) =
        spaces::governance_mutation(&s.pool, &user.uid, id, SpacePermission::Manage).await?;
    require_team(&space)?;
    sqlx::query("delete from team_join_link where space_id=$1")
        .bind(id)
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Preview and redemption apply the same policy. Re-read after the organization
/// lock, so rotation, expiration, retirement and role revocation cannot race entry.
pub async fn join(
    pool: &PgPool,
    caller: &str,
    token: Uuid,
    redeem: bool,
) -> AppResult<TeamJoinPreview> {
    let id: Uuid = sqlx::query_scalar("select space_id from team_join_link where token=$1")
        .bind(token)
        .fetch_optional(pool)
        .await?
        .ok_or(AppError::NotFound)?;
    let space = spaces::load(pool, id).await?;
    let mut tx = bootstrap::locked(pool).await?;
    spaces::lock_organization(&mut tx, &space).await?;
    let issuer: String = sqlx::query_scalar("select created_by from team_join_link where space_id=$1 and token=$2 and expires_at>clock_timestamp()")
        .bind(id).bind(token).fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    // A former owner's link cannot keep granting access on that owner's behalf.
    let space = authorization::authorize(&mut *tx, &issuer, id, SpacePermission::Manage).await?;
    require_team(&space)?;
    authorization::authorize(&mut *tx, caller, space.organization, SpacePermission::Read).await?;
    let audit = if redeem {
        authorization::write_role(&mut tx, Some(&issuer), caller, Role::Member, id, true).await?
    } else {
        authorization::RoleAudit::default()
    };
    tx.commit().await?;
    audit.emit();
    Ok(TeamJoinPreview {
        team_id: id,
        team_name: space.name,
    })
}

#[utoipa::path(get, path="/team-join-links/{token}", params(("token"=Uuid, Path)),
 responses((status=200, body=TeamJoinPreview), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn preview_team_join_link(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(token): ApiPath<Uuid>,
) -> AppResult<Json<TeamJoinPreview>> {
    Ok(Json(join(&s.pool, &user.uid, token, false).await?))
}

#[utoipa::path(post, path="/team-join-links/{token}", params(("token"=Uuid, Path)),
 responses((status=200, body=TeamJoinPreview), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn redeem_team_join_link(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(token): ApiPath<Uuid>,
) -> AppResult<Json<TeamJoinPreview>> {
    Ok(Json(join(&s.pool, &user.uid, token, true).await?))
}
