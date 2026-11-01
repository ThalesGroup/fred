// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Current-definition publication. Reads authorize within a request-local SQL
//! snapshot; each page/detail is a new admission. Mutations authorize after the
//! shared organization lock. An admitted operation may finish after title expiry.

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use utoipa::ToSchema;
use uuid::Uuid;

use super::{PAGE_SIZE, Prompt, PromptSummary};
use crate::{
    api::AppState,
    authorization::prompt_publication_access,
    db,
    domain::{Space, SpaceKind, SpaceRow},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    onboarding::AdmittedUser,
    spaces,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PageQuery {
    after: Option<Uuid>,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PromptMarketplace {
    pub organization_id: Uuid,
    pub name: String,
}

#[derive(Serialize, ToSchema)]
pub struct PromptMarketplacePage {
    #[schema(max_items = 100)]
    pub items: Vec<PromptMarketplace>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PublishedPromptSummary {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub prompt: PromptSummary,
    pub team_name: String,
    /// Advisory UI decision; writes always recheck the current source-team title.
    pub can_publish: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PublishedPrompt {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub prompt: Prompt,
    pub team_name: String,
}

#[derive(Serialize, ToSchema)]
pub struct PublishedPromptPage {
    #[schema(max_items = 100)]
    pub items: Vec<PublishedPromptSummary>,
    /// Exclusive immutable UUID cursor. Pages are current reads, not a snapshot
    /// across requests; restart to see concurrent publications before the cursor.
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PromptPublicationRequest {
    pub published: bool,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(prompt_marketplaces))
        .routes(utoipa_axum::routes!(prompt_publication_teams))
        .routes(utoipa_axum::routes!(published_prompts))
        .routes(utoipa_axum::routes!(published_prompt))
        .routes(utoipa_axum::routes!(set_prompt_publication))
}

/// Only organizations reached through an active collective business title,
/// including temporary invitations. This grants no ordinary space permissions.
#[utoipa::path(get, path = "/me/prompt-marketplaces",
    params(("after" = Option<Uuid>, Query)),
    responses((status = 200, body = PromptMarketplacePage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn prompt_marketplaces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<PromptMarketplacePage>> {
    let mut items: Vec<PromptMarketplace> = sqlx::query_as(concat!(
        prompt_publication_access!(),
        "
        select o.id as organization_id, o.name from space o
        where exists(select 1 from prompt_access a where a.organization_id = o.id)
          and o.id > $2 order by o.id limit $3"
    ))
    .bind(&user.uid)
    .bind(query.after.unwrap_or(Uuid::nil()))
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(&s.pool)
    .await?;
    let next_cursor = (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].organization_id);
    items.truncate(PAGE_SIZE);
    Ok(Json(PromptMarketplacePage { items, next_cursor }))
}

#[derive(Serialize, ToSchema)]
pub struct PromptPublicationTeam {
    pub organization_id: Uuid,
    #[serde(flatten)]
    pub space: Space,
}

#[derive(Serialize, ToSchema)]
pub struct PromptPublicationTeamPage {
    #[schema(max_items = 100)]
    pub items: Vec<PromptPublicationTeam>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

/// Navigation for direct team editors, including guests. Does not advertise
/// membership or authority over any domain other than prompt publication/reads.
#[utoipa::path(get, path = "/me/prompt-publication-teams",
    params(("after" = Option<Uuid>, Query)),
    responses((status = 200, body = PromptPublicationTeamPage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn prompt_publication_teams(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<PromptPublicationTeamPage>> {
    let mut rows: Vec<SpaceRow> = sqlx::query_as(concat!(
        prompt_publication_access!(),
        "select s.id, s.kind, s.name, s.personal_owner, s.parent_id, s.organization_id
         from space s join prompt_access a on a.space_id=s.id
         where s.kind='team' and a.can_publish and s.id > $2 order by s.id limit $3"
    ))
    .bind(&user.uid)
    .bind(query.after.unwrap_or(Uuid::nil()))
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(&s.pool)
    .await?;
    let next_cursor = (rows.len() > PAGE_SIZE).then(|| rows[PAGE_SIZE - 1].id);
    rows.truncate(PAGE_SIZE);
    let items = rows
        .into_iter()
        .map(|row| PromptPublicationTeam {
            organization_id: row.organization_id,
            space: row.into(),
        })
        .collect();
    Ok(Json(PromptPublicationTeamPage { items, next_cursor }))
}

async fn authorized_read(
    pool: &PgPool,
    actor: &str,
    organization: Uuid,
) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '15s'")
        .execute(&mut *tx)
        .await?;
    let allowed: bool = sqlx::query_scalar(concat!(
        prompt_publication_access!(),
        " select exists(select 1 from prompt_access where organization_id = $2)"
    ))
    .bind(actor)
    .bind(organization)
    .fetch_one(&mut *tx)
    .await?;
    if !allowed {
        return Err(AppError::NotFound);
    }
    Ok(tx)
}

/// Bounded organization catalogue; previews and team labels never come from
/// an unrestricted source-space read. No usage counter or import is exposed.
#[utoipa::path(get, path = "/organizations/{organization_id}/published-prompts",
    params(("organization_id" = Uuid, Path), ("after" = Option<Uuid>, Query)),
    responses((status = 200, body = PublishedPromptPage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn published_prompts(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<PublishedPromptPage>> {
    let mut tx = authorized_read(&s.pool, &user.uid, organization).await?;
    let mut items: Vec<PublishedPromptSummary> = sqlx::query_as(concat!(
        prompt_publication_access!(), "
        select p.prompt_id, p.space_id, p.published, p.logical_name, p.display_name,
            p.description, p.category_id, p.tags, p.created_at, p.created_by,
            p.updated_at, p.updated_by, left(p.text, 240) as text_preview,
            exists(select 1 from prompt_favorite f where f.prompt_id=p.prompt_id and f.user_id=$1) as is_favorite,
            s.name as team_name,
            exists(select 1 from prompt_access a where a.space_id=s.id and a.can_publish) as can_publish
        from prompt p join space s on s.id=p.space_id
        where s.organization_id=$2 and s.kind='team' and s.deletion_id is null
          and p.published and p.prompt_id > $3
        order by p.prompt_id limit $4"
    )).bind(&user.uid).bind(organization).bind(query.after.unwrap_or(Uuid::nil()))
        .bind((PAGE_SIZE + 1) as i64).fetch_all(&mut *tx).await?;
    let next_cursor =
        (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].prompt.metadata.prompt_id);
    items.truncate(PAGE_SIZE);
    tx.commit().await?;
    Ok(Json(PublishedPromptPage { items, next_cursor }))
}

#[utoipa::path(get, path = "/organizations/{organization_id}/published-prompts/{prompt_id}",
    params(("organization_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    responses((status = 200, body = PublishedPrompt),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn published_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<PublishedPrompt>> {
    let mut tx = authorized_read(&s.pool, &user.uid, organization).await?;
    let prompt = sqlx::query_as(
        "select p.*, s.name as team_name,
            exists(select 1 from prompt_favorite f where f.prompt_id=p.prompt_id and f.user_id=$3) as is_favorite
        from prompt p join space s on s.id=p.space_id
        where p.prompt_id=$1 and s.organization_id=$2 and s.kind='team'
          and s.deletion_id is null and p.published"
    ).bind(prompt_id).bind(organization).bind(&user.uid)
        .fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    tx.commit().await?;
    Ok(Json(prompt))
}

/// Idempotent publication/retraction by a direct permanent or actively invited
/// team editor. Neither ancestor roles nor technical administration qualify.
#[utoipa::path(put, path = "/spaces/{space_id}/prompts/{prompt_id}/publication",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
    request_body = PromptPublicationRequest,
    responses((status = 204, description = "Publication state saved"),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn set_prompt_publication(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<PromptPublicationRequest>,
) -> AppResult<StatusCode> {
    let mut tx = spaces::mutation_transaction(&s.pool, space_id).await?;
    let space = db::space(&mut *tx, space_id).await?;
    let (inside, editor): (bool, bool) = sqlx::query_as(concat!(
        prompt_publication_access!(),
        " select
        exists(select 1 from prompt_access where organization_id=$2),
        exists(select 1 from prompt_access where space_id=$3 and can_publish)"
    ))
    .bind(&user.uid)
    .bind(space.organization_id)
    .bind(space_id)
    .fetch_one(&mut *tx)
    .await?;
    if !inside {
        return Err(AppError::NotFound);
    }
    if !editor {
        return Err(AppError::Forbidden);
    }
    if space.kind != SpaceKind::Team {
        return Err(AppError::BadRequest(
            "only team prompts can be published".into(),
        ));
    }
    crate::lifecycle::store::require_active(&mut *tx, space_id).await?;
    let result = sqlx::query("update prompt set published=$3 where space_id=$1 and prompt_id=$2")
        .bind(space_id)
        .bind(prompt_id)
        .bind(body.published)
        .execute(&mut *tx)
        .await?;
    if result.rows_affected() == 0 {
        return Err(AppError::NotFound);
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
