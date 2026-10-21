// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

//! Outbound directory access uses the manager's service identity, never the caller's token.
//! Upstream bodies and transport errors are intentionally not carried into application logs.

use crate::config::M2mConfig;
use anyhow::{Context, Result, bail};
use reqwest::{Client, Method, StatusCode, Url};
use serde::Deserialize;
use std::{
    sync::Arc,
    time::{Duration, Instant},
};
use tokio::sync::Mutex;

#[derive(Clone)]
pub struct Directory {
    http: Client,
    realm: String,
    token_url: Url,
    users_url: Url,
    client_id: String,
    secret: String,
    token: Arc<Mutex<Option<Token>>>,
}
struct Token {
    value: String,
    expires: Instant,
}

#[derive(Deserialize)]
pub struct User {
    pub id: String,
    pub username: String,
}

/// The directory uses a generated address only when the declaration omits one.
pub(crate) fn effective_email(username: &str, email: Option<&str>) -> String {
    email
        .filter(|v| !v.is_empty())
        .map(str::to_owned)
        .unwrap_or_else(|| format!("{username}@example.com"))
}

impl Directory {
    pub fn configured(config: Option<&M2mConfig>) -> Result<Option<Self>> {
        let Some(config) = config.filter(|c| c.enabled) else {
            return Ok(None);
        };
        let client = config
            .client_id
            .as_deref()
            .filter(|s| !s.is_empty())
            .context("security.m2m.client_id is required")?;
        let env = config
            .secret_env_var
            .as_deref()
            .context("security.m2m.secret_env_var is required")?;
        let secret = std::env::var(env)
            .ok()
            .filter(|s| !s.is_empty())
            .context("Keycloak service secret is missing")?;
        Ok(Some(Self::new(&config.realm_url, client, secret)?))
    }

    pub fn new(realm: &str, client_id: &str, secret: String) -> Result<Self> {
        let realm = Url::parse(realm).map_err(|_| anyhow::anyhow!("invalid Keycloak realm URL"))?;
        if !matches!(realm.scheme(), "http" | "https")
            || !realm.username().is_empty()
            || realm.password().is_some()
            || realm.query().is_some()
            || realm.fragment().is_some()
        {
            bail!("invalid Keycloak realm URL");
        }
        let mut segments: Vec<_> = realm
            .path_segments()
            .context("invalid Keycloak realm URL")?
            .filter(|s| !s.is_empty())
            .collect();
        let name = segments
            .pop()
            .context("Keycloak realm is missing")?
            .to_owned();
        if segments.pop() != Some("realms") {
            bail!("invalid Keycloak realm path");
        }
        let prefix = segments.join("/");
        let mut users_url = realm.clone();
        users_url.set_path(&format!("/{prefix}/admin/realms/{name}/users").replace("//", "/"));
        let realm_string = realm.as_str().trim_end_matches('/').to_owned();
        let mut token_url = realm;
        token_url.set_path(&format!(
            "{}/protocol/openid-connect/token",
            token_url.path().trim_end_matches('/')
        ));
        Ok(Self {
            http: Client::builder()
                .timeout(Duration::from_secs(5))
                .redirect(reqwest::redirect::Policy::none())
                .build()?,
            realm: realm_string,
            token_url,
            users_url,
            client_id: client_id.to_owned(),
            secret,
            token: Arc::new(Mutex::new(None)),
        })
    }

    pub fn realm(&self) -> &str {
        &self.realm
    }

    async fn access_token(&self) -> Result<String> {
        let mut cached = self.token.lock().await;
        if let Some(t) = cached.as_ref().filter(|t| t.expires > Instant::now()) {
            return Ok(t.value.clone());
        }
        #[derive(Deserialize)]
        struct Reply {
            access_token: String,
            expires_in: u64,
        }
        let response = self
            .http
            .post(self.token_url.clone())
            .form(&[
                ("grant_type", "client_credentials"),
                ("client_id", &self.client_id),
                ("client_secret", &self.secret),
            ])
            .send()
            .await
            .map_err(|_| anyhow::anyhow!("Keycloak token request failed"))?;
        if !response.status().is_success() {
            bail!("Keycloak token request rejected ({})", response.status());
        }
        let reply: Reply = response
            .json()
            .await
            .map_err(|_| anyhow::anyhow!("invalid Keycloak token response"))?;
        if reply.access_token.is_empty() || reply.expires_in == 0 {
            bail!("invalid Keycloak token response");
        }
        let value = reply.access_token;
        *cached = Some(Token {
            value: value.clone(),
            expires: Instant::now()
                + Duration::from_secs(reply.expires_in.saturating_sub(5).min(86400)),
        });
        Ok(value)
    }

    pub(crate) async fn request(
        &self,
        method: Method,
        url: Url,
        body: Option<&serde_json::Value>,
    ) -> Result<reqwest::Response> {
        for attempt in 0..2 {
            let token = self.access_token().await?;
            let mut request = self
                .http
                .request(method.clone(), url.clone())
                .bearer_auth(&token);
            if let Some(body) = body {
                request = request.json(body);
            }
            let response = request
                .send()
                .await
                .map_err(|_| anyhow::anyhow!("Keycloak directory request failed"))?;
            if response.status() != StatusCode::UNAUTHORIZED || attempt == 1 {
                return Ok(response);
            }
            let mut cached = self.token.lock().await;
            if cached.as_ref().is_some_and(|t| t.value == token) {
                *cached = None;
            }
        }
        unreachable!("two attempts always return")
    }

    /// Same free-text Keycloak search and result bound as Python's user service.
    pub async fn search(&self, query: &str) -> Result<Vec<crate::users::UserSummary>> {
        let mut url = self.users_url.clone();
        url.query_pairs_mut().append_pair("search", query).append_pair("max", "20");
        let response = self.request(Method::GET, url, None).await?;
        if !response.status().is_success() {
            bail!("Keycloak user search rejected ({})", response.status());
        }
        let users: Vec<serde_json::Value> = response.json().await
            .map_err(|_| anyhow::anyhow!("invalid Keycloak search response"))?;
        Ok(users.iter().filter_map(crate::users::UserSummary::from_raw).take(20).collect())
    }

    /// Exact search with explicit pagination. Do not trust a provider ignoring `exact`.
    pub async fn find_username(&self, username: &str) -> Result<Option<User>> {
        let mut found = None;
        let mut first = 0;
        for _ in 0..1000 {
            let mut url = self.users_url.clone();
            url.query_pairs_mut()
                .append_pair("username", username)
                .append_pair("exact", "true")
                .append_pair("first", &first.to_string())
                .append_pair("max", "100");
            let response = self.request(Method::GET, url, None).await?;
            if !response.status().is_success() {
                bail!("Keycloak username lookup rejected ({})", response.status());
            }
            let users: Vec<User> = response
                .json()
                .await
                .map_err(|_| anyhow::anyhow!("invalid Keycloak username response"))?;
            if users.is_empty() {
                return Ok(found);
            }
            first += users.len();
            for user in users {
                if user.username != username || user.id.is_empty() || found.is_some() {
                    bail!("Keycloak username lookup is ambiguous or inexact");
                }
                found = Some(user);
            }
        }
        bail!("Keycloak username pagination did not terminate")
    }

    /// An exact email lookup must succeed before provisioning a missing identity.
    /// Any match conflicts: a username lookup already established that this is a new account.
    pub async fn email_in_use(&self, email: &str) -> Result<bool> {
        let mut url = self.users_url.clone();
        url.query_pairs_mut()
            .append_pair("email", email)
            .append_pair("exact", "true")
            .append_pair("first", "0")
            .append_pair("max", "1");
        let response = self.request(Method::GET, url, None).await?;
        if !response.status().is_success() {
            bail!("Keycloak email lookup rejected ({})", response.status());
        }
        let users: Vec<User> = response
            .json()
            .await
            .map_err(|_| anyhow::anyhow!("invalid Keycloak email response"))?;
        Ok(!users.is_empty())
    }

    /// Re-resolve immediately before creation and after both success and conflict.
    /// Existing profiles/passwords are never patched; a lost response is recovered by replay.
    pub async fn ensure_user(
        &self,
        username: &str,
        password: Option<&str>,
        email: Option<&str>,
        first_name: Option<&str>,
        last_name: Option<&str>,
    ) -> Result<(User, bool)> {
        if let Some(user) = self.find_username(username).await? {
            return Ok((user, false));
        }
        let password = password
            .filter(|p| !p.is_empty())
            .context("missing identity requires a password")?;
        let mut body = serde_json::json!({
            "username": username, "enabled": true,
            "email": effective_email(username, email),
            "credentials": [{"type":"password", "value":password, "temporary":false}],
        });
        if let Some(name) = first_name {
            body["firstName"] = name.into();
        }
        if let Some(name) = last_name {
            body["lastName"] = name.into();
        }
        let response = self
            .request(Method::POST, self.users_url.clone(), Some(&body))
            .await?;
        let created = response.status() == StatusCode::CREATED;
        if !created && response.status() != StatusCode::CONFLICT {
            bail!("Keycloak user creation rejected ({})", response.status());
        }
        let user = self
            .find_username(username)
            .await?
            .context("Keycloak created/conflicting identity cannot be resolved")?;
        Ok((user, created))
    }

    pub async fn exists(&self, subject: &str) -> Result<bool> {
        if subject.is_empty() {
            return Ok(false);
        }
        let mut url = self.users_url.clone();
        url.path_segments_mut()
            .map_err(|_| anyhow::anyhow!("invalid directory URL"))?
            .push(subject);
        let response = self.request(Method::GET, url, None).await?;
        if response.status() == StatusCode::NOT_FOUND {
            return Ok(false);
        }
        if !response.status().is_success() {
            bail!("Keycloak directory lookup rejected ({})", response.status());
        }
        let user: User = response
            .json()
            .await
            .map_err(|_| anyhow::anyhow!("invalid Keycloak user response"))?;
        if user.id != subject {
            bail!("Keycloak returned a different subject");
        }
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{
        Json, Router,
        extract::{Path, State},
        http::{HeaderMap, StatusCode},
        routing::{get, post},
    };
    use serde_json::json;
    use std::sync::atomic::{AtomicUsize, Ordering};

    async fn fixture(
        fail_token: bool,
    ) -> (Directory, Arc<AtomicUsize>, tokio::task::JoinHandle<()>) {
        let count = Arc::new(AtomicUsize::new(0));
        let app = Router::new()
            .route(
                "/realms/app/protocol/openid-connect/token",
                post(
                    move |State(count): State<Arc<AtomicUsize>>, body: String| async move {
                        assert!(body.contains("client_id=control-plane"));
                        assert!(body.contains("client_secret=private-secret"));
                        let n = count.fetch_add(1, Ordering::SeqCst);
                        if fail_token {
                            return (
                                StatusCode::BAD_REQUEST,
                                Json(json!({"error": "private-secret"})),
                            );
                        }
                        (
                            StatusCode::OK,
                            Json(json!({"access_token": format!("token-{n}"), "expires_in": 300})),
                        )
                    },
                ),
            )
            .route(
                "/admin/realms/app/users/{id}",
                get(|Path(id): Path<String>, headers: HeaderMap| async move {
                    match id.as_str() {
                        "missing" => (StatusCode::NOT_FOUND, Json(json!({}))),
                        "failure" => (
                            StatusCode::INTERNAL_SERVER_ERROR,
                            Json(json!({"error": "private-secret"})),
                        ),
                        "malformed" => (StatusCode::OK, Json(json!({"id": "private-secret"}))),
                        "mismatch" => (
                            StatusCode::OK,
                            Json(json!({"id": "other", "username": "other"})),
                        ),
                        "refresh" if headers["authorization"] == "Bearer token-0" => {
                            (StatusCode::UNAUTHORIZED, Json(json!({})))
                        }
                        _ => (StatusCode::OK, Json(json!({"id": id, "username": "alice"}))),
                    }
                }),
            )
            .with_state(count.clone());
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let realm = format!("http://{}/realms/app", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (
            Directory::new(&realm, "control-plane", "private-secret".into()).unwrap(),
            count,
            task,
        )
    }

    #[tokio::test]
    async fn directory_caches_service_tokens_and_refreshes_once_on_unauthorized() {
        let (directory, count, task) = fixture(false).await;
        assert!(directory.exists("alice").await.unwrap());
        assert!(!directory.exists("missing").await.unwrap());
        assert_eq!(count.load(Ordering::SeqCst), 1);
        assert!(directory.exists("refresh").await.unwrap());
        assert_eq!(count.load(Ordering::SeqCst), 2);
        task.abort();
    }

    // Proves: I11
    #[tokio::test]
    async fn directory_failures_do_not_echo_credentials_or_payloads() {
        for fail_token in [false, true] {
            let (directory, _, task) = fixture(fail_token).await;
            for id in ["failure", "malformed", "mismatch"] {
                let error = directory.exists(id).await.unwrap_err();
                assert!(!format!("{error:?}").contains("private-secret"));
            }
            task.abort();
        }
    }

    #[test]
    fn directory_configuration_and_urls_fail_closed() {
        assert!(Directory::configured(None).unwrap().is_none());
        assert!(
            serde_yaml_ng::from_str::<M2mConfig>("realm_url: http://localhost/realms/app").is_err()
        );
        let disabled: M2mConfig =
            serde_yaml_ng::from_str("realm_url: http://localhost/realms/app\nenabled: false")
                .unwrap();
        assert!(Directory::configured(Some(&disabled)).unwrap().is_none());
        for url in [
            "file:///realms/app",
            "http://user:secret@host/realms/app",
            "http://host/app",
            "http://host/realms/app?secret=bad",
        ] {
            assert!(Directory::new(url, "control-plane", "secret".into()).is_err());
        }
        let directory = Directory::new(
            "http://host/auth/realms/app",
            "control-plane",
            "secret".into(),
        )
        .unwrap();
        assert_eq!(
            directory.users_url.as_str(),
            "http://host/auth/admin/realms/app/users"
        );
    }
}
