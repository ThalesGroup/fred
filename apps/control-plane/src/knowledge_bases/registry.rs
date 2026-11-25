// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
//! The organization Owner registers a dedicated workload; deployment owns its secrets.
use super::*;
use crate::{
    authorization, domain,
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    roles::SpacePermission,
    spaces,
};
use axum::{Json as ResponseJson, extract::State, http::StatusCode};
use utoipa_axum::{router::OpenApiRouter, routes};

#[derive(Serialize, ToSchema, sqlx::FromRow)]
#[schema(as=KnowledgeBaseService)]
pub struct Service {
    pub runtime_id: String,
    pub organization_id: Uuid,
    pub issuer: String,
    pub client_id: String,
    pub audience: String,
    pub credential_bindings: Vec<String>,
    pub revision: i64,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
#[schema(as=RegisterKnowledgeBaseService)]
pub struct RegisterService {
    pub runtime_id: String,
    pub issuer: String,
    pub client_id: String,
    pub audience: String,
    #[serde(default)]
    pub credential_bindings: Vec<String>,
}
#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
#[schema(as=UpdateKnowledgeBaseService)]
pub struct UpdateService {
    pub expected_revision: i64,
    pub credential_bindings: Vec<String>,
}
const SELECT: &str = "select runtime_id,organization_id,issuer,client_id,audience,credential_bindings,revision from kb_service";
pub(super) async fn service(conn: &mut PgConnection, runtime: &str) -> AppResult<Service> {
    sqlx::query_as(sqlx::AssertSqlSafe(format!("{SELECT} where runtime_id=$1 and exists(select 1 from space where id=kb_service.organization_id and deletion_id is null)")))
        .bind(runtime)
        .fetch_optional(conn)
        .await?
        .ok_or(AppError::NotFound)
}
fn bindings(values: &[String]) -> AppResult<()> {
    if values.len() > 64
        || values
            .iter()
            .any(|v| domain::canonical_name(v, 128).as_deref() != Some(v))
        || values
            .iter()
            .collect::<std::collections::HashSet<_>>()
            .len()
            != values.len()
    {
        return Err(AppError::Unprocessable(
            "Invalid credential binding names.".into(),
        ));
    }
    Ok(())
}
#[utoipa::path(get,path="/organizations/{organization_id}/knowledge-base-services",params(("organization_id"=Uuid,Path)),responses((status=200,body=[Service]),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody)))]
async fn organization_knowledge_base_services(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
) -> AppResult<ResponseJson<Vec<Service>>> {
    authorization::authorize_organization(
        &s.pool,
        &user.uid,
        organization_id,
        SpacePermission::Manage,
    )
    .await?;
    Ok(ResponseJson(
        sqlx::query_as(sqlx::AssertSqlSafe(format!(
            "{SELECT} where organization_id=$1 order by runtime_id"
        )))
        .bind(organization_id)
        .fetch_all(&s.pool)
        .await?,
    ))
}
#[utoipa::path(post,path="/organizations/{organization_id}/knowledge-base-services",params(("organization_id"=Uuid,Path)),request_body=RegisterService,responses((status=201,body=Service),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn register_knowledge_base_service(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(organization_id): ApiPath<Uuid>,
    ApiJson(input): ApiJson<RegisterService>,
) -> AppResult<(StatusCode, ResponseJson<Service>)> {
    bindings(&input.credential_bindings)?;
    let issuer = input.issuer.trim_end_matches('/');
    if !domain::valid_logical_name(&input.runtime_id)
        || input.runtime_id == fred_rust_agent::DEFINITION.provider
        || s.agent_catalog
            .runtime_catalog_sources
            .iter()
            .any(|source| source.runtime_id == input.runtime_id)
        || domain::canonical_name(&input.client_id, 255).as_deref() != Some(&input.client_id)
        || domain::canonical_name(&input.audience, 255).as_deref() != Some(&input.audience)
        || !reqwest::Url::parse(issuer).is_ok_and(|url| {
            matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
                && url.as_str().trim_end_matches('/') == issuer
        })
    {
        return Err(AppError::Unprocessable(
            "Invalid collector identity.".into(),
        ));
    }
    // A collector cannot appropriate an identity already trusted for core processing.
    if s.agent_catalog
        .capability_preparation
        .workers
        .values()
        .chain(s.processing.iter().map(|p| &p.config.worker))
        .any(|w| w.issuer.trim_end_matches('/') == issuer && w.client_id == input.client_id)
    {
        return Err(AppError::Conflict(
            "Use a dedicated collector identity.".into(),
        ));
    }
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization_id),
        SpacePermission::Manage,
    )
    .await?;
    sqlx::query("insert into kb_service(runtime_id,organization_id,issuer,client_id,audience,credential_bindings) values($1,$2,$3,$4,$5,$6)").bind(&input.runtime_id).bind(organization_id).bind(issuer).bind(&input.client_id).bind(&input.audience).bind(&input.credential_bindings).execute(&mut *tx).await?;
    sqlx::query("insert into capability_source(source_id,origin,kb_service_id) values($1,'knowledge_base',$1)").bind(&input.runtime_id).execute(&mut *tx).await?;
    let registered = service(&mut tx, &input.runtime_id).await?;
    tx.commit().await?;
    Ok((StatusCode::CREATED, ResponseJson(registered)))
}
#[utoipa::path(put,path="/organizations/{organization_id}/knowledge-base-services/{runtime_id}",params(("organization_id"=Uuid,Path),("runtime_id"=String,Path)),request_body=UpdateService,responses((status=200,body=Service),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody)))]
async fn update_knowledge_base_service(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((organization_id, runtime)): ApiPath<(Uuid, String)>,
    ApiJson(input): ApiJson<UpdateService>,
) -> AppResult<ResponseJson<Service>> {
    bindings(&input.credential_bindings)?;
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(organization_id),
        SpacePermission::Manage,
    )
    .await?;
    let current = service(&mut tx, &runtime).await?;
    if current.organization_id != organization_id {
        return Err(AppError::NotFound);
    }
    if current.revision != input.expected_revision {
        return Err(AppError::Conflict(
            "Collector changed; refresh before saving.".into(),
        ));
    }
    sqlx::query(
        "update kb_service set credential_bindings=$2,revision=revision+1 where runtime_id=$1",
    )
    .bind(&runtime)
    .bind(input.credential_bindings)
    .execute(&mut *tx)
    .await?;
    let updated = service(&mut tx, &runtime).await?;
    tx.commit().await?;
    Ok(ResponseJson(updated))
}
pub(super) fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(
            organization_knowledge_base_services,
            register_knowledge_base_service
        ))
        .routes(routes!(update_knowledge_base_service))
}
