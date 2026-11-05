// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Global packaged-skill state, read from PostgreSQL at each turn admission.

use axum::{Json, extract::State, http::header, response::IntoResponse};
use serde::{Deserialize, Serialize};
use sqlx::{PgPool, Postgres, Transaction};
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};

use crate::{
    agents::skills::{self, PlatformSkillInventory},
    api::AppState,
    authorization,
    error::{AppError, AppResult},
    extract::{ApiJson, ApiPath},
    onboarding::AdmittedUser,
    roles::PlatformPermission,
};

#[derive(Serialize, ToSchema)]
pub struct SkillPolicy {
    pub disabled_skill_names: Vec<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetSkillEnabled {
    pub enabled: bool,
}

#[derive(Serialize, ToSchema)]
pub struct SkillEnabled {
    pub name: String,
    pub enabled: bool,
}

#[utoipa::path(get, path = "/platform/skills", responses(
    (status = 200, body = PlatformSkillInventory),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody),
    (status = 503, body = crate::error::ErrorBody)
))]
async fn get_skills(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<impl IntoResponse> {
    authorization::require_platform(
        &state.pool,
        &user.uid,
        PlatformPermission::ManageCapabilities,
    )
    .await?;
    let inventory = skills::platform_inventory(&state).await?;
    authorization::require_platform(
        &state.pool,
        &user.uid,
        PlatformPermission::ManageCapabilities,
    )
    .await?;
    Ok(([(header::CACHE_CONTROL, "no-store")], Json(inventory)))
}

fn valid_name(name: &str) -> bool {
    (1..=64).contains(&name.len())
        && name.split('-').all(|part| {
            !part.is_empty()
                && part
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit())
        })
}

pub async fn disabled(pool: &PgPool) -> AppResult<Vec<String>> {
    Ok(
        sqlx::query_scalar(
            "select name from platform_skill_policy where not enabled order by name",
        )
        .fetch_all(pool)
        .await?,
    )
}

pub async fn disabled_in(tx: &mut Transaction<'_, Postgres>) -> AppResult<Vec<String>> {
    Ok(
        sqlx::query_scalar(
            "select name from platform_skill_policy where not enabled order by name",
        )
        .fetch_all(&mut **tx)
        .await?,
    )
}

#[utoipa::path(get, path = "/platform/skills/policy", responses(
    (status = 200, body = SkillPolicy),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn get_policy(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
) -> AppResult<impl IntoResponse> {
    authorization::require_platform(
        &state.pool,
        &user.uid,
        PlatformPermission::ManageCapabilities,
    )
    .await?;
    Ok((
        [(header::CACHE_CONTROL, "no-store")],
        Json(SkillPolicy {
            disabled_skill_names: disabled(&state.pool).await?,
        }),
    ))
}

#[utoipa::path(put, path = "/platform/skills/{name}", params(
    ("name" = String, Path)
), request_body = SetSkillEnabled, responses(
    (status = 200, body = SkillEnabled),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn set_skill(
    State(state): State<AppState>,
    AdmittedUser(user): AdmittedUser,
    ApiPath(name): ApiPath<String>,
    ApiJson(body): ApiJson<SetSkillEnabled>,
) -> AppResult<Json<SkillEnabled>> {
    if !valid_name(&name) {
        return Err(AppError::Unprocessable("Invalid skill name".into()));
    }
    authorization::require_platform(
        &state.pool,
        &user.uid,
        PlatformPermission::ManageCapabilities,
    )
    .await?;
    let known_recovery = body.enabled
        && sqlx::query_scalar::<_, bool>(
            "select enabled from platform_skill_policy where name = $1",
        )
        .bind(&name)
        .fetch_optional(&state.pool)
        .await?
        .is_some();
    if !known_recovery {
        let inventory = skills::platform_inventory(&state).await?;
        if !body.enabled && !inventory.unsupported_runtime_ids.is_empty() {
            return Err(AppError::Conflict(
                "Upgrade all runtime sources before disabling platform skills".into(),
            ));
        }
        if !body.enabled && !inventory.unavailable_runtime_ids.is_empty() {
            return Err(AppError::Unavailable(
                "All runtime sources must be reachable before disabling platform skills".into(),
            ));
        }
        if !inventory
            .skills
            .iter()
            .any(|entry| entry.skill.name == name)
        {
            return Err(AppError::NotFound);
        }
    }
    let mut tx = state.pool.begin().await?;
    authorization::require_platform(&mut *tx, &user.uid, PlatformPermission::ManageCapabilities)
        .await?;
    sqlx::query(
        "insert into platform_skill_policy(name, enabled, updated_by)
         values ($1, $2, $3)
         on conflict (name) do update set enabled=excluded.enabled,
             updated_by=excluded.updated_by, updated_at=now()",
    )
    .bind(&name)
    .bind(body.enabled)
    .bind(&user.uid)
    .execute(&mut *tx)
    .await?;
    tx.commit().await?;
    tracing::info!(
        target: "fred.security.audit",
        audit_event = "platform.skill.activation_updated",
        actor_uid = %user.uid,
        skill_name = %name,
        enabled = body.enabled
    );
    Ok(Json(SkillEnabled {
        name,
        enabled: body.enabled,
    }))
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new()
        .routes(routes!(get_skills))
        .routes(routes!(get_policy))
        .routes(routes!(set_skill))
}

#[cfg(test)]
mod tests {
    use super::valid_name;

    #[test]
    fn packaged_names_are_canonical() {
        assert!(valid_name("graph"));
        assert!(valid_name("meeting-minutes"));
        for name in ["", "-graph", "graph-", "graph--view", "Graph", "../graph"] {
            assert!(!valid_name(name));
        }
    }
}
