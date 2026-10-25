// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Personal display choices, available before consent and isolated by verified subject.
use axum::{Json, extract::State};
use serde::{Deserialize, Deserializer, Serialize};
use sqlx::PgPool;
use utoipa::ToSchema;
use utoipa_axum::{router::OpenApiRouter, routes};

use crate::{
    api::AppState,
    error::{AppError, AppResult},
    extract::ApiJson,
    onboarding::OwnUser,
};

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, ToSchema, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "text", rename_all = "lowercase")]
pub enum ThemeMode {
    Light,
    Dark,
    #[default]
    System,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, ToSchema, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "text", rename_all = "lowercase")]
pub enum Language {
    En,
    Fr,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, ToSchema, sqlx::Type)]
#[serde(rename_all = "lowercase")]
#[sqlx(type_name = "text", rename_all = "lowercase")]
pub enum TeamSortMode {
    #[default]
    Recent,
    Alpha,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, ToSchema, sqlx::Type)]
#[sqlx(type_name = "text")]
pub enum AgentSort {
    #[default]
    #[serde(rename = "name")]
    #[sqlx(rename = "name")]
    Name,
    #[serde(rename = "created_at:desc")]
    #[sqlx(rename = "created_at:desc")]
    CreatedAtDesc,
    #[serde(rename = "updated_at:desc")]
    #[sqlx(rename = "updated_at:desc")]
    UpdatedAtDesc,
}

#[derive(Debug, Default, Serialize, ToSchema, sqlx::FromRow)]
pub struct UserPreferences {
    pub initialized: bool,
    pub ui_theme_id: Option<String>,
    pub theme_mode: ThemeMode,
    pub language: Option<Language>,
    pub sidebar_collapsed: bool,
    pub team_sort_mode: TeamSortMode,
    pub agent_sort: AgentSort,
}

/// Omitted fields are preserved; explicit null restores the field's default.
#[derive(Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PatchUserPreferences {
    #[serde(default, deserialize_with = "present")]
    #[schema(pattern = "^[a-z][a-z0-9-]{0,31}$")]
    pub ui_theme_id: Option<Option<String>>,
    #[serde(default, deserialize_with = "present")]
    pub theme_mode: Option<Option<ThemeMode>>,
    #[serde(default, deserialize_with = "present")]
    pub language: Option<Option<Language>>,
    #[serde(default, deserialize_with = "present")]
    pub sidebar_collapsed: Option<Option<bool>>,
    #[serde(default, deserialize_with = "present")]
    pub team_sort_mode: Option<Option<TeamSortMode>>,
    #[serde(default, deserialize_with = "present")]
    pub agent_sort: Option<Option<AgentSort>>,
}

fn present<'de, D, T>(deserializer: D) -> Result<Option<Option<T>>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    Option::<T>::deserialize(deserializer).map(Some)
}

impl PatchUserPreferences {
    fn validate(&self) -> AppResult<()> {
        if self.ui_theme_id.is_none()
            && self.theme_mode.is_none()
            && self.language.is_none()
            && self.sidebar_collapsed.is_none()
            && self.team_sort_mode.is_none()
            && self.agent_sort.is_none()
        {
            return Err(AppError::Unprocessable(
                "at least one preference is required".into(),
            ));
        }
        if let Some(Some(id)) = &self.ui_theme_id
            && (!(1..=32).contains(&id.len())
                || !id.as_bytes()[0].is_ascii_lowercase()
                || !id
                    .bytes()
                    .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-'))
        {
            return Err(AppError::Unprocessable("invalid theme ID".into()));
        }
        Ok(())
    }
}

async fn get(pool: &PgPool, uid: &str) -> AppResult<UserPreferences> {
    Ok(sqlx::query_as::<_, UserPreferences>(
        "SELECT true AS initialized, ui_theme_id, theme_mode, language,
                sidebar_collapsed, team_sort_mode, agent_sort
         FROM users_preferences WHERE user_id = $1",
    )
    .bind(uid)
    .fetch_optional(pool)
    .await?
    .unwrap_or_default())
}

async fn patch(
    pool: &PgPool,
    uid: &str,
    patch: PatchUserPreferences,
) -> AppResult<UserPreferences> {
    patch.validate()?;
    // The upsert merges only submitted columns under PostgreSQL's row lock.
    // Concurrent changes to distinct preferences cannot overwrite one another.
    Ok(sqlx::query_as::<_, UserPreferences>(
        "INSERT INTO users_preferences
            (user_id, ui_theme_id, theme_mode, language, sidebar_collapsed, team_sort_mode, agent_sort)
         VALUES ($1, $2, $3, $4, $5, $6, $7)
         ON CONFLICT (user_id) DO UPDATE SET
            ui_theme_id = CASE WHEN $8 THEN EXCLUDED.ui_theme_id ELSE users_preferences.ui_theme_id END,
            theme_mode = CASE WHEN $9 THEN EXCLUDED.theme_mode ELSE users_preferences.theme_mode END,
            language = CASE WHEN $10 THEN EXCLUDED.language ELSE users_preferences.language END,
            sidebar_collapsed = CASE WHEN $11 THEN EXCLUDED.sidebar_collapsed ELSE users_preferences.sidebar_collapsed END,
            team_sort_mode = CASE WHEN $12 THEN EXCLUDED.team_sort_mode ELSE users_preferences.team_sort_mode END,
            agent_sort = CASE WHEN $13 THEN EXCLUDED.agent_sort ELSE users_preferences.agent_sort END,
            updated_at = now()
         RETURNING true AS initialized, ui_theme_id, theme_mode, language,
                   sidebar_collapsed, team_sort_mode, agent_sort",
    )
    .bind(uid)
    .bind(patch.ui_theme_id.as_ref().and_then(|value| value.as_deref()))
    .bind(patch.theme_mode.flatten().unwrap_or_default())
    .bind(patch.language.flatten())
    .bind(patch.sidebar_collapsed.flatten().unwrap_or_default())
    .bind(patch.team_sort_mode.flatten().unwrap_or_default())
    .bind(patch.agent_sort.flatten().unwrap_or_default())
    .bind(patch.ui_theme_id.is_some())
    .bind(patch.theme_mode.is_some())
    .bind(patch.language.is_some())
    .bind(patch.sidebar_collapsed.is_some())
    .bind(patch.team_sort_mode.is_some())
    .bind(patch.agent_sort.is_some())
    .fetch_one(pool)
    .await?)
}

#[utoipa::path(get, path = "/users/me/preferences", responses(
    (status = 200, body = UserPreferences),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn get_my_preferences(
    State(s): State<AppState>,
    OwnUser(user): OwnUser,
) -> AppResult<Json<UserPreferences>> {
    Ok(Json(get(&s.pool, &user.uid).await?))
}

#[utoipa::path(patch, path = "/users/me/preferences", request_body = PatchUserPreferences, responses(
    (status = 200, body = UserPreferences),
    (status = 401, body = crate::error::ErrorBody),
    (status = 403, body = crate::error::ErrorBody),
    (status = 422, body = crate::error::ErrorBody),
    (status = 500, body = crate::error::ErrorBody)
))]
async fn patch_my_preferences(
    State(s): State<AppState>,
    OwnUser(user): OwnUser,
    ApiJson(body): ApiJson<PatchUserPreferences>,
) -> AppResult<Json<UserPreferences>> {
    Ok(Json(patch(&s.pool, &user.uid, body).await?))
}

pub fn routes() -> OpenApiRouter<AppState> {
    OpenApiRouter::new().routes(routes!(get_my_preferences, patch_my_preferences))
}
