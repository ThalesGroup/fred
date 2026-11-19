// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use crate::{
    api::AppState,
    authorization,
    domain::Permission,
    extract::{ApiJson, ApiPath},
    model_catalog::instance as models,
    onboarding::AdmittedUser,
    spaces,
};
use axum::{Json, extract::State, http::StatusCode};
use utoipa_axum::{router::OpenApiRouter, routes};

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(
            get_common_prompt_settings,
            put_common_prompt_settings
        ))
        .routes(routes!(
            get_creation_assistant_settings,
            patch_creation_assistant_settings,
            reset_creation_assistant_prompt
        ))
}

#[utoipa::path(get,path="/spaces/{organization_id}/prompt-settings/common",params(("organization_id"=Uuid,Path)),responses(
    (status=200,body=CommonPromptSettings),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody))) ]
async fn get_common_prompt_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<CommonPromptSettings>> {
    authorization::authorize_organization(&s.pool, &user.uid, id, Permission::Manage).await?;
    let defaults = defaults::read(&s.agent_catalog).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    authorization::authorize_organization(&mut *tx, &user.uid, id, Permission::Manage).await?;
    let saved = read(&mut *tx, id).await?;
    tx.commit().await?;
    Ok(Json(CommonPromptSettings {
        text: saved.common_text,
        updated_by: saved.common_updated_by,
        updated_at: saved.common_updated_at,
        defaults,
    }))
}

#[utoipa::path(put,path="/spaces/{organization_id}/prompt-settings/common",params(("organization_id"=Uuid,Path)),request_body=SetCommonPrompt,responses(
    (status=204),(status=400,body=crate::error::ErrorBody),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody))) ]
async fn put_common_prompt_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<SetCommonPrompt>,
) -> AppResult<StatusCode> {
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(id),
        Permission::Manage,
    )
    .await?;
    save_common(&mut tx, id, &user.uid, &body.text).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(get,path="/spaces/{organization_id}/prompt-settings/creation-assistant",params(("organization_id"=Uuid,Path)),responses(
    (status=200,body=CreationAssistantSettings),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody))) ]
async fn get_creation_assistant_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<Json<CreationAssistantSettings>> {
    authorization::authorize_organization(&s.pool, &user.uid, id, Permission::Manage).await?;
    let defaults = defaults::read(&s.agent_catalog).await?;
    let mut tx = s.pool.begin().await?;
    sqlx::query("set transaction isolation level repeatable read, read only")
        .execute(&mut *tx)
        .await?;
    authorization::authorize_organization(&mut *tx, &user.uid, id, Permission::Manage).await?;
    let saved = read(&mut *tx, id).await?;
    let model = saved.creation_model.map(|v| v.0);
    let models =
        models::resolve(&mut tx, id, &serde_json::json!({"recommended_model":model})).await?;
    tx.commit().await?;
    Ok(Json(CreationAssistantSettings {
        missing_language_placeholder: saved
            .creation_text
            .as_ref()
            .is_some_and(|text| !text.contains("{language}")),
        text: saved.creation_text,
        model,
        reasoning: saved.creation_reasoning,
        text_updated_by: saved.creation_text_updated_by,
        text_updated_at: saved.creation_text_updated_at,
        updated_by: saved.creation_updated_by,
        updated_at: saved.creation_updated_at,
        defaults,
        models,
    }))
}

#[utoipa::path(patch,path="/spaces/{organization_id}/prompt-settings/creation-assistant",params(("organization_id"=Uuid,Path)),request_body=PatchCreationAssistant,responses(
    (status=204),(status=400,body=crate::error::ErrorBody),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=422,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody))) ]
async fn patch_creation_assistant_settings(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
    ApiJson(body): ApiJson<PatchCreationAssistant>,
) -> AppResult<StatusCode> {
    let (mut tx, space) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(id),
        Permission::Manage,
    )
    .await?;
    if let Some(model) = &body.model {
        models::validate_write(
            &mut tx,
            &space,
            &serde_json::json!({"recommended_model":model}),
            true,
        )
        .await?;
    }
    save_creation(&mut tx, id, &user.uid, &body).await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}

#[utoipa::path(delete,path="/spaces/{organization_id}/prompt-settings/creation-assistant",params(("organization_id"=Uuid,Path)),responses(
    (status=204),(status=401,body=crate::error::ErrorBody),(status=403,body=crate::error::ErrorBody),(status=404,body=crate::error::ErrorBody),(status=409,body=crate::error::ErrorBody),(status=500,body=crate::error::ErrorBody))) ]
async fn reset_creation_assistant_prompt(
    State(s): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(id): ApiPath<Uuid>,
) -> AppResult<StatusCode> {
    let (mut tx, _) = spaces::governance_mutation(
        &s.pool,
        &user.uid,
        spaces::MutationTarget::Organization(id),
        Permission::Manage,
    )
    .await?;
    save_creation(
        &mut tx,
        id,
        &user.uid,
        &PatchCreationAssistant {
            text: Some(None),
            ..Default::default()
        },
    )
    .await?;
    tx.commit().await?;
    Ok(StatusCode::NO_CONTENT)
}
