// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space roster reads and person removal; mutations remain owned by `spaces`.
use axum::{Json, extract::State, http::StatusCode};
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
    search: Option<String>,
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
        .routes(routes!(remove_space_member))
}

/// Ends a person's membership with all their roles on the space. Leaving a team or
/// project is self-service; otherwise the caller needs authority over each removed
/// role. 409 while the person holds roles in dependent spaces or is the last owner/admin.
#[utoipa::path(delete, path="/spaces/{id}/members/{user}", params(("id"=Uuid, Path), ("user"=String, Path)),
 responses((status=204), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=503, body=ErrorBody)))]
async fn remove_space_member(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((id, target)): ApiPath<(Uuid, String)>,
) -> AppResult<StatusCode> {
    crate::spaces::remove_member(&s.pool, &user.uid, id, &target).await?;
    Ok(StatusCode::NO_CONTENT)
}

/// Search the scoped roster, not the global directory's first results. Pages may
/// be sparse; the cursor always permits continuing beyond this bounded scan.
async fn search(
    pool: &PgPool,
    directory: &Directory<'_>,
    caller: &str,
    id: Uuid,
    page: &Page,
    candidates: bool,
) -> AppResult<SpaceMembers> {
    let query = page
        .search
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_lowercase();
    if query.chars().count() > 180 {
        return Err(AppError::Unprocessable("search is too long".into()));
    }
    let space = authorize_roster(&mut *pool.acquire().await?, caller, id, candidates).await?;
    if candidates && space.kind == SpaceKind::Organization {
        let users = directory.search(&query).await?;
        authorize_roster(&mut *pool.acquire().await?, caller, id, candidates).await?;
        let subjects: Vec<_> = users.iter().map(|u| u.id.clone()).collect();
        let roles: Vec<(String, String)> = sqlx::query_as(
            "select subject,role from space_role_grant where space_id=$1 and subject=any($2)",
        )
        .bind(id)
        .bind(&subjects)
        .fetch_all(pool)
        .await?;
        return Ok(SpaceMembers {
            items: users
                .into_iter()
                .map(|user| {
                    let own_roles = roles
                        .iter()
                        .filter(|(subject, _)| subject == &user.id)
                        .filter_map(|(_, r)| Role::parse(r))
                        .collect();
                    SpaceMember {
                        user,
                        roles: own_roles,
                    }
                })
                .collect(),
            next_cursor: None,
        });
    }
    let mut after = page.after.clone();
    let mut items = Vec::new();
    // A maximum of 200 scoped profiles per request; no SQL held over directory I/O.
    for _ in 0..4 {
        let mut result = list(pool, directory, caller, id, after.as_deref(), candidates).await?;
        result.items.retain(|member| {
            let u = &member.user;
            [
                &u.id,
                u.username.as_deref().unwrap_or_default(),
                u.first_name.as_deref().unwrap_or_default(),
                u.last_name.as_deref().unwrap_or_default(),
                u.email.as_deref().unwrap_or_default(),
                &u.display_name().unwrap_or_default(),
            ]
            .iter()
            .any(|field| field.to_lowercase().contains(&query))
        });
        items.extend(result.items);
        after = result.next_cursor;
        if query.is_empty() || !items.is_empty() || after.is_none() {
            break;
        }
    }
    Ok(SpaceMembers {
        items,
        next_cursor: after,
    })
}

async fn authorize_roster(
    ex: &mut sqlx::PgConnection,
    caller: &str,
    id: Uuid,
    candidates: bool,
) -> AppResult<crate::domain::Space> {
    let facts = authorization::load_facts(&mut *ex, caller, id).await?;
    if facts.space.kind == SpaceKind::Organization {
        authorization::decide(&facts, SpacePermission::AdministerOrganization)?;
        return Ok(facts.space.into());
    }
    match authorization::decide(&facts, SpacePermission::Manage) {
        Err(AppError::Forbidden) if !candidates => {
            authorization::decide(&facts, SpacePermission::Read)?
        }
        result => result?,
    }
    Ok(facts.space.into())
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
    let space = authorize_roster(&mut tx, caller, id, candidates).await?;
    if !matches!(
        space.kind,
        SpaceKind::Organization | SpaceKind::Team | SpaceKind::Project
    ) {
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
    authorize_roster(&mut *pool.acquire().await?, caller, id, candidates).await?;
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
    params(("id" = Uuid, Path), ("after" = Option<String>, Query), ("search" = Option<String>, Query)),
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
        search(
            &s.pool,
            &organization_directory(&s)?,
            &user.uid,
            id,
            &page,
            false,
        )
        .await?,
    ))
}

#[utoipa::path(
    get, path = "/spaces/{id}/member-candidates",
    params(("id" = Uuid, Path), ("after" = Option<String>, Query), ("search" = Option<String>, Query)),
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
        search(
            &s.pool,
            &organization_directory(&s)?,
            &user.uid,
            id,
            &page,
            true,
        )
        .await?,
    ))
}
