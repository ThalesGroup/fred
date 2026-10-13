//! Minimal OpenFGA HTTP client: check, write, and read a user's direct roles.
//! Startup follows fred-core's engine: find the store by name, create it if allowed,
//! then write the model when `sync_schema_on_init` is set.

use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::Deserialize;
use serde_json::{Value, json};
use uuid::Uuid;

use crate::domain::{Permission, Role};

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

    async fn parse(path: &str, resp: reqwest::Response) -> Result<Value> {
        let status = resp.status();
        let body: Value = resp.json().await.unwrap_or(Value::Null);
        if !status.is_success() {
            bail!("openfga {path} returned {status}: {body}");
        }
        Ok(body)
    }

    /// The single authorization call of every request.
    pub async fn check(&self, user: &str, permission: Permission, space: Uuid) -> Result<bool> {
        let mut body = json!({
            "tuple_key": {
                "user": format!("user:{user}"),
                "relation": permission.as_str(),
                "object": format!("space:{space}"),
            },
        });
        self.pin_model(&mut body);
        let resp = self
            .post(&format!("/stores/{}/check", self.store), body)
            .await?;
        Ok(resp["allowed"].as_bool().unwrap_or(false))
    }

    pub async fn write(&self, writes: &[Tuple<'_>], deletes: &[Tuple<'_>]) -> Result<()> {
        let mut body = json!({});
        self.pin_model(&mut body);
        if !writes.is_empty() {
            body["writes"] = json!({
                "tuple_keys": writes.iter().map(Tuple::key).collect::<Vec<_>>(),
                "on_duplicate": "ignore",
            });
        }
        if !deletes.is_empty() {
            body["deletes"] = json!({
                "tuple_keys": deletes.iter().map(Tuple::key).collect::<Vec<_>>(),
                "on_missing": "ignore",
            });
        }
        self.post(&format!("/stores/{}/write", self.store), body)
            .await?;
        Ok(())
    }

    /// Every direct role of a user, across all spaces. Bounded by that user's memberships,
    /// never by documents or folders.
    pub async fn roles_of(&self, user: &str) -> Result<Vec<(Uuid, Role)>> {
        #[derive(Deserialize)]
        struct Key {
            relation: String,
            object: String,
        }
        #[derive(Deserialize)]
        struct Item {
            key: Key,
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
            let mut body =
                json!({ "tuple_key": { "user": format!("user:{user}"), "object": "space:" } });
            if !token.is_empty() {
                body["continuation_token"] = json!(token);
            }
            let page: Page = serde_json::from_value(
                self.post(&format!("/stores/{}/read", self.store), body)
                    .await?,
            )?;
            for t in page.tuples {
                let id = t
                    .key
                    .object
                    .strip_prefix("space:")
                    .and_then(|s| s.parse().ok());
                if let (Some(id), Some(role)) = (id, Role::parse(&t.key.relation)) {
                    out.push((id, role));
                }
            }
            if page.continuation_token.is_empty() {
                return Ok(out);
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
