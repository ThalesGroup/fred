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

//! Minimal OpenFGA HTTP client: check, write, and read a user's direct roles.
//! Startup follows fred-core's engine: find the store by name, create it if allowed,
//! then write the model when `sync_schema_on_init` is set.

use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::{
    domain::{Permission, Role},
    roles::{PlatformPermission, PlatformRole, SpacePermission},
};

/// The single platform object holding platform roles.
const PLATFORM: &str = "platform:root";

#[derive(Clone)]
pub struct Fga {
    http: reqwest::Client,
    base: String,
    store: String,
    /// None means the store's latest model, as fred-core does without a sync.
    model: Option<String>,
    token: Option<String>,
}

pub struct Tuple<'a> {
    pub user: &'a str,
    pub role: Role,
    pub space: Uuid,
}

impl Tuple<'_> {
    fn key(&self) -> Value {
        json!({
            "user": format!("user:{}", self.user),
            "relation": self.role.as_str(),
            "object": format!("space:{}", self.space),
        })
    }
}

impl Fga {
    pub async fn connect(
        base: &str,
        store_name: &str,
        create_store_if_needed: bool,
        sync_schema_on_init: bool,
        token: Option<String>,
        timeout: Option<Duration>,
    ) -> Result<Self> {
        let mut http = reqwest::Client::builder();
        if let Some(t) = timeout {
            http = http.timeout(t);
        }
        let mut fga = Self {
            http: http.build()?,
            base: base.trim_end_matches('/').to_string(),
            store: String::new(),
            model: None,
            token,
        };
        let stores = fga.get(&format!("/stores?name={store_name}")).await?;
        let found = stores["stores"]
            .as_array()
            .into_iter()
            .flatten()
            .find_map(|s| {
                (s["name"].as_str() == Some(store_name)).then(|| s["id"].as_str().map(String::from))
            });
        fga.store = match found.flatten() {
            Some(id) => id,
            None if create_store_if_needed => {
                tracing::info!(store_name, "[REBAC] OpenFGA store not found; creating it.");
                let created = fga.post("/stores", json!({ "name": store_name })).await?;
                created["id"].as_str().context("no store id")?.to_string()
            }
            None => bail!("OpenFGA store '{store_name}' does not exist"),
        };
        if sync_schema_on_init {
            let model: Value = serde_json::from_str(include_str!("../openfga/model.json"))?;
            let path = format!("/stores/{}/authorization-models", fga.store);
            let resp = fga.post(&path, model).await?;
            fga.model = resp["authorization_model_id"].as_str().map(String::from);
        }
        tracing::info!(store_id = fga.store, model_id = ?fga.model, "[REBAC] OpenFGA engine initialized");
        Ok(fga)
    }

    async fn get(&self, path: &str) -> Result<Value> {
        let mut req = self.http.get(format!("{}{}", self.base, path));
        if let Some(t) = &self.token {
            req = req.bearer_auth(t);
        }
        Self::parse(path, req.send().await.context("openfga unreachable")?).await
    }

    async fn post(&self, path: &str, body: Value) -> Result<Value> {
        let mut req = self.http.post(format!("{}{}", self.base, path)).json(&body);
        if let Some(t) = &self.token {
            req = req.bearer_auth(t);
        }
        Self::parse(path, req.send().await.context("openfga unreachable")?).await
    }

    async fn parse(_path: &str, resp: reqwest::Response) -> Result<Value> {
        let status = resp.status();
        let body: Value = resp.json().await.unwrap_or(Value::Null);
        if !status.is_success() {
            bail!("openfga request failed ({status})");
        }
        Ok(body)
    }

    /// The single authorization call of every request.
    pub async fn check(&self, user: &str, permission: Permission, space: Uuid) -> Result<bool> {
        self.check_object(user, permission.as_str(), &format!("space:{space}"))
            .await
    }

    pub async fn is_platform_admin(&self, user: &str) -> Result<bool> {
        self.check_object(user, "admin", PLATFORM).await
    }

    pub async fn grant_platform_admin(&self, user: &str) -> Result<()> {
        let key =
            json!({ "user": format!("user:{user}"), "relation": "admin", "object": PLATFORM });
        self.write_keys(vec![key], Vec::new()).await
    }

    async fn check_object(&self, user: &str, relation: &str, object: &str) -> Result<bool> {
        let mut body = json!({
            "tuple_key": { "user": format!("user:{user}"), "relation": relation, "object": object },
            "consistency": "HIGHER_CONSISTENCY",
        });
        self.pin_model(&mut body);
        let resp = self
            .post(&format!("/stores/{}/check", self.store), body)
            .await?;
        Ok(resp["allowed"].as_bool().unwrap_or(false))
    }

    pub async fn write(&self, writes: &[Tuple<'_>], deletes: &[Tuple<'_>]) -> Result<()> {
        self.write_keys(
            writes.iter().map(Tuple::key).collect(),
            deletes.iter().map(Tuple::key).collect(),
        )
        .await
    }

    /// Idempotent, as fred-core's engine: duplicates and missing deletes are ignored.
    async fn write_keys(&self, writes: Vec<Value>, deletes: Vec<Value>) -> Result<()> {
        let mut body = json!({});
        self.pin_model(&mut body);
        if !writes.is_empty() {
            body["writes"] = json!({ "tuple_keys": writes, "on_duplicate": "ignore" });
        }
        if !deletes.is_empty() {
            body["deletes"] = json!({ "tuple_keys": deletes, "on_missing": "ignore" });
        }
        self.post(&format!("/stores/{}/write", self.store), body)
            .await?;
        Ok(())
    }

    pub async fn check_platform(&self, user: &str, permission: PlatformPermission) -> Result<bool> {
        self.check_object(user, permission.relation(), PLATFORM)
            .await
    }

    pub async fn check_space(
        &self,
        user: &str,
        permission: SpacePermission,
        space: Uuid,
    ) -> Result<bool> {
        self.check_object(user, permission.relation(), &format!("space:{space}"))
            .await
    }

    pub async fn effective_platform_roles(&self, user: &str) -> Result<Vec<PlatformRole>> {
        let [a, b, c, d, e] = PlatformRole::ALL;
        let (a, b, c, d, e) = tokio::try_join!(
            self.check_object(user, a.relation(), PLATFORM),
            self.check_object(user, b.relation(), PLATFORM),
            self.check_object(user, c.relation(), PLATFORM),
            self.check_object(user, d.relation(), PLATFORM),
            self.check_object(user, e.relation(), PLATFORM),
        )?;
        Ok(PlatformRole::ALL
            .into_iter()
            .zip([a, b, c, d, e])
            .filter_map(|(role, allowed)| allowed.then_some(role))
            .collect())
    }

    /// Low-level writer; callers must hold the platform lock and authorize the mutation.
    pub async fn write_platform(&self, user: &str, role: PlatformRole, grant: bool) -> Result<()> {
        let key = json!({ "user": format!("user:{user}"), "relation": role.relation(), "object": PLATFORM });
        if grant {
            self.write_keys(vec![key], vec![]).await
        } else {
            self.write_keys(vec![], vec![key]).await
        }
    }

    pub async fn platform_grants(&self) -> Result<Vec<(String, PlatformRole)>> {
        Ok(self
            .read_keys(json!({ "object": PLATFORM }))
            .await?
            .into_iter()
            .filter_map(|k| {
                Some((
                    k.user.strip_prefix("user:")?.to_owned(),
                    PlatformRole::parse(&k.relation)?,
                ))
            })
            .collect())
    }

    pub async fn space_admins(&self, space: Uuid) -> Result<Vec<String>> {
        Ok(self
            .read_keys(json!({ "object": format!("space:{space}"), "relation": "admin" }))
            .await?
            .into_iter()
            .filter_map(|k| k.user.strip_prefix("user:").map(str::to_owned))
            .collect())
    }

    /// Direct roles only; no derived role is represented as a stored grant.
    pub async fn roles_of(&self, user: &str) -> Result<Vec<(Uuid, Role)>> {
        Ok(self
            .read_keys(json!({ "user": format!("user:{user}"), "object": "space:" }))
            .await?
            .into_iter()
            .filter_map(|k| {
                Some((
                    k.object.strip_prefix("space:")?.parse().ok()?,
                    Role::parse(&k.relation)?,
                ))
            })
            .collect())
    }

    async fn read_keys(&self, key: Value) -> Result<Vec<StoredKey>> {
        #[derive(Deserialize)]
        struct Item {
            key: StoredKey,
        }
        #[derive(Deserialize)]
        struct Page {
            tuples: Vec<Item>,
            #[serde(default)]
            continuation_token: String,
        }
        let mut out = Vec::new();
        let mut token = String::new();
        loop {
            let body = json!({ "tuple_key": key, "continuation_token": token, "consistency": "HIGHER_CONSISTENCY" });
            let page: Page = serde_json::from_value(
                self.post(&format!("/stores/{}/read", self.store), body)
                    .await?,
            )?;
            out.extend(page.tuples.into_iter().map(|t| t.key));
            if page.continuation_token.is_empty() {
                return Ok(out);
            }
            if page.continuation_token == token {
                bail!("OpenFGA repeated a continuation token");
            }
            token = page.continuation_token;
        }
    }

    fn pin_model(&self, body: &mut Value) {
        if let Some(model) = &self.model {
            body["authorization_model_id"] = json!(model);
        }
    }
}

#[derive(Deserialize)]
struct StoredKey {
    user: String,
    relation: String,
    object: String,
}
