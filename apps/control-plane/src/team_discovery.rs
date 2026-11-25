// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Team, project and opted-in resource metadata are discoverable without content
//! authority. A project's audience is its parent team's content holders.
//! Enrollment writes ordinary direct roles; resource discovery never grants access.
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::{PgConnection, PgPool};
use utoipa_axum::{router::OpenApiRouter, routes};
use uuid::Uuid;

use crate::{
    api::AppState,
    authorization, bootstrap,
    domain::{Permission, Role, Space, SpaceKind},
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

/// What a space's card shows: identity, enrollment and a bounded roster summary
/// (direct role holder count, owner count, at most four named owners for the
/// card's avatar row). Excludes the roster itself, resources and content permissions.
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
    /// Distinct subjects holding any direct role.
    pub member_count: i64,
    /// Direct owners in total; `owners` describes at most four of them.
    pub owner_count: i64,
    /// Resolved after SQL; an owner the directory cannot describe is omitted. The id
    /// is the subject the space-scoped user avatar route expects.
    #[sqlx(skip)]
    #[schema(max_items = 4)]
    pub owners: Vec<SpaceOwner>,
    #[serde(skip)]
    pub owner_subjects: Vec<String>,
}

/// An owner on a space card: avatar subject and display name, nothing else.
#[derive(Debug, Serialize, utoipa::ToSchema)]
pub struct SpaceOwner {
    pub id: String,
    pub display_name: String,
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

#[derive(Debug, Clone, Copy, Deserialize, Serialize, sqlx::Type, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
#[sqlx(type_name = "text", rename_all = "snake_case")]
pub enum DiscoverableResourceKind {
    Prompt,
    Skill,
    Agent,
}

#[derive(Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ResourceDirectoryQuery {
    pub search: Option<String>,
    pub page: Option<u32>,
    pub kind: Option<DiscoverableResourceKind>,
}

/// An allowlist, not a truncated content response: no text previews, package
/// fields, tuning, authors, hashes or metadata derived from private instructions.
#[derive(Debug, Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct DiscoverableResource {
    pub resource_id: Uuid,
    pub kind: DiscoverableResourceKind,
    pub display_name: String,
    pub description: Option<String>,
    pub space_id: Uuid,
    pub space_name: String,
    pub space_kind: SpaceKind,
    pub can_read: bool,
}

#[derive(Serialize, utoipa::ToSchema)]
pub struct ResourceDirectoryPage {
    #[schema(max_items = 20)]
    pub items: Vec<DiscoverableResource>,
    pub total: i64,
}

const PAGE_SIZE: i64 = 20;
const PROJECT_LIMIT: i64 = 200;

fn search_tokens(search: Option<&str>) -> AppResult<Vec<String>> {
    let search = search.unwrap_or_default().trim().to_lowercase();
    if search.chars().count() > 180 {
        return Err(AppError::Unprocessable("search is too long".into()));
    }
    Ok(search.split_whitespace().map(str::to_owned).collect())
}

/// Personal definitions cannot be exposed outside their ordinary private library.
pub(crate) fn validate_resource_visibility(kind: SpaceKind, discoverable: bool) -> AppResult<()> {
    if kind == SpaceKind::Personal && discoverable {
        return Err(AppError::Unprocessable(
            "Personal resources cannot be visible in organization search".into(),
        ));
    }
    Ok(())
}
// Lists, metadata, avatar reads and joins share exactly the same disclosure
// predicate; `disclosed` adds the parent-team audience of a project.
macro_rules! discoverable {
    () => {
        "s.kind in ('team','project') and s.deletion_id is null
    and (s.visibility='visible' or exists (
        select 1 from space_role_grant r where r.space_id=s.id and r.subject=$2))"
    };
}
macro_rules! card { () => { "s.id,s.name,s.description,s.visibility,s.joining_mode,
    exists(select 1 from space_role_grant r where r.space_id=s.id and r.subject=$2) as is_member,
    false as can_join,
    (select count(distinct r.subject) from space_role_grant r where r.space_id=s.id) as member_count,
    (select count(*) from space_role_grant r where r.space_id=s.id and r.role='owner') as owner_count,
    array(select r.subject from space_role_grant r where r.space_id=s.id and r.role='owner'
        order by r.subject limit 4) as owner_subjects" }; }

/// Resolve the owners of a page of cards together, after SQL is released. Names are
/// display data only: an unavailable directory leaves them empty, as for authors.
async fn name_owners(s: &AppState, cards: &mut [DiscoverableTeam]) {
    let subjects = cards
        .iter()
        .flat_map(|card| card.owner_subjects.iter().cloned())
        .collect();
    let names = async {
        crate::api::organization_directory(s)?
            .display_names(subjects)
            .await
    };
    let names = names.await.unwrap_or_else(|_| {
        tracing::warn!("Space owner names unavailable");
        Default::default()
    });
    for card in cards {
        card.owners = card
            .owner_subjects
            .iter()
            .filter_map(|subject| {
                names.get(subject).map(|name| SpaceOwner {
                    id: subject.clone(),
                    display_name: name.clone(),
                })
            })
            .collect();
    }
}

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
    if !facts.organization_participant
        && authorization::decide(&facts, SpacePermission::AdministerOrganization).is_err()
    {
        return Err(AppError::NotFound);
    }
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
    let tokens = search_tokens(query.search.as_deref())?;
    let mut tx = spaces::storage_transaction(pool, organization, true).await?;
    let facts = require_organization(&mut tx, caller, organization).await?;
    let eligible = authorization::decide(&facts, SpacePermission::Read).is_ok();
    macro_rules! filter { () => { concat!("s.organization_id=$1 and s.kind='team' and ", discoverable!(), " and not exists (
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

/// Current source metadata only. The shared organization guard and ordinary
/// direct-role matrix determine audience and the optional source-opening action.
pub async fn resources(
    pool: &PgPool,
    caller: &str,
    organization: Uuid,
    query: &ResourceDirectoryQuery,
) -> AppResult<ResourceDirectoryPage> {
    let tokens = search_tokens(query.search.as_deref())?;
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '15s'")
        .execute(&mut *tx)
        .await?;
    require_organization(&mut tx, caller, organization).await?;
    // A project's external disclosure needs both its own and its team's visibility.
    // A direct project role exposes its own origin only, never a hidden ancestor.
    macro_rules! catalog {
        () => {
            "with catalog as (
                select r.resource_id,r.kind,r.display_name,r.description,
                    s.id as space_id,s.name as space_name,s.kind as space_kind,
                    r.content_available and exists(select 1 from space_role_grant g
                        where g.space_id=s.id and g.subject=$2 and g.role=any($5)) as can_read
                from space s left join space parent on parent.id=s.parent_id
                cross join lateral (
                    select prompt_id as resource_id,'prompt'::text as kind,display_name,description,true as content_available
                        from prompt where space_id=s.id and discoverable
                    union all
                    select skill_id,'skill',name,summary->>'description',true
                        from skill where space_id=s.id and discoverable
                    union all
                    select agent_instance_id,'agent',display_name,description,
                        exists(select 1 from agent_template_policy p
                            where p.organization_id=$1 and p.template_id=a.template_id)
                        from agent_instance a where space_id=s.id and discoverable
                ) r
                where s.organization_id=$1 and s.kind<>'personal' and s.deletion_id is null
                    and (parent.id is null or parent.deletion_id is null)
                    and (s.kind='organization'
                        or (s.kind='team' and s.visibility='visible')
                        or (s.kind='project' and parent.visibility='visible' and s.visibility='visible')
                        or exists(select 1 from space_role_grant g where g.space_id=s.id and g.subject=$2))
                    and ($4::text is null or r.kind=$4)
                    and not exists(select 1 from unnest($3::text[]) token where
                        strpos(lower(r.display_name),token)=0
                        and strpos(lower(coalesce(r.description,'')),token)=0
                        and strpos(lower(s.name),token)=0 and strpos(r.kind,token)=0)
            ) "
        };
    }
    let read_roles = authorization::roles_granting(SpacePermission::Read);
    let total = sqlx::query_scalar(concat!(catalog!(), "select count(*) from catalog"))
        .bind(organization)
        .bind(caller)
        .bind(&tokens)
        .bind(query.kind)
        .bind(&read_roles)
        .fetch_one(&mut *tx)
        .await?;
    let items = sqlx::query_as(concat!(
        catalog!(),
        "select * from catalog order by lower(display_name),kind,resource_id limit $6 offset $7"
    ))
    .bind(organization)
    .bind(caller)
    .bind(&tokens)
    .bind(query.kind)
    .bind(&read_roles)
    .bind(PAGE_SIZE)
    .bind(i64::from(query.page.unwrap_or_default()) * PAGE_SIZE)
    .fetch_all(&mut *tx)
    .await?;
    tx.commit().await?;
    Ok(ResourceDirectoryPage { items, total })
}

/// A card requires organization participation. Join eligibility is the parent's
/// content role, which also bounds a project's audience unless the caller holds a
/// direct role on it. Hidden spaces are never disclosed via a guessed ID.
async fn disclosed(
    conn: &mut PgConnection,
    caller: &str,
    space: &Space,
) -> AppResult<(DiscoverableTeam, bool)> {
    require_organization(&mut *conn, caller, space.organization).await?;
    let mut card: DiscoverableTeam = sqlx::query_as(concat!(
        "select ",
        card!(),
        " from space s where s.id=$1 and ",
        discoverable!()
    ))
    .bind(space.id)
    .bind(caller)
    .fetch_optional(&mut *conn)
    .await?
    .ok_or(AppError::NotFound)?;
    let parent = space.parent_id.ok_or(AppError::NotFound)?;
    let eligible = authorization::authorize(&mut *conn, caller, parent, Permission::Read)
        .await
        .is_ok();
    if space.kind == SpaceKind::Project && !card.is_member && !eligible {
        return Err(AppError::NotFound);
    }
    set_join_action(&mut card, eligible);
    Ok((card, eligible))
}

/// Used by the metadata route and the existing authenticated avatar transport.
pub async fn metadata(pool: &PgPool, caller: &str, id: Uuid) -> AppResult<DiscoverableTeam> {
    let mut tx = spaces::storage_transaction(pool, id, true).await?;
    let space: Space = crate::db::space(&mut *tx, id).await?.into();
    let (card, _) = disclosed(&mut tx, caller, &space).await?;
    tx.commit().await?;
    Ok(card)
}

/// A team's projects for its content holders and its managers (an owner without
/// content access): visible ones and those where the caller holds a direct role.
/// Only content holders may join. Bounded by the design target per team.
pub async fn projects(pool: &PgPool, caller: &str, team: Uuid) -> AppResult<Vec<DiscoverableTeam>> {
    let mut tx = spaces::storage_transaction(pool, team, true).await?;
    let facts = authorization::load_facts(&mut *tx, caller, team).await?;
    let eligible = authorization::decide(&facts, SpacePermission::Read).is_ok();
    if !eligible {
        authorization::decide(&facts, SpacePermission::Manage).map_err(|error| match error {
            AppError::Forbidden => AppError::NotFound,
            error => error,
        })?;
    }
    if facts.space.kind != SpaceKind::Team {
        return Err(AppError::NotFound);
    }
    let mut items: Vec<DiscoverableTeam> = sqlx::query_as(concat!(
        "select ",
        card!(),
        " from space s where s.parent_id=$1 and ",
        discoverable!(),
        " order by lower(s.name),s.id limit $3"
    ))
    .bind(team)
    .bind(caller)
    .bind(PROJECT_LIMIT)
    .fetch_all(&mut *tx)
    .await?;
    for project in &mut items {
        set_join_action(project, eligible);
    }
    tx.commit().await?;
    Ok(items)
}

/// Platform then organization, the same order as role writes and link redemption.
/// Recheck all facts after locking; hiding/closing/revoking/retiring orders with join.
pub async fn join(pool: &PgPool, caller: &str, id: Uuid) -> AppResult<()> {
    let space = spaces::load(pool, id).await?;
    let mut tx = bootstrap::locked(pool).await?;
    spaces::lock_organization(&mut tx, &space).await?;
    let (card, eligible) = disclosed(&mut tx, caller, &space).await?;
    // Same parent-role prerequisite as invitation redemption and ordinary grants.
    if !eligible
        || card.visibility != TeamVisibility::Visible
        || card.joining_mode != TeamJoiningMode::Open
    {
        return Err(AppError::Forbidden);
    }
    // Do not turn a pre-existing owner/editor/analyst into a content Member.
    if !card.is_member {
        authorization::write_role(&mut tx, caller, Role::Member, id, true).await?;
    }
    tx.commit().await?;
    if !card.is_member {
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
        .routes(routes!(organization_resources))
        .routes(routes!(team_metadata))
        .routes(routes!(team_projects))
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
    let mut page = list(&s.pool, &user.uid, organization_id, &query).await?;
    name_owners(&s, &mut page.items).await;
    Ok(Json(page))
}

#[utoipa::path(get, path="/organizations/{organization_id}/resources", params(
    ("organization_id"=Uuid, Path), ("search"=Option<String>, Query),
    ("page"=Option<u32>, Query), ("kind"=Option<DiscoverableResourceKind>, Query)),
    responses((status=200, body=ResourceDirectoryPage), (status=401, body=ErrorBody),
    (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody),
    (status=500, body=ErrorBody)))]
async fn organization_resources(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<ResourceDirectoryQuery>,
) -> AppResult<Json<ResourceDirectoryPage>> {
    Ok(Json(
        resources(&s.pool, &user.uid, organization_id, &query).await?,
    ))
}

#[utoipa::path(get, path="/spaces/{id}/discovery", params(("id"=Uuid, Path)),
 responses((status=200, body=DiscoverableTeam), (status=401, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody), (status=500, body=ErrorBody), (status=503, body=ErrorBody)))]
async fn team_metadata(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<DiscoverableTeam>> {
    let mut card = metadata(&s.pool, &user.uid, id).await?;
    name_owners(&s, std::slice::from_mut(&mut card)).await;
    Ok(Json(card))
}

#[utoipa::path(get, path="/spaces/{id}/projects", params(("id"=Uuid, Path)),
 responses((status=200, body=Vec<DiscoverableTeam>), (status=401, body=ErrorBody), (status=404, body=ErrorBody), (status=409, body=ErrorBody), (status=422, body=ErrorBody), (status=500, body=ErrorBody), (status=503, body=ErrorBody)))]
async fn team_projects(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<Vec<DiscoverableTeam>>> {
    let mut items = projects(&s.pool, &user.uid, id).await?;
    name_owners(&s, &mut items).await;
    Ok(Json(items))
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
