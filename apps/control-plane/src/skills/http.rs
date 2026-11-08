// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{PackageSummary, SkillCatalog, SkillDetail, SpaceSkill, package::Files};
use crate::{
    api::AppState,
    authorization,
    domain::Permission,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    spaces,
};
use axum::{Json, extract::State, http::StatusCode};
use serde::{Deserialize, Serialize};
use sqlx::types::Json as SqlJson;
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PutSkill {
    pub files: Files,
    pub expected_revision: Option<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateSkill {
    pub name: String,
    pub files: Files,
}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(default_skills))
        .routes(utoipa_axum::routes!(list_skills, create_skill))
        .routes(utoipa_axum::routes!(skill_scope))
        .routes(utoipa_axum::routes!(get_skill, put_skill, delete_skill))
        .routes(utoipa_axum::routes!(install_skill))
        .routes(utoipa_axum::routes!(preview_skill))
        .layer(axum::extract::DefaultBodyLimit::max(5 * 1024 * 1024))
}

#[utoipa::path(get, path="/skills/defaults", responses(
        (status=200, body=Vec<PackageSummary>),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn default_skills(AdmittedUser(_user): AdmittedUser) -> AppResult<Json<Vec<PackageSummary>>> {
    Ok(Json(
        super::defaults::packages()
            .into_iter()
            .map(|(name, files)| super::package::validate(name, &files, true))
            .collect::<AppResult<_>>()?,
    ))
}

#[utoipa::path(get, path="/spaces/{space_id}/skills", params(("space_id"=Uuid, Path)), responses(
        (status=200, body=Vec<SpaceSkill>),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn list_skills(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
) -> AppResult<Json<Vec<SpaceSkill>>> {
    authorization::authorize(&s.pool, &user.uid, space, Permission::Read).await?;
    Ok(Json(super::list(&s.pool, space).await?))
}

#[utoipa::path(post, path="/spaces/{space_id}/skills", params(("space_id"=Uuid, Path)), request_body=CreateSkill, responses(
        (status=204),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn create_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
    ApiJson(body): ApiJson<CreateSkill>,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space, Permission::Write).await?;
    super::save(
        &mut tx,
        space,
        &user.uid,
        &body.name,
        &body.files,
        None,
        false,
    )
    .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(get, path="/spaces/{space_id}/skills/scope", params(("space_id"=Uuid, Path)), responses(
        (status=200, body=SkillCatalog),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn skill_scope(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(space): ApiPath<Uuid>,
) -> AppResult<Json<SkillCatalog>> {
    let space = authorization::authorize(&s.pool, &user.uid, space, Permission::Read).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let snapshot = super::resolve(&mut tx, &user.uid, &space, false).await?;
    tx.commit().await?;
    Ok(Json(snapshot.catalog))
}

#[utoipa::path(get, path="/spaces/{space_id}/skills/{skill_id}", params(("space_id"=Uuid, Path), ("skill_id"=Uuid, Path)), responses(
        (status=200, body=PutSkill),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn get_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, skill_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<PutSkill>> {
    authorization::authorize(&s.pool, &user.uid, space, Permission::Read).await?;
    let row: Option<(SqlJson<Files>, String)> =
        sqlx::query_as("select files, revision from skill where space_id=$1 and skill_id=$2")
            .bind(space)
            .bind(skill_id)
            .fetch_optional(&s.pool)
            .await?;
    let (files, revision) = row.ok_or(AppError::NotFound)?;
    Ok(Json(PutSkill {
        files: files.0,
        expected_revision: Some(revision),
    }))
}

#[utoipa::path(put, path="/spaces/{space_id}/skills/{skill_id}", params(("space_id"=Uuid, Path), ("skill_id"=Uuid, Path)), request_body=PutSkill, responses(
        (status=204),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn put_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, skill_id)): ApiPath<(Uuid, Uuid)>,
    ApiJson(body): ApiJson<PutSkill>,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space, Permission::Write).await?;
    let name: String =
        sqlx::query_scalar("select name from skill where space_id=$1 and skill_id=$2")
            .bind(space)
            .bind(skill_id)
            .fetch_optional(&mut *tx)
            .await?
            .ok_or(AppError::NotFound)?;
    super::save(
        &mut tx,
        space,
        &user.uid,
        &name,
        &body.files,
        body.expected_revision.as_deref(),
        false,
    )
    .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(post, path="/spaces/{space_id}/skills/packages/{name}/install", params(("space_id"=Uuid, Path), ("name"=String, Path)), responses(
        (status=204),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn install_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, name)): ApiPath<(Uuid, String)>,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space, Permission::Write).await?;
    let (_, files) = super::defaults::packages()
        .into_iter()
        .find(|(n, _)| *n == name)
        .ok_or(AppError::NotFound)?;
    super::save(&mut tx, space, &user.uid, &name, &files, None, true).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(delete, path="/spaces/{space_id}/skills/{skill_id}", params(("space_id"=Uuid, Path), ("skill_id"=Uuid, Path)), responses(
        (status=204),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn delete_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, skill_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<StatusCode> {
    let (mut tx, _) =
        spaces::authorized_mutation(&s.pool, &user.uid, space, Permission::Write).await?;
    if sqlx::query("delete from skill where space_id=$1 and skill_id=$2")
        .bind(space)
        .bind(skill_id)
        .execute(&mut *tx)
        .await?
        .rows_affected()
        == 0
    {
        return Err(AppError::NotFound);
    }
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(get, path="/spaces/{space_id}/skills/scope/{skill_id}", params(("space_id"=Uuid, Path), ("skill_id"=Uuid, Path)), responses(
        (status=200, body=SkillDetail),
        (status = 400, body = crate::error::ErrorBody),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 422, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    ))]
async fn preview_skill(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath((space, skill_id)): ApiPath<(Uuid, Uuid)>,
) -> AppResult<Json<SkillDetail>> {
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    let space = authorization::authorize(&mut *tx, &user.uid, space, Permission::Read).await?;
    let mut snapshot = super::resolve(&mut tx, &user.uid, &space, true).await?;
    let skill = snapshot
        .catalog
        .skills
        .into_iter()
        .find(|s| s.skill_id == skill_id)
        .ok_or(AppError::NotFound)?;
    let content = snapshot
        .files
        .remove(&format!("/skills/{skill_id}/SKILL.md"))
        .ok_or(AppError::NotFound)?;
    tx.commit().await?;
    Ok(Json(SkillDetail {
        skill,
        content,
        revision: snapshot.catalog.revision,
    }))
}
