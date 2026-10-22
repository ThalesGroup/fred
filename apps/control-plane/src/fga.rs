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

//! Minimal OpenFGA HTTP client: check, write, and read direct roles and the space tree.
//! Startup follows fred-core's engine: find the store by name, create it if allowed,
//! then write the model when `sync_schema_on_init` is set.

use std::time::Duration;

use anyhow::{Context, Result, bail};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use uuid::Uuid;

use crate::{
    domain::{Permission, Role},
    roles::{PlatformPermission, PlatformRole, SpacePermission},
};

mod lifecycle;
pub(crate) use lifecycle::References;
/// The single platform object holding platform roles.
mod migration;

const PLATFORM: &str = "platform:root";

#[derive(Clone)]
pub struct Fga {
    http: reqwest::Client,
    base: String,
    store: String,
    configured_store: String,
    ambiguous_source: bool,
    /// None means the store's latest model, as fred-core does without a sync.
    model: Option<String>,
    token: Option<String>,
}

/// Captured before authorization, consumed atomically with the authorized effects.
/// A failed/ambiguous write invalidates this attempt; never refresh it and reuse a decision.
pub struct Guard {
    versions: Option<Vec<Value>>,
}
impl Guard {
    pub(crate) fn extend(&mut self, other: Self) -> Result<()> {
        self.versions
            .as_mut()
            .context("invalid guard")?
            .extend(other.versions.context("invalid guard")?);
        Ok(())
    }
}

#[derive(Clone, Copy)]
pub enum Scope {
    Platform,
    Organization(Uuid),
}
impl Scope {
    fn object(self) -> String {
        match self {
            Self::Platform => "guard:platform".into(),
            Self::Organization(id) => format!("guard:{id}"),
        }
    }
}

/// Concurrent OpenFGA Reads issued by one operation, such as one level of a tree walk.
pub const READ_CONCURRENCY: usize = 8;

#[derive(Debug, thiserror::Error)]
#[error("authorization changed; retry with fresh authorization checks")]
pub struct Conflict;

/// OpenFGA rejected a tuple itself, for example a malformed subject.
#[derive(Debug, thiserror::Error)]
#[error("invalid authorization tuple")]
pub struct InvalidTuple;

/// Only the status and OpenFGA's error code are kept; the message can echo input.
#[derive(Debug, thiserror::Error)]
#[error("openfga request failed ({status})")]
struct RequestFailure {
    status: reqwest::StatusCode,
    code: Option<String>,
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

/// Placement of a new space, written once with its creation grants and never removed.
pub enum Link {
    Parent { child: Uuid, parent: Uuid },
    Organization { personal: Uuid, organization: Uuid },
}

impl Link {
    fn key(&self) -> Value {
        let (relation, object, user) = match self {
            Self::Parent { child, parent } => ("parent", child, parent),
            Self::Organization {
                personal,
                organization,
            } => ("organization", personal, organization),
        };
        json!({ "user": format!("space:{user}"), "relation": relation, "object": format!("space:{object}") })
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
            configured_store: store_name.into(),
            ambiguous_source: false,
            model: None,
            token,
        };
        let stores = fga.get(&format!("/stores?name={store_name}")).await?;
        fga.ambiguous_source = stores["stores"]
            .as_array()
            .into_iter()
            .flatten()
            .filter(|s| s["name"].as_str() == Some(store_name))
            .count()
            > 1;
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
            let code = body["code"].as_str().map(String::from);
            return Err(RequestFailure { status, code }.into());
        }
        Ok(body)
    }

    /// The single authorization call of every request.
    pub async fn check(&self, user: &str, permission: Permission, space: Uuid) -> Result<bool> {
        self.check_object(user, permission.as_str(), &format!("space:{space}"))
            .await
    }

    pub async fn is_platform_owner(&self, user: &str) -> Result<bool> {
        self.check_object(user, PlatformRole::PlatformOwner.relation(), PLATFORM)
            .await
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

    pub async fn write(
        &self,
        guard: &mut Guard,
        writes: &[Tuple<'_>],
        deletes: &[Tuple<'_>],
    ) -> Result<()> {
        self.write_guarded(
            guard,
            writes.iter().map(Tuple::key).collect(),
            deletes.iter().map(Tuple::key).collect(),
        )
        .await
    }

    /// Links and grants land in one Write, so a placed space never lacks its creator's grants.
    pub async fn write_created(
        &self,
        guard: &mut Guard,
        links: &[Link],
        grants: &[Tuple<'_>],
    ) -> Result<()> {
        self.write_guarded(
            guard,
            links
                .iter()
                .map(Link::key)
                .chain(grants.iter().map(Tuple::key))
                .collect(),
            vec![],
        )
        .await
    }

    /// Initialization is strict on both tuples. An uncertain initializer cannot later
    /// add another version: the immutable sentinel makes that entire retry fail.
    pub(crate) async fn initialize_guard(&self, scope: Scope) -> Result<()> {
        let object = scope.object();
        self.post(&format!("/stores/{}/write", self.store), json!({
            "authorization_model_id": self.model,
            "writes": {"tuple_keys": [
                {"user":"revision:initialized", "relation":"initialized", "object":object},
                {"user":format!("revision:{}", Uuid::new_v4()), "relation":"version", "object":object}
            ], "on_duplicate":"error"}
        })).await?;
        Ok(())
    }

    /// SQL locks prevent ordinary contention; these revisions also fence remote writes
    /// that outlive their caller/transaction. Read before *all* checks used by the delta.
    pub async fn guard(&self, scopes: &[Scope]) -> Result<Guard> {
        anyhow::ensure!(
            !scopes.is_empty(),
            "a mutation needs an authorization scope"
        );
        let mut versions = Vec::new();
        for scope in scopes {
            let object = scope.object();
            anyhow::ensure!(
                !versions.iter().any(|v: &Value| v["object"] == object),
                "duplicate guard scope"
            );
            let mut keys = self
                .read_keys(json!({"object":object,"relation":"version"}))
                .await?;
            anyhow::ensure!(keys.len() == 1, "missing or corrupt authorization guard");
            let key = keys.pop().unwrap();
            let revision = key
                .user
                .strip_prefix("revision:")
                .context("invalid guard subject")?;
            Uuid::parse_str(revision).context("invalid guard revision")?;
            anyhow::ensure!(
                key.condition.is_none_or(|c| c.is_null()),
                "conditional guard is invalid"
            );
            versions.push(json!({"user":key.user,"relation":key.relation,"object":key.object}));
        }
        Ok(Guard {
            versions: Some(versions),
        })
    }

    /// Empty role deltas still fence earlier requests, including idempotent revocations.
    /// Callers omit absent role deletes after a guarded read: guard deletes stay strict.
    async fn write_guarded(
        &self,
        guard: &mut Guard,
        mut writes: Vec<Value>,
        mut deletes: Vec<Value>,
    ) -> Result<()> {
        let previous = guard
            .versions
            .take()
            .context("authorization attempt already failed")?;
        anyhow::ensure!(
            writes.len() + deletes.len() + 2 * previous.len() <= 100,
            "OpenFGA transaction exceeds 100 tuple operations"
        );
        let next: Vec<Value> = previous
            .iter()
            .map(|key| {
                json!({
                    "user":format!("revision:{}", Uuid::new_v4()),
                    "relation":"version", "object":key["object"]
                })
            })
            .collect();
        writes.extend(next.clone());
        deletes.extend(previous);
        let mut body = json!({
            "writes":{"tuple_keys":writes, "on_duplicate":"ignore"},
            "deletes":{"tuple_keys":deletes, "on_missing":"error"}
        });
        self.pin_model(&mut body);
        if let Err(error) = self
            .post(&format!("/stores/{}/write", self.store), body)
            .await
        {
            // A consumed guard is a missing delete; anything else malformed is the input.
            return Err(match error.downcast_ref::<RequestFailure>() {
                Some(e) if e.status.as_u16() == 409 => Conflict.into(),
                Some(e) if e.code.as_deref() == Some("write_failed_due_to_invalid_input") => {
                    Conflict.into()
                }
                Some(e) if e.code.as_deref() == Some("validation_error") => InvalidTuple.into(),
                _ => error,
            });
        }
        guard.versions = Some(next);
        Ok(())
    }

    pub async fn fence(&self, guard: &mut Guard) -> Result<()> {
        self.write_guarded(guard, vec![], vec![]).await
    }

    /// Store identity for diagnostics and operator tools, never selected by a caller.
    pub fn store_id(&self) -> &str {
        &self.store
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
        let [a, b, c, d] = PlatformRole::ALL;
        let (a, b, c, d) = tokio::try_join!(
            self.check_object(user, a.relation(), PLATFORM),
            self.check_object(user, b.relation(), PLATFORM),
            self.check_object(user, c.relation(), PLATFORM),
            self.check_object(user, d.relation(), PLATFORM),
        )?;
        Ok(PlatformRole::ALL
            .into_iter()
            .zip([a, b, c, d])
            .filter_map(|(role, allowed)| allowed.then_some(role))
            .collect())
    }

    /// Low-level writer; callers must hold the platform lock and authorize the mutation.
    pub async fn write_platform(
        &self,
        guard: &mut Guard,
        user: &str,
        role: PlatformRole,
        grant: bool,
    ) -> Result<()> {
        let key = json!({ "user": format!("user:{user}"), "relation": role.relation(), "object": PLATFORM });
        if grant {
            self.write_guarded(guard, vec![key], vec![]).await
        } else {
            self.write_guarded(guard, vec![], vec![key]).await
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

    /// Direct holders of `role` on one space.
    pub async fn space_holders(&self, space: Uuid, role: Role) -> Result<Vec<String>> {
        Ok(self
            .read_keys(json!({ "object": format!("space:{space}"), "relation": role.as_str() }))
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

    /// A user's direct roles on one space.
    pub async fn direct_roles_on(&self, user: &str, space: Uuid) -> Result<Vec<Role>> {
        Ok(self
            .read_keys(
                json!({ "user": format!("user:{user}"), "object": format!("space:{space}") }),
            )
            .await?
            .iter()
            .filter_map(|k| Role::parse(&k.relation))
            .collect())
    }

    /// The space a `parent` or `organization` link of `space` points to.
    pub async fn link_of(&self, space: Uuid, organization: bool) -> Result<Option<Uuid>> {
        let relation = if organization {
            "organization"
        } else {
            "parent"
        };
        let keys = self
            .read_keys(json!({ "object": format!("space:{space}"), "relation": relation }))
            .await?;
        anyhow::ensure!(keys.len() <= 1, "space has several {relation} links");
        keys.first().map(|k| space_id(&k.user)).transpose()
    }

    /// Spaces linked to `space` as their parent, or as their organization for personal spaces.
    pub async fn linked_to(&self, space: Uuid, organization: bool) -> Result<Vec<Uuid>> {
        let relation = if organization {
            "organization"
        } else {
            "parent"
        };
        self.read_keys(
            json!({ "user": format!("space:{space}"), "relation": relation, "object": "space:" }),
        )
        .await?
        .iter()
        .map(|k| space_id(&k.object))
        .collect()
    }

    /// One concurrent children Read per space.
    pub async fn children_of(&self, spaces: &[Uuid]) -> Result<Vec<(Uuid, Vec<Uuid>)>> {
        self.concurrently(
            spaces,
            |fga, id| async move { fga.linked_to(id, false).await },
        )
        .await
    }

    /// One Read per space, at most `READ_CONCURRENCY` in flight.
    async fn concurrently<T, F, Fut>(&self, spaces: &[Uuid], read: F) -> Result<Vec<(Uuid, T)>>
    where
        T: Send + 'static,
        F: Fn(Fga, Uuid) -> Fut,
        Fut: std::future::Future<Output = Result<T>> + Send + 'static,
    {
        let mut waiting = spaces.iter().copied();
        let mut reads = tokio::task::JoinSet::new();
        let spawn = |reads: &mut tokio::task::JoinSet<_>, id: Uuid| {
            let pending = read(self.clone(), id);
            reads.spawn(async move { pending.await.map(|value| (id, value)) });
        };
        for id in waiting.by_ref().take(READ_CONCURRENCY) {
            spawn(&mut reads, id);
        }
        let mut out = Vec::with_capacity(spaces.len());
        while let Some(result) = reads.join_next().await {
            out.push(result??);
            if let Some(id) = waiting.next() {
                spawn(&mut reads, id);
            }
        }
        Ok(out)
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
            let mut body =
                json!({ "continuation_token": token, "consistency": "HIGHER_CONSISTENCY" });
            if key.as_object().is_some_and(|k| !k.is_empty()) {
                body["tuple_key"] = key.clone();
            }
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

fn space_id(subject: &str) -> Result<Uuid> {
    subject
        .strip_prefix("space:")
        .context("link is not a space")?
        .parse()
        .context("invalid space id")
}

#[derive(Clone, Deserialize, Serialize)]
struct StoredKey {
    user: String,
    relation: String,
    object: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    condition: Option<Value>,
}

/// OpenFGA protobuf JSON adds absent default values when reading a model back.
/// Remove only representation defaults, retaining every nonempty authorization term.
fn normalized_model(mut value: Value) -> Value {
    match &mut value {
        Value::Object(map) => {
            map.retain(|key, value| {
                !((matches!(key.as_str(), "object" | "condition" | "module") && value == "")
                    || (matches!(key.as_str(), "metadata" | "source_info") && value.is_null())
                    || (key == "relations" && value.as_object().is_some_and(|v| v.is_empty())))
            });
            for value in map.values_mut() {
                *value = normalized_model(value.take());
            }
        }
        Value::Array(values) => {
            for value in values {
                *value = normalized_model(value.take());
            }
        }
        _ => {}
    }
    value
}
