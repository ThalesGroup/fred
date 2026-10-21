// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Python users.service.search_users and its local identity directory.
//! Profiles are display data; authorization remains in OpenFGA.
use crate::{
    auth::CurrentUser,
    error::{AppError, AppResult},
    keycloak,
    onboarding::AdmissionState,
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::{collections::VecDeque, sync::LazyLock, time::{Duration, Instant}};
use tokio::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Default, Deserialize, utoipa::ToSchema, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum DirectoryKind {
    #[default]
    Keycloak,
    Local,
}

/// Only identity classification is needed here, not delegated grant acceptance.
/// These are the existing Python security.delegation claim settings.
#[derive(Debug, Clone, Deserialize, utoipa::ToSchema)]
#[serde(default)]
pub struct DirectoryDelegation {
    pub audience: String,
    pub caller_role: String,
    pub caller_roles_claim: Option<Vec<String>>,
}
impl Default for DirectoryDelegation {
    fn default() -> Self {
        Self { audience: "fred-delegation".into(), caller_role: "delegation_caller".into(), caller_roles_claim: None }
    }
}
impl DirectoryDelegation {
    pub fn validated(&self) -> anyhow::Result<Self> {
        let identifier = |value: &str| -> anyhow::Result<String> {
            let value = value.trim();
            anyhow::ensure!((1..=256).contains(&value.chars().count()), "invalid security.delegation identifier");
            Ok(value.to_owned())
        };
        let caller_roles_claim = self.caller_roles_claim.as_ref().map(|path| {
            anyhow::ensure!(!path.is_empty(), "security.delegation.caller_roles_claim must not be empty");
            path.iter().map(|part| identifier(part)).collect::<anyhow::Result<Vec<_>>>()
        }).transpose()?;
        Ok(Self { audience: identifier(&self.audience)?, caller_role: identifier(&self.caller_role)?, caller_roles_claim })
    }

    pub fn roles_path(&self) -> Vec<String> {
        self.caller_roles_claim.clone().filter(|path| !path.is_empty())
            .unwrap_or_else(|| vec!["resource_access".into(), self.audience.clone(), "roles".into()])
    }
}

#[derive(Serialize, sqlx::FromRow, utoipa::ToSchema)]
pub struct UserSummary {
    pub id: String,
    pub username: Option<String>,
    pub first_name: Option<String>,
    pub last_name: Option<String>,
    pub email: Option<String>,
    pub avatar_image_url: Option<String>,
}

impl UserSummary {
    pub(crate) fn from_raw(raw: &serde_json::Value) -> Option<Self> {
        let id = raw.get("id")?.as_str()?.to_owned();
        if id.is_empty() { return None; }
        let field = |name| raw.get(name).filter(|v| !v.is_null()).and_then(|v| {
            let text = v.as_str().map(str::to_owned).unwrap_or_else(|| v.to_string());
            let text = text.trim();
            (!text.is_empty()).then(|| text.to_owned())
        });
        Some(Self { id, username: field("username"), first_name: field("firstName"),
            last_name: field("lastName"), email: field("email"), avatar_image_url: None })
    }
}

pub enum Directory<'a> {
    Keycloak(Option<&'a keycloak::Directory>),
    Local(&'a PgPool),
}

impl Directory<'_> {
    pub async fn search(&self, query: &str) -> AppResult<Vec<UserSummary>> {
        let query = query.trim();
        // Match the service guard, not only HTTP validation: whitespace must not list users.
        if query.chars().count() < 2 { return Ok(Vec::new()); }
        match self {
            Self::Keycloak(Some(directory)) => Ok(directory.search(query).await?),
            Self::Keycloak(None) => Ok(Vec::new()),
            Self::Local(pool) => Ok(sqlx::query_as(
                "select id::text as id, username, email, first_name, last_name, null::text as avatar_image_url from user_identity where username ilike $1 or email ilike $1 or first_name ilike $1 or last_name ilike $1 order by username, id limit 20"
            ).bind(format!("%{query}%")).fetch_all(*pool).await?),
        }
    }

    pub async fn find_username(&self, username: &str) -> AppResult<Option<keycloak::User>> {
        match self {
            Self::Keycloak(Some(directory)) => Ok(directory.find_username(username).await?),
            Self::Keycloak(None) => Err(AppError::Unavailable("user directory is not configured".into())),
            Self::Local(pool) => {
                // Never choose arbitrarily when distinct subjects share a username.
                let rows: Vec<(String, String)> = sqlx::query_as(
                    "select id::text, username from user_identity where username = $1 order by id limit 2"
                ).bind(username).fetch_all(*pool).await?;
                if rows.len() > 1 {
                    return Err(AppError::Unprocessable("username is ambiguous".into()));
                }
                Ok(rows.into_iter().next().map(|(id, username)| keycloak::User { id, username }))
            }
        }
    }
}

// Same bounded ten-minute snapshot cache as Python. No network/SQL awaits under the mutex.
static SNAPSHOTS: LazyLock<Mutex<VecDeque<(String, Uuid, Instant)>>> = LazyLock::new(|| Mutex::new(VecDeque::new()));
pub async fn snapshot(admission: &AdmissionState, user: &CurrentUser) {
    if admission.user_directory != DirectoryKind::Local || !admission.auth.enabled()
        || user.username.is_empty() || user.service_account || user.delegation_caller
        || user.roles.iter().any(|role| role == "service_agent") {
        return;
    }
    let Ok(id) = Uuid::parse_str(&user.uid) else { return; };
    let database = admission.pool.connect_options().get_database().unwrap_or_default().to_owned();
    let now = Instant::now();
    {
        let mut cache = SNAPSHOTS.lock().await;
        if cache.iter().any(|(db, uid, deadline)| db == &database && *uid == id && *deadline > now) { return; }
        cache.retain(|(db, uid, _)| db != &database || *uid != id);
        cache.push_back((database.clone(), id, now + Duration::from_secs(600)));
        if cache.len() > 2048 { cache.pop_front(); }
    }
    let result = sqlx::query("insert into user_identity (id, username, email, first_name, last_name) values ($1,$2,$3,$4,$5) on conflict (id) do update set username=excluded.username, email=excluded.email, first_name=excluded.first_name, last_name=excluded.last_name, last_seen_at=now()")
        .bind(id).bind(&user.username).bind(&user.email).bind(&user.first_name).bind(&user.last_name)
        .execute(&admission.pool).await;
    if result.is_err() {
        SNAPSHOTS.lock().await.retain(|(db, uid, _)| db != &database || *uid != id);
        tracing::warn!("[AUTH] Local identity snapshot failed");
    }
}
