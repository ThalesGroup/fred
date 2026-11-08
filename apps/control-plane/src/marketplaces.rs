// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Marketplace audiences, independent of the published resource type.
//! Organization participation is the first supported audience. Source-space rights
//! are not required to read publications; platform administration alone grants no access.

use crate::{
    api::AppState,
    authorization::{self, subject_spaces},
    domain::{Space, SpaceKind},
    error::{AppError, AppResult},
    extract::ApiQuery,
    onboarding::AdmittedUser,
    roles::SpacePermission,
};
use axum::{Json, extract::State};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use utoipa::ToSchema;
use uuid::Uuid;

const PAGE_SIZE: usize = 100;
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PageQuery {
    after: Option<Uuid>,
}

pub(crate) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new().routes(utoipa_axum::routes!(marketplaces))
}

/// Only the source's organization marketplace is enabled in this increment.
/// This policy is shared by publishers; adding a platform audience requires an
/// explicit extension here and in the common space/isolation model.
pub(crate) fn publication_destinations(source: &Space) -> Vec<Uuid> {
    vec![source.organization]
}

pub(crate) fn require_destination(source: &Space, marketplace_space: Uuid) -> AppResult<()> {
    if !publication_destinations(source).contains(&marketplace_space) {
        return Err(AppError::BadRequest(
            "marketplace is not an enabled destination for this space".into(),
        ));
    }
    Ok(())
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct Marketplace {
    pub space_id: Uuid,
    pub name: String,
}

#[derive(Serialize, ToSchema)]
pub struct MarketplacePage {
    #[schema(max_items = 100)]
    pub items: Vec<Marketplace>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

/// Organizations where the caller participates through an active collective business role.
#[utoipa::path(get, path = "/me/marketplaces",
    params(("after" = Option<Uuid>, Query)),
    responses((status = 200, body = MarketplacePage),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody))) ]
async fn marketplaces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<PageQuery>,
) -> AppResult<Json<MarketplacePage>> {
    let mut items: Vec<Marketplace> = sqlx::query_as(concat!(
        subject_spaces!(),
        "
        select o.id as space_id, o.name from space o
        where exists(select 1 from organization_participants a where a.organization_id = o.id)
          and o.id > $3 order by o.id limit $4"
    ))
    .bind(&user.uid)
    .bind(authorization::roles_granting(
        SpacePermission::CreatePersonalSpace,
    ))
    .bind(query.after.unwrap_or(Uuid::nil()))
    .bind((PAGE_SIZE + 1) as i64)
    .fetch_all(&s.pool)
    .await?;
    let next_cursor = (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].space_id);
    items.truncate(PAGE_SIZE);
    Ok(Json(MarketplacePage { items, next_cursor }))
}

/// Authorize organization catalogue reads using participation facts from a read-only SQL snapshot.
/// Each catalogue page or definition read obtains a new snapshot and authorization decision.
pub(crate) async fn read_snapshot(
    pool: &PgPool,
    actor: &str,
    marketplace_space: Uuid,
) -> AppResult<Transaction<'static, Postgres>> {
    let mut tx = pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    sqlx::query("set local statement_timeout = '15s'")
        .execute(&mut *tx)
        .await?;
    let facts = authorization::load_facts(&mut *tx, actor, marketplace_space).await?;
    if facts.space.kind != SpaceKind::Organization || !facts.organization_participant {
        return Err(AppError::NotFound);
    }
    Ok(tx)
}
