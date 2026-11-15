// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Team metadata is discoverable independently of content authority. Settings live
//! on space; enrollment writes ordinary direct roles, just like invitation links.
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, PgPool};
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization, bootstrap,
    domain::{Role, SpaceKind},
    error::{AppError, AppResult, ErrorBody},
    extract::{ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    roles::SpacePermission,
    spaces,
};

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, sqlx::Type, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum TeamVisibility {
    Hidden,
    Visible,
}

#[derive(
    Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, sqlx::Type, utoipa::ToSchema,
)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum TeamJoiningMode {
    InviteOnly,
    Open,
}

/// Deliberately excludes roster, counts, resources and content permissions.
#[derive(Debug, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct DiscoverableTeam {
    pub id: Uuid,
    pub name: String,
    pub description: Option<String>,
    pub visibility: TeamVisibility,
    pub joining_mode: TeamJoiningMode,
    /// Any direct role, including an owner without content access.
    pub is_member: bool,
    pub can_join: bool,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct TeamDirectoryPage {
    #[schema(max_items = 20)]
    pub items: Vec<DiscoverableTeam>,
    pub total: i64,
}

#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TeamDirectoryQuery {
    pub search: Option<String>,
    pub page: Option<u32>,
}

const PAGE_SIZE: i64 = 20;
// List, metadata and avatar reads share exactly the same disclosure predicate.
macro_rules! discoverable {
    () => {
        "s.kind='team' and s.deletion_id is null
    and (s.visibility='visible' or exists (
        select 1 from space_role_grant r where r.space_id=s.id and r.subject=$2))"
    };
}
macro_rules! card { () => { "s.id,s.name,s.description,s.visibility,s.joining_mode,
    exists(select 1 from space_role_grant r where r.space_id=s.id and r.subject=$2) as is_member,
    false as can_join" }; }

async fn require_organization(
    conn: &mut PgConnection,
    caller: &str,
    id: Uuid,
) -> AppResult<authorization::SpaceFacts> {
    let facts = authorization::load_facts(&mut *conn, caller, id).await?;
    if facts.space.kind != SpaceKind::Organization || !facts.in_organization {
        return Err(AppError::NotFound);
    }
    facts.require_active()?;
    Ok(facts)
}

fn set_join_action(team: &mut DiscoverableTeam, eligible: bool) {
    team.can_join = eligible
        && !team.is_member
        && team.visibility == TeamVisibility::Visible
        && team.joining_mode == TeamJoiningMode::Open;
}

/// One organization guard covers eligibility, visibility, count and page. No
/// directory or object-store calls occur while SQL is held.
pub async fn list(
    pool: &PgPool,
    caller: &str,
    organization: Uuid,
    query: &TeamDirectoryQuery,
) -> AppResult<TeamDirectoryPage> {
    let search = query
        .search
        .as_deref()
        .unwrap_or_default()
        .trim()
        .to_lowercase();
    if search.chars().count() > 180 {
        return Err(AppError::Unprocessable("search is too long".into()));
    }
    let tokens: Vec<&str> = search.split_whitespace().collect();
    let mut tx = spaces::storage_transaction(pool, organization, true).await?;
    let facts = require_organization(&mut tx, caller, organization).await?;
    let eligible = authorization::decide(&facts, SpacePermission::Read).is_ok();
    macro_rules! filter { () => { concat!("s.organization_id=$1 and ", discoverable!(), " and not exists (
        select 1 from unnest($3::text[]) token where
        strpos(lower(s.name),token)=0 and strpos(lower(coalesce(s.description,'')),token)=0)") }; }
    let total = sqlx::query_scalar(concat!("select count(*) from space s where ", filter!()))
        .bind(organization)
        .bind(caller)
        .bind(&tokens)
        .fetch_one(&mut *tx)
        .await?;
    let mut items: Vec<DiscoverableTeam> = sqlx::query_as(concat!(
        "select ",
        card!(),
        " from space s where ",
        filter!(),
        " order by lower(s.name),s.id limit $4 offset $5"
    ))
    .bind(organization)
    .bind(caller)
    .bind(&tokens)
    .bind(PAGE_SIZE)
    .bind(i64::from(query.page.unwrap_or_default()) * PAGE_SIZE)
    .fetch_all(&mut *tx)
    .await?;
    for team in &mut items {
        set_join_action(team, eligible);
    }
    tx.commit().await?;
    Ok(TeamDirectoryPage { items, total })
}

/// Used by the metadata route and the existing authenticated avatar transport.
/// Hidden teams are visible to their direct role holders only, never via a guessed ID.
pub async fn metadata(pool: &PgPool, caller: &str, id: Uuid) -> AppResult<DiscoverableTeam> {
    let mut tx = spaces::storage_transaction(pool, id, true).await?;
    let space: crate::domain::Space = crate::db::space(&mut *tx, id).await?.into();
    let facts = require_organization(&mut tx, caller, space.organization).await?;
    let mut team: DiscoverableTeam = sqlx::query_as(concat!(
        "select ",
        card!(),
        " from space s where s.id=$1 and ",
        discoverable!()
    ))
    .bind(id)
    .bind(caller)
    .fetch_optional(&mut *tx)
    .await?
    .ok_or(AppError::NotFound)?;
    let eligible = authorization::decide(&facts, SpacePermission::Read).is_ok();
    set_join_action(&mut team, eligible);
    tx.commit().await?;
    Ok(team)
}

/// Platform then organization, the same order as role writes and link redemption.
/// Recheck all facts after locking; hiding/closing/revoking/retiring orders with join.
pub async fn join(pool: &PgPool, caller: &str, id: Uuid) -> AppResult<()> {
    let space = spaces::load(pool, id).await?;
    let mut tx = bootstrap::locked(pool).await?;
    spaces::lock_organization(&mut tx, &space).await?;
    let facts = require_organization(&mut tx, caller, space.organization).await?;
    let team: DiscoverableTeam = sqlx::query_as(concat!(
        "select ",
        card!(),
        " from space s where s.id=$1 and ",
        discoverable!()
    ))
    .bind(id)
    .bind(caller)
    .fetch_optional(&mut *tx)
    .await?
    .ok_or(AppError::NotFound)?;
    // Same parent-role prerequisite as invitation redemption and ordinary grants.
    authorization::decide(&facts, SpacePermission::Read)?;
    if team.visibility != TeamVisibility::Visible || team.joining_mode != TeamJoiningMode::Open {
        return Err(AppError::Forbidden);
    }
    // Do not turn a pre-existing owner/editor/analyst into a content Member.
    if !team.is_member {
        authorization::write_role(&mut tx, caller, Role::Member, id, true).await?;
    }
    tx.commit().await?;
    if !team.is_member {
        crate::logging::audit_relation(
            Some(caller),
            caller,
            "member",
            &format!("space:{id}"),
            true,
        );
    }
    Ok(())
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(organization_teams))
        .routes(routes!(team_metadata))
        .routes(routes!(join_team))
}

#[utoipa::path(get, path="/organizations/{organization_id}/teams", params(("organization_id"=Uuid, Path), ("search"=Option<String>, Query), ("page"=Option<u32>, Query)),
 responses((status=200, body=TeamDirectoryPage), (status=401, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody), (status=500, body=ErrorBody), (status=503, body=ErrorBody)))]
async fn organization_teams(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<TeamDirectoryQuery>,
) -> AppResult<Json<TeamDirectoryPage>> {
    Ok(Json(
        list(&s.pool, &user.uid, organization_id, &query).await?,
    ))
}

#[utoipa::path(get, path="/spaces/{id}/discovery", params(("id"=Uuid, Path)),
 responses((status=200, body=DiscoverableTeam), (status=401, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody), (status=500, body=ErrorBody), (status=503, body=ErrorBody)))]
async fn team_metadata(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<DiscoverableTeam>> {
    Ok(Json(metadata(&s.pool, &user.uid, id).await?))
}

#[utoipa::path(post, path="/spaces/{id}/join", params(("id"=Uuid, Path)),
 responses((status=204), (status=401, body=ErrorBody), (status=403, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody), (status=500, body=ErrorBody)))]
async fn join_team(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    join(&s.pool, &user.uid, id).await?;
    Ok(StatusCode::NO_CONTENT)
}
