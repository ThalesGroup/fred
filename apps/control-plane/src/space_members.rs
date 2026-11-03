// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Team/project governance reads; mutations remain owned by spaces::grant/revoke.
use axum::{Json, extract::State};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::{AppState, organization_directory},
    authorization,
    domain::{Role, SpaceKind},
    error::{AppError, AppResult, ErrorBody},
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    roles::SpacePermission,
    users::{Directory, UserSummary},
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Page {
    after: Option<String>,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct SpaceMember {
    pub user: UserSummary,
    /// Roles on the managed space, also for candidates from its parent.
    pub roles: Vec<Role>,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct SpaceMembers {
    pub items: Vec<SpaceMember>,
    #[schema(required = true)]
    pub next_cursor: Option<String>,
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(space_members))
        .routes(routes!(space_member_candidates))
}

/// One snapshot for grants and eligibility. Release SQL before consulting the
/// identity directory, then recheck authority before returning its display data.
pub async fn list(
    pool: &PgPool,
    directory: &Directory<'_>,
    caller: &str,
    id: Uuid,
    after: Option<&str>,
    candidates: bool,
) -> AppResult<SpaceMembers> {
    if after.is_some_and(|value| !crate::domain::valid_subject(value)) {
        return Err(AppError::Unprocessable("invalid membership cursor".into()));
    }
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, caller, id, SpacePermission::Manage).await?;
    if !matches!(space.kind, SpaceKind::Team | SpaceKind::Project) {
        return Err(AppError::Unprocessable("team or project required".into()));
    }
    let mut subjects: Vec<String> = if candidates {
        sqlx::query_scalar("select distinct subject from space_role_grant where space_id=$1 and role=any($2) and ($3::text is null or subject>$3) order by subject limit 51")
            .bind(space.parent_id)
            .bind(authorization::roles_granting(SpacePermission::Read))
            .bind(after).fetch_all(&mut *tx).await?
    } else {
        sqlx::query_scalar("select distinct subject from space_role_grant where space_id=$1 and ($2::text is null or subject>$2) order by subject limit 51")
            .bind(id).bind(after).fetch_all(&mut *tx).await?
    };
    let more = subjects.len() > 50;
    subjects.truncate(50);
    let next_cursor = more.then(|| subjects.last().cloned()).flatten();
    let rows: Vec<(String, String)> = sqlx::query_as(
        "select subject, role from space_role_grant where space_id=$1 and subject=any($2) order by subject, role"
    ).bind(id).bind(&subjects).fetch_all(&mut *tx).await?;
    tx.commit().await?;
    let users = tokio::time::timeout(
        std::time::Duration::from_secs(15),
        directory.summaries(&subjects),
    )
    .await
    .map_err(|_| AppError::Unavailable("identity directory timeout".into()))??;
    authorization::authorize(pool, caller, id, SpacePermission::Manage).await?;
    let items = users
        .into_iter()
        .map(|user| {
            let roles = rows
                .iter()
                .filter(|(subject, _)| *subject == user.id)
                .filter_map(|(_, role)| Role::parse(role))
                .collect();
            SpaceMember { user, roles }
        })
        .collect();
    Ok(SpaceMembers { items, next_cursor })
}

#[utoipa::path(
    get, path = "/spaces/{id}/members",
    params(("id" = Uuid, Path), ("after" = Option<String>, Query)),
    responses((status = 200, body = SpaceMembers), (status = 401, body = ErrorBody),
        (status = 403, body = ErrorBody), (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody), (status = 422, body = ErrorBody), (status = 503, body = ErrorBody))
)]
async fn space_members(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(page): ApiQuery<Page>,
) -> AppResult<Json<SpaceMembers>> {
    Ok(Json(
        list(
            &s.pool,
            &organization_directory(&s)?,
            &user.uid,
            id,
            page.after.as_deref(),
            false,
        )
        .await?,
    ))
}

#[utoipa::path(
    get, path = "/spaces/{id}/member-candidates",
    params(("id" = Uuid, Path), ("after" = Option<String>, Query)),
    responses((status = 200, body = SpaceMembers), (status = 401, body = ErrorBody),
        (status = 403, body = ErrorBody), (status = 404, body = ErrorBody),
        (status = 409, body = ErrorBody), (status = 422, body = ErrorBody), (status = 503, body = ErrorBody))
)]
async fn space_member_candidates(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiQuery(page): ApiQuery<Page>,
) -> AppResult<Json<SpaceMembers>> {
    Ok(Json(
        list(
            &s.pool,
            &organization_directory(&s)?,
            &user.uid,
            id,
            page.after.as_deref(),
            true,
        )
        .await?,
    ))
}
