// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Current-definition publication. Reads authorize within a request-local SQL
//! snapshot; each page/detail is a new admission. Mutations authorize after the
//! shared organization lock. An admitted operation may finish after role revocation.

use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use super::{PAGE_SIZE, Prompt, PromptSummary};
use crate::{
    api::AppState,
    authorization::{self, subject_spaces},
    domain::{Space, SpaceRow},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery},
    marketplaces,
    onboarding::AdmittedUser,
    roles::SpacePermission,
    spaces,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PageQuery {
    after: Option<Uuid>,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PublishedPromptSummary {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub prompt: PromptSummary,
    pub source_space_name: String,
    /// Advisory UI decision; writes always recheck the current source-space Write permission.
    pub can_publish: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct PublishedPrompt {
    #[serde(flatten)]
    #[sqlx(flatten)]
    pub prompt: Prompt,
    pub source_space_name: String,
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
        .routes(utoipa_axum::routes!(prompt_publication_spaces))
        .routes(utoipa_axum::routes!(published_prompts))
        .routes(utoipa_axum::routes!(published_prompt))
        .routes(utoipa_axum::routes!(set_prompt_publication))
}

#[derive(Serialize, ToSchema)]
pub struct PromptPublicationSpace {
    pub marketplace_space_ids: Vec<Uuid>,
    #[serde(flatten)]
    pub space: Space,
}

#[derive(Serialize, ToSchema)]
pub struct PromptPublicationSpacePage {
    #[schema(max_items = 100)]
    pub items: Vec<PromptPublicationSpace>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

/// Active source spaces where the caller has direct Write permission and a publication destination.
#[utoipa::path(get, path = "/me/prompt-publication-spaces",
    params(("after" = Option<Uuid>, Query)),
    responses((status = 200, body = PromptPublicationSpacePage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn prompt_publication_spaces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<PromptPublicationSpacePage>> {
    let mut rows: Vec<SpaceRow> = sqlx::query_as(concat!(
        subject_spaces!(),
        "select s.id, s.kind, s.name, s.personal_owner, s.parent_id, s.organization_id
         from subject_spaces s
         where s.active and s.direct_roles && $5::text[]
           and exists(select 1 from organization_participants o where o.organization_id=s.organization_id)
         and s.id > $3 order by s.id limit $4"
    ))
    .bind(&user.uid)
    .bind(authorization::roles_granting(
        SpacePermission::CreatePersonalSpace,
    ))
    .bind(query.after.unwrap_or(Uuid::nil()))
    .bind((PAGE_SIZE + 1) as i64)
    .bind(authorization::roles_granting(SpacePermission::Write))
    .fetch_all(&s.pool)
    .await?;
    let next_cursor = (rows.len() > PAGE_SIZE).then(|| rows[PAGE_SIZE - 1].id);
    rows.truncate(PAGE_SIZE);
    let items = rows
        .into_iter()
        .map(|row| {
            let space = row.into();
            PromptPublicationSpace {
                marketplace_space_ids: marketplaces::publication_destinations(&space),
                space,
            }
        })
        .collect();
    Ok(Json(PromptPublicationSpacePage { items, next_cursor }))
}

/// Bounded marketplace catalogue; previews and source labels never come from
/// an unrestricted source-space read. No usage counter or import is exposed.
#[utoipa::path(get, path = "/spaces/{marketplace_space_id}/published-prompts",
    params(("marketplace_space_id" = Uuid, Path), ("after" = Option<Uuid>, Query)),
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
    ApiPath(marketplace_space_id): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<PublishedPromptPage>> {
    let mut tx = marketplaces::read_snapshot(&s.pool, &user.uid, marketplace_space_id).await?;
    let mut items: Vec<PublishedPromptSummary> = sqlx::query_as(concat!(
        subject_spaces!(), "
        select p.prompt_id, p.space_id, array[publication.marketplace_space_id] as published_in, p.logical_name, p.display_name,
            p.description, p.category_id, p.tags, p.created_at, p.created_by,
            p.updated_at, p.updated_by, left(p.text, 240) as text_preview,
            exists(select 1 from prompt_favorite f where f.prompt_id=p.prompt_id and f.user_id=$1) as is_favorite,
            s.name as source_space_name,
            exists(select 1 from subject_spaces a where a.id=s.id and a.active and a.direct_roles && $6::text[]) as can_publish
        from prompt_publication publication join prompt p on p.prompt_id=publication.prompt_id
        join space s on s.id=p.space_id left join space parent on parent.id=s.parent_id
        where publication.marketplace_space_id=$3 and s.deletion_id is null and parent.deletion_id is null
          and p.prompt_id > $4
        order by p.prompt_id limit $5"
    )).bind(&user.uid).bind(authorization::roles_granting(SpacePermission::CreatePersonalSpace))
        .bind(marketplace_space_id).bind(query.after.unwrap_or(Uuid::nil()))
        .bind((PAGE_SIZE + 1) as i64).bind(authorization::roles_granting(SpacePermission::Write)).fetch_all(&mut *tx).await?;
    let next_cursor =
        (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].prompt.metadata.prompt_id);
    items.truncate(PAGE_SIZE);
    tx.commit().await?;
    Ok(Json(PublishedPromptPage { items, next_cursor }))
}

#[utoipa::path(get, path = "/spaces/{marketplace_space_id}/published-prompts/{prompt_id}",
    params(("marketplace_space_id" = Uuid, Path), ("prompt_id" = Uuid, Path)),
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
    ApiPath((marketplace_space_id, prompt_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<PublishedPrompt>> {
    let mut tx = marketplaces::read_snapshot(&s.pool, &user.uid, marketplace_space_id).await?;
    let prompt = sqlx::query_as(
        "select p.*, array[publication.marketplace_space_id] as published_in, s.name as source_space_name,
            exists(select 1 from prompt_favorite f where f.prompt_id=p.prompt_id and f.user_id=$3) as is_favorite
        from prompt_publication publication join prompt p on p.prompt_id=publication.prompt_id
        join space s on s.id=p.space_id left join space parent on parent.id=s.parent_id
        where p.prompt_id=$1 and publication.marketplace_space_id=$2
          and s.deletion_id is null and parent.deletion_id is null"
    ).bind(prompt_id).bind(marketplace_space_id).bind(&user.uid)
        .fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    tx.commit().await?;
    Ok(Json(prompt))
}

/// Idempotent publication/retraction by a direct source-space editor, to an explicit marketplace.
/// Missing or outside-organization space: 404; retired space: 409 space_pending_deletion;
/// missing direct Write permission, including organization admin alone: 403.
#[utoipa::path(put, path = "/spaces/{space_id}/prompts/{prompt_id}/publications/{marketplace_space_id}",
    params(("space_id" = Uuid, Path), ("prompt_id" = Uuid, Path), ("marketplace_space_id" = Uuid, Path)),
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
    ApiPath((space_id, prompt_id, marketplace_space_id)): ApiPath<(Uuid, Uuid, Uuid)>,
    ApiJson(body): ApiJson<PromptPublicationRequest>,
) -> AppResult<StatusCode> {
    let (mut tx, space) =
        spaces::authorized_mutation(&s.pool, &user.uid, space_id, SpacePermission::Write).await?;
    marketplaces::require_destination(&space, marketplace_space_id)?;
    let exists: bool = sqlx::query_scalar(
        "select exists(select 1 from prompt where space_id=$1 and prompt_id=$2)",
    )
    .bind(space_id)
    .bind(prompt_id)
    .fetch_one(&mut *tx)
    .await?;
    if !exists {
        return Err(AppError::NotFound);
    }
    let changed = if body.published {
        sqlx::query("insert into prompt_publication(prompt_id,marketplace_space_id,published_by) values($1,$2,$3) on conflict do nothing")
            .bind(prompt_id).bind(marketplace_space_id).bind(&user.uid).execute(&mut *tx).await?.rows_affected()
    } else {
        sqlx::query("delete from prompt_publication where prompt_id=$1 and marketplace_space_id=$2")
            .bind(prompt_id)
            .bind(marketplace_space_id)
            .execute(&mut *tx)
            .await?
            .rows_affected()
    };
    tx.commit().await?;
    if changed != 0 {
        tracing::info!(target: "fred.security.audit", audit_event="prompt.publication.changed",
            actor_uid=%user.uid, space_id=%space_id, prompt_id=%prompt_id,
            marketplace_space_id=%marketplace_space_id, published=body.published);
    }
    Ok(StatusCode::NO_CONTENT)
}
