// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use axum::{
    Json,
    extract::State,
    http::{HeaderMap, StatusCode},
};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use super::{PAGE_SIZE, models::*, store};
use crate::{
    api::AppState,
    authorization::{self, subject_spaces},
    domain::{Space, SpaceRow},
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath, ApiQuery, idempotency_key},
    onboarding::AdmittedUser,
    roles::SpacePermission,
};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct CatalogueQuery {
    after: Option<Uuid>,
    kind: Option<MarketplaceKind>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ProposalQuery {
    after: Option<Uuid>,
    kind: Option<MarketplaceKind>,
    state: Option<ProposalState>,
    proposing_space_id: Option<Uuid>,
}

#[derive(Serialize, ToSchema)]
pub struct ProposalSpace {
    #[serde(flatten)]
    pub space: Space,
    pub marketplace_space_ids: Vec<Uuid>,
    /// Ordinary resource placement in this writable space, for proposal and installation pickers.
    pub resource_kinds: Vec<MarketplaceKind>,
}

#[derive(Serialize, ToSchema)]
pub struct ProposalSpacePage {
    #[schema(max_items = 100)]
    pub items: Vec<ProposalSpace>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

pub(super) fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(marketplace_proposal_spaces))
        .routes(utoipa_axum::routes!(marketplace_entries))
        .routes(utoipa_axum::routes!(marketplace_entry))
        .routes(utoipa_axum::routes!(
            marketplace_proposals,
            submit_marketplace_proposal
        ))
        .routes(utoipa_axum::routes!(marketplace_proposal))
        .routes(utoipa_axum::routes!(decide_marketplace_proposal))
        .routes(utoipa_axum::routes!(cancel_marketplace_proposal))
        .routes(utoipa_axum::routes!(withdraw_marketplace_entry))
        .routes(utoipa_axum::routes!(install_marketplace_entry))
        .routes(utoipa_axum::routes!(marketplace_installation))
}

#[utoipa::path(get, path="/me/marketplace-proposal-spaces", params(("after"=Option<Uuid>,Query)), responses(
    (status=200,body=ProposalSpacePage),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_proposal_spaces(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiQuery(query): ApiQuery<super::PageQuery>,
) -> AppResult<Json<ProposalSpacePage>> {
    let mut rows: Vec<SpaceRow> = sqlx::query_as(concat!(subject_spaces!(), "select s.id,s.kind,s.name,s.personal_owner,s.parent_id,s.organization_id
        from subject_spaces s where s.active and s.direct_roles && $3::text[]
        and exists(select 1 from organization_participants p where p.organization_id=s.organization_id)
        and s.id > $4 order by s.id limit 101"))
        .bind(&user.uid).bind(authorization::roles_granting(SpacePermission::CreatePersonalSpace))
        .bind(authorization::roles_granting(SpacePermission::Write)).bind(query.after.unwrap_or(Uuid::nil())).fetch_all(&s.pool).await?;
    let next_cursor = (rows.len() > PAGE_SIZE).then(|| rows[PAGE_SIZE - 1].id);
    rows.truncate(PAGE_SIZE);
    let items = rows
        .into_iter()
        .map(|row| {
            let space: Space = row.into();
            let mut resource_kinds = vec![MarketplaceKind::Prompt, MarketplaceKind::Skill];
            if crate::agent_instances::http::require_instance_space(space.kind).is_ok() {
                resource_kinds.push(MarketplaceKind::Agent);
            }
            ProposalSpace {
                resource_kinds,
                marketplace_space_ids: super::publication_destinations(&space),
                space,
            }
        })
        .collect();
    Ok(Json(ProposalSpacePage { items, next_cursor }))
}

#[utoipa::path(get,path="/spaces/{marketplace_space_id}/marketplace/entries",params(
    ("marketplace_space_id"=Uuid,Path),("after"=Option<Uuid>,Query),("kind"=Option<MarketplaceKind>,Query)),responses(
    (status=200,body=MarketplaceEntryPage),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_entries(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(catalogue): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<CatalogueQuery>,
) -> AppResult<Json<MarketplaceEntryPage>> {
    let mut tx = super::read_snapshot(&s.pool, &user.uid, catalogue).await?;
    let editor = store::can_write(&mut tx, &user.uid, Some(catalogue)).await?;
    let mut items: Vec<MarketplaceEntrySummary> = sqlx::query_as("select e.entry_id,e.marketplace_space_id,e.kind,p.proposal_id,
        e.publication_version,e.published_at,p.display_name,p.description,p.origin_name,p.package_hash,$4 as can_withdraw
        from marketplace_entry e join marketplace_proposal p on p.proposal_id=e.published_proposal_id
        where e.marketplace_space_id=$1 and e.entry_id>$2 and ($3::text is null or e.kind=$3) order by e.entry_id limit 101")
        .bind(catalogue).bind(query.after.unwrap_or(Uuid::nil())).bind(query.kind.map(MarketplaceKind::as_str))
        .bind(editor).fetch_all(&mut *tx).await?;
    let next_cursor = (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].entry_id);
    items.truncate(PAGE_SIZE);
    tx.commit().await?;
    Ok(Json(MarketplaceEntryPage { items, next_cursor }))
}

#[utoipa::path(get,path="/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}",params(
    ("marketplace_space_id"=Uuid,Path),("entry_id"=Uuid,Path)),responses(
    (status=200,body=MarketplaceEntryDetail),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_entry(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<MarketplaceEntryDetail>> {
    let mut tx = super::read_snapshot(&s.pool, &user.uid, catalogue).await?;
    let editor = store::can_write(&mut tx, &user.uid, Some(catalogue)).await?;
    let entry: MarketplaceEntrySummary=sqlx::query_as("select e.entry_id,e.marketplace_space_id,e.kind,p.proposal_id,
        e.publication_version,e.published_at,p.display_name,p.description,p.origin_name,p.package_hash,$3 as can_withdraw
        from marketplace_entry e join marketplace_proposal p on p.proposal_id=e.published_proposal_id
        where e.marketplace_space_id=$1 and e.entry_id=$2")
        .bind(catalogue).bind(id).bind(editor).fetch_optional(&mut *tx).await?.ok_or(AppError::NotFound)?;
    let package = store::package(&mut tx, entry.proposal_id).await?;
    tx.commit().await?;
    Ok(Json(MarketplaceEntryDetail { entry, package }))
}

#[utoipa::path(get,path="/spaces/{marketplace_space_id}/marketplace/proposals",params(
    ("marketplace_space_id"=Uuid,Path),("after"=Option<Uuid>,Query),("kind"=Option<MarketplaceKind>,Query),
    ("state"=Option<ProposalState>,Query),("proposing_space_id"=Option<Uuid>,Query)),responses(
    (status=200,body=ProposalPage),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_proposals(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(catalogue): ApiPath<Uuid>,
    ApiQuery(query): ApiQuery<ProposalQuery>,
) -> AppResult<Json<ProposalPage>> {
    let mut tx = super::read_snapshot(&s.pool, &user.uid, catalogue).await?;
    let editor = store::can_write(&mut tx, &user.uid, Some(catalogue)).await?;
    let mut items: Vec<ProposalSummary>=sqlx::query_as(concat!(subject_spaces!(), "select p.proposal_id,p.entry_id,p.marketplace_space_id,
        p.proposing_space_id,p.kind,p.origin_name,p.display_name,p.description,p.package_hash,p.submitted_by,p.submitted_at,p.state,
        p.decided_by,p.decided_at,p.decision_reason,e.publication_version,e.published_proposal_id,
        ($4 and p.state='pending') as can_decide,
        (p.state='pending' and exists(select 1 from subject_spaces a where a.id=p.proposing_space_id and a.active and a.direct_roles && $5::text[])) as can_cancel
        from marketplace_proposal p join marketplace_entry e using(entry_id)
        where p.marketplace_space_id=$3 and ($4 or exists(select 1 from subject_spaces a
            where a.id=p.proposing_space_id and a.active and a.direct_roles && $5::text[]))
        and p.proposal_id>$6 and ($7::text is null or p.kind=$7) and ($8::text is null or p.state=$8)
        and ($9::uuid is null or p.proposing_space_id=$9) order by p.proposal_id limit 101"))
        .bind(&user.uid).bind(authorization::roles_granting(SpacePermission::CreatePersonalSpace)).bind(catalogue)
        .bind(editor).bind(authorization::roles_granting(SpacePermission::Write)).bind(query.after.unwrap_or(Uuid::nil()))
        .bind(query.kind.map(MarketplaceKind::as_str)).bind(query.state.map(ProposalState::as_str)).bind(query.proposing_space_id)
        .fetch_all(&mut *tx).await?;
    let next_cursor = (items.len() > PAGE_SIZE).then(|| items[PAGE_SIZE - 1].proposal_id);
    items.truncate(PAGE_SIZE);
    tx.commit().await?;
    Ok(Json(ProposalPage { items, next_cursor }))
}

#[utoipa::path(get,path="/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}",params(
    ("marketplace_space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),responses(
    (status=200,body=MarketplaceProposal),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_proposal(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<MarketplaceProposal>> {
    let mut tx = super::read_snapshot(&s.pool, &user.uid, catalogue).await?;
    let proposal = store::proposal(&mut tx, &user.uid, catalogue, id).await?;
    let package = store::package(&mut tx, id).await?;
    tx.commit().await?;
    Ok(Json(MarketplaceProposal { proposal, package }))
}

#[utoipa::path(post,path="/spaces/{marketplace_space_id}/marketplace/proposals",params(
    ("marketplace_space_id"=Uuid,Path),("Idempotency-Key"=Uuid,Header)),request_body=SubmitProposalRequest,responses(
    (status=200,body=MarketplaceProposal),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
    (status=500,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn submit_marketplace_proposal(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(catalogue): ApiPath<Uuid>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<SubmitProposalRequest>,
) -> AppResult<Json<MarketplaceProposal>> {
    Ok(Json(
        store::submit(
            &s,
            &user,
            catalogue,
            idempotency_key(&headers)?,
            &body,
            headers.get(axum::http::header::AUTHORIZATION),
        )
        .await?,
    ))
}

#[utoipa::path(put,path="/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/decision",params(
    ("marketplace_space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),request_body=ProposalDecisionRequest,responses(
    (status=200,body=ProposalSummary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
    (status=500,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn decide_marketplace_proposal(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<ProposalDecisionRequest>,
) -> AppResult<Json<ProposalSummary>> {
    Ok(Json(
        store::decide(&s.pool, &user.uid, catalogue, id, &body).await?,
    ))
}

#[utoipa::path(put,path="/spaces/{marketplace_space_id}/marketplace/proposals/{proposal_id}/cancellation",params(
    ("marketplace_space_id"=Uuid,Path),("proposal_id"=Uuid,Path)),responses(
    (status=200,body=ProposalSummary),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
    (status=500,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn cancel_marketplace_proposal(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<ProposalSummary>> {
    Ok(Json(
        store::cancel(&s.pool, &user.uid, catalogue, id).await?,
    ))
}

#[utoipa::path(put,path="/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/withdrawal",params(
    ("marketplace_space_id"=Uuid,Path),("entry_id"=Uuid,Path)),request_body=WithdrawRequest,responses(
    (status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
    (status=500,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn withdraw_marketplace_entry(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<WithdrawRequest>,
) -> AppResult<StatusCode> {
    store::withdraw(
        &s.pool,
        &user.uid,
        catalogue,
        id,
        body.expected_publication_version,
    )
    .await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(post,path="/spaces/{marketplace_space_id}/marketplace/entries/{entry_id}/installations",params(
    ("marketplace_space_id"=Uuid,Path),("entry_id"=Uuid,Path),("Idempotency-Key"=Uuid,Header)),request_body=InstallRequest,responses(
    (status=200,body=InstallationReceipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),
    (status=500,body=crate::error::ErrorBody),(status=503,body=crate::error::ErrorBody)))]
async fn install_marketplace_entry(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((catalogue, id)): ApiPath<(Uuid, Uuid)>,
    headers: HeaderMap,
    ApiJson(body): ApiJson<InstallRequest>,
) -> AppResult<Json<InstallationReceipt>> {
    Ok(Json(
        store::install(
            &s,
            &user,
            catalogue,
            id,
            idempotency_key(&headers)?,
            &body,
            headers.get(axum::http::header::AUTHORIZATION),
        )
        .await?,
    ))
}

#[utoipa::path(get,path="/spaces/{space_id}/marketplace-installations/{installation_id}",params(
    ("space_id"=Uuid,Path),("installation_id"=Uuid,Path)),responses(
    (status=200,body=InstallationReceipt),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),
    (status=404,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody)))]
async fn marketplace_installation(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<InstallationReceipt>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let receipt = store::receipt(&mut tx, &user.uid, space, id).await?;
    tx.commit().await?;
    Ok(Json(receipt))
}
