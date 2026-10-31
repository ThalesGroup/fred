// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Python users.service.search_users and its local identity directory.
//! Profiles are display data; authorization uses the separate SQL role tables.
use crate::{
    auth::CurrentUser,
    error::{AppError, AppResult},
    keycloak,
    onboarding::AdmissionState,
};
use futures::{StreamExt, TryStreamExt};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::{
    collections::{BTreeSet, HashMap, VecDeque},
    sync::LazyLock,
    time::{Duration, Instant},
};
use tokio::sync::Mutex;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, Default, Deserialize, utoipa::ToSchema, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum DirectoryKind {
    #[default]
    Keycloak,
    Local,
}

/// Shared identity classification and runtime-resolver delegation settings.
/// Names and defaults match Python security.delegation; acceptance is route-scoped.
#[derive(Debug, Clone, Deserialize, utoipa::ToSchema)]
#[serde(default, deny_unknown_fields)]
pub struct DirectoryDelegation {
    /// Accept person/run/agent assertions at runtime and decision endpoints.
    pub accept_delegated_calls: bool,
    /// Keycloak client-credentials markers are mandatory when enabled.
    pub service_accounts_only: bool,
    /// Human login clients, in addition to security.user.client_id, cannot delegate.
    pub user_clients: Vec<String>,
    pub audience: String,
    pub caller_role: String,
    pub caller_roles_claim: Option<Vec<String>>,
}
impl Default for DirectoryDelegation {
    fn default() -> Self {
        Self {
            accept_delegated_calls: false,
            service_accounts_only: false,
            user_clients: Vec::new(),
            audience: "fred-delegation".into(),
            caller_role: "delegation_caller".into(),
            caller_roles_claim: None,
        }
    }
}
impl DirectoryDelegation {
    pub fn validated(&self) -> anyhow::Result<Self> {
        let identifier = |value: &str| -> anyhow::Result<String> {
            let value = value.trim();
            anyhow::ensure!(
                (1..=256).contains(&value.chars().count()),
                "invalid security.delegation identifier"
            );
            Ok(value.to_owned())
        };
        let caller_roles_claim = self
            .caller_roles_claim
            .as_ref()
            .map(|path| {
                anyhow::ensure!(
                    !path.is_empty(),
                    "security.delegation.caller_roles_claim must not be empty"
                );
                path.iter()
                    .map(|part| identifier(part))
                    .collect::<anyhow::Result<Vec<_>>>()
            })
            .transpose()?;
        Ok(Self {
            accept_delegated_calls: self.accept_delegated_calls,
            service_accounts_only: self.service_accounts_only,
            user_clients: self
                .user_clients
                .iter()
                .map(|client| identifier(client))
                .collect::<anyhow::Result<Vec<_>>>()?,
            audience: identifier(&self.audience)?,
            caller_role: identifier(&self.caller_role)?,
            caller_roles_claim,
        })
    }

    pub fn roles_path(&self) -> Vec<String> {
        self.caller_roles_claim
            .clone()
            .filter(|path| !path.is_empty())
            .unwrap_or_else(|| {
                vec![
                    "resource_access".into(),
                    self.audience.clone(),
                    "roles".into(),
                ]
            })
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
    /// A subject without display fields, when the directory cannot describe it.
    pub fn id_only(id: &str) -> Self {
        Self {
            id: id.to_owned(),
            username: None,
            first_name: None,
            last_name: None,
            email: None,
            avatar_image_url: None,
        }
    }

    pub(crate) fn from_raw(raw: &serde_json::Value) -> Option<Self> {
        let id = raw.get("id")?.as_str()?.to_owned();
        if id.is_empty() {
            return None;
        }
        let field = |name| {
            raw.get(name).filter(|v| !v.is_null()).and_then(|v| {
                let text = v
                    .as_str()
                    .map(str::to_owned)
                    .unwrap_or_else(|| v.to_string());
                let text = text.trim();
                (!text.is_empty()).then(|| text.to_owned())
            })
        };
        Some(Self {
            id,
            username: field("username"),
            first_name: field("firstName"),
            last_name: field("lastName"),
            email: field("email"),
            avatar_image_url: None,
        })
    }

    /// "First Last", else the username.
    pub fn display_name(&self) -> Option<String> {
        let full = [self.first_name.as_deref(), self.last_name.as_deref()]
            .into_iter()
            .flatten()
            .collect::<Vec<_>>()
            .join(" ");
        if full.is_empty() {
            self.username.clone()
        } else {
            Some(full)
        }
    }
}

/// Bound on concurrent Keycloak profile reads for one request.
const PROFILE_CONCURRENCY: usize = 8;

pub enum Directory<'a> {
    Keycloak(Option<&'a keycloak::Directory>),
    Local(&'a PgPool),
}

impl Directory<'_> {
    pub async fn search(&self, query: &str) -> AppResult<Vec<UserSummary>> {
        let query = query.trim();
        // Match the service guard, not only HTTP validation: whitespace must not list users.
        if query.chars().count() < 2 {
            return Ok(Vec::new());
        }
        match self {
            Self::Keycloak(Some(directory)) => Ok(directory.search(query).await?),
            Self::Keycloak(None) => Ok(Vec::new()),
            // A literal, case-insensitive prefix of one field, served by the prefix indexes.
            // Unnamed statements are planned with the pattern, so the indexes stay usable.
            Self::Local(pool) => Ok(sqlx::query_as(
                "select id::text as id, username, email, first_name, last_name, null::text as avatar_image_url from user_identity where lower(username) like lower($1) escape '\\' or lower(email) like lower($1) escape '\\' or lower(first_name) like lower($1) escape '\\' or lower(last_name) like lower($1) escape '\\' order by username, id limit 20"
            )
            .persistent(false)
            .bind(format!("{}%", like_literal(query)))
            .fetch_all(*pool)
            .await?),
        }
    }

    /// Display names of the subjects this directory knows; unknown ones are absent.
    pub async fn display_names(
        &self,
        subjects: BTreeSet<String>,
    ) -> AppResult<HashMap<String, String>> {
        match self {
            Self::Keycloak(None) => Ok(HashMap::new()),
            Self::Keycloak(Some(directory)) => {
                let profiles: Vec<Option<UserSummary>> = futures::stream::iter(subjects)
                    .map(|subject| async move { directory.user(&subject).await })
                    .buffer_unordered(PROFILE_CONCURRENCY)
                    .try_collect()
                    .await?;
                Ok(profiles
                    .into_iter()
                    .flatten()
                    .filter_map(|user| {
                        let name = user.display_name()?;
                        Some((user.id, name))
                    })
                    .collect())
            }
            Self::Local(pool) => {
                // Subjects are UUIDs here; parse to keep the primary-key lookup.
                let ids: HashMap<Uuid, &String> = subjects
                    .iter()
                    .filter_map(|s| Some((Uuid::parse_str(s).ok()?, s)))
                    .collect();
                let rows: Vec<(Uuid, String)> = sqlx::query_as(
                    "select id, coalesce(nullif(trim(concat_ws(' ', first_name, last_name)), ''), username)
                     from user_identity where id = any($1)",
                )
                .bind(ids.keys().copied().collect::<Vec<_>>())
                .fetch_all(*pool)
                .await?;
                Ok(rows
                    .into_iter()
                    .filter_map(|(id, name)| Some((ids.get(&id)?.to_string(), name)))
                    .collect())
            }
        }
    }

    /// Whether a subject is a known identity of this directory; not a lease on it.
    pub async fn exists(&self, subject: &str) -> AppResult<bool> {
        match self {
            Self::Keycloak(Some(directory)) => Ok(directory.exists(subject).await?),
            Self::Keycloak(None) => Err(AppError::Unavailable(
                "user directory is not configured".into(),
            )),
            Self::Local(pool) => match Uuid::parse_str(subject) {
                Ok(id) => Ok(sqlx::query_scalar(
                    "select exists(select 1 from user_identity where id = $1)",
                )
                .bind(id)
                .fetch_one(*pool)
                .await?),
                Err(_) => Ok(false),
            },
        }
    }

    /// Display summaries of known subjects, in order. A subject the directory no longer
    /// knows keeps an id-only summary rather than disappearing from governance views.
    pub async fn summaries(&self, subjects: &[String]) -> AppResult<Vec<UserSummary>> {
        let known: Vec<UserSummary> = match self {
            // Governance rosters are a few accounts: one lookup each, in order.
            Self::Keycloak(Some(directory)) => {
                let mut found = Vec::with_capacity(subjects.len());
                for subject in subjects {
                    found.extend(directory.user(subject).await?);
                }
                found
            }
            Self::Keycloak(None) => Vec::new(),
            Self::Local(pool) => {
                let ids: Vec<Uuid> = subjects.iter().filter_map(|s| s.parse().ok()).collect();
                sqlx::query_as("select id::text as id, username, email, first_name, last_name, null::text as avatar_image_url from user_identity where id = any($1)")
                    .bind(&ids)
                    .fetch_all(*pool)
                    .await?
            }
        };
        let mut known: std::collections::HashMap<String, UserSummary> =
            known.into_iter().map(|u| (u.id.clone(), u)).collect();
        Ok(subjects
            .iter()
            .map(|id| known.remove(id).unwrap_or_else(|| UserSummary::id_only(id)))
            .collect())
    }

    pub async fn find_username(&self, username: &str) -> AppResult<Option<keycloak::User>> {
        match self {
            Self::Keycloak(Some(directory)) => Ok(directory.find_username(username).await?),
            Self::Keycloak(None) => Err(AppError::Unavailable(
                "user directory is not configured".into(),
            )),
            Self::Local(pool) => {
                // Never choose arbitrarily when distinct subjects share a username.
                let rows: Vec<(String, String)> = sqlx::query_as(
                    "select id::text, username from user_identity where username = $1 order by id limit 2"
                ).bind(username).fetch_all(*pool).await?;
                if rows.len() > 1 {
                    return Err(AppError::Unprocessable("username is ambiguous".into()));
                }
                Ok(rows
                    .into_iter()
                    .next()
                    .map(|(id, username)| keycloak::User { id, username }))
            }
        }
    }
}

/// `LIKE` treats `%`, `_` and the escape character as syntax; search them literally.
fn like_literal(text: &str) -> String {
    text.replace('\\', "\\\\")
        .replace('%', "\\%")
        .replace('_', "\\_")
}

// Same bounded ten-minute snapshot cache as Python. No network/SQL awaits under the mutex.
static SNAPSHOTS: LazyLock<Mutex<VecDeque<(String, Uuid, Instant)>>> =
    LazyLock::new(|| Mutex::new(VecDeque::new()));
pub async fn snapshot(admission: &AdmissionState, user: &CurrentUser) {
    if admission.user_directory != DirectoryKind::Local
        || !admission.auth.enabled()
        || user.username.is_empty()
        || user.service_account
        || user.delegation_caller
        || user.roles.iter().any(|role| role == "service_agent")
    {
        return;
    }
    let Ok(id) = Uuid::parse_str(&user.uid) else {
        return;
    };
    let database = admission
        .pool
        .connect_options()
        .get_database()
        .unwrap_or_default()
        .to_owned();
    let now = Instant::now();
    {
        let mut cache = SNAPSHOTS.lock().await;
        if cache
            .iter()
            .any(|(db, uid, deadline)| db == &database && *uid == id && *deadline > now)
        {
            return;
        }
        cache.retain(|(db, uid, _)| db != &database || *uid != id);
        cache.push_back((database.clone(), id, now + Duration::from_secs(600)));
        if cache.len() > 2048 {
            cache.pop_front();
        }
    }
    let result = sqlx::query("insert into user_identity (id, username, email, first_name, last_name) values ($1,$2,$3,$4,$5) on conflict (id) do update set username=excluded.username, email=excluded.email, first_name=excluded.first_name, last_name=excluded.last_name, last_seen_at=now()")
        .bind(id).bind(&user.username).bind(&user.email).bind(&user.first_name).bind(&user.last_name)
        .execute(&admission.pool).await;
    if result.is_err() {
        SNAPSHOTS
            .lock()
            .await
            .retain(|(db, uid, _)| db != &database || *uid != id);
        tracing::warn!("[AUTH] Local identity snapshot failed");
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn like_wildcards_and_the_escape_are_literal() {
        assert_eq!(super::like_literal(r"50%_a\b"), r"50\%\_a\\b");
        assert_eq!(super::like_literal("dim"), "dim");
    }

    #[test]
    fn display_name_prefers_the_full_name_then_the_username() {
        let raw = |value| super::UserSummary::from_raw(&value).unwrap().display_name();
        let named = serde_json::json!({"id": "u", "username": "pnair", "firstName": "Priya", "lastName": "Nair"});
        assert_eq!(raw(named).as_deref(), Some("Priya Nair"));
        let first = serde_json::json!({"id": "u", "username": "pnair", "firstName": "Priya"});
        assert_eq!(raw(first).as_deref(), Some("Priya"));
        let bare = serde_json::json!({"id": "u", "username": "pnair", "firstName": " "});
        assert_eq!(raw(bare).as_deref(), Some("pnair"));
        assert_eq!(raw(serde_json::json!({"id": "u"})), None);
    }
}
