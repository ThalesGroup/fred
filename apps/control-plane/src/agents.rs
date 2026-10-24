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

//! Embedded and live runtime template discovery. No enrollment or persistent catalog.

use std::{collections::BTreeMap, time::Duration};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

use crate::{
    domain::{Permission, SpaceKind},
    error::{AppError, AppResult},
    spaces,
};

const NATIVE_RUNTIME_ID: &str = fred_rust_agent::DEFINITION.provider;

#[derive(Debug, Clone, Default, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PlatformConfig {
    #[serde(default)]
    pub runtime_catalog_sources: Vec<RuntimeCatalogSource>,
}

#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct RuntimeCatalogSource {
    pub runtime_id: String,
    pub base_url: String,
    #[serde(default = "crate::config::yes")]
    pub enabled: bool,
}

impl PlatformConfig {
    pub fn validate(&self) -> Result<()> {
        let mut ids = std::collections::HashSet::new();
        for source in &self.runtime_catalog_sources {
            let id = &source.runtime_id;
            ensure!(
                !id.is_empty() && id.trim() == id,
                "runtime_id {id:?} must be nonblank, without surrounding spaces"
            );
            ensure!(
                id != NATIVE_RUNTIME_ID,
                "runtime_id {id} is reserved for the embedded agent; external sources cannot use it"
            );
            ensure!(ids.insert(id), "runtime_id {id} is duplicated");
            // Messages name the source, never base_url, which may carry credentials.
            let url = reqwest::Url::parse(&source.base_url)
                .with_context(|| format!("runtime {id} base_url must be an HTTP(S) URL"))?;
            ensure!(
                matches!(url.scheme(), "http" | "https")
                    && url.host_str().is_some()
                    && url.username().is_empty()
                    && url.password().is_none()
                    && url.query().is_none()
                    && url.fragment().is_none(),
                "runtime {id} base_url must be HTTP(S), without credentials, query or fragment"
            );
        }
        Ok(())
    }
}

#[derive(Debug, Deserialize, Serialize, ToSchema)]
pub struct RuntimeTemplate {
    pub template_agent_id: String,
    pub title: String,
    pub description: String,
    pub kind: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub public_version: Option<String>,
    // Keep tuning, capabilities and future runtime metadata without a second SDK model.
    #[serde(flatten)]
    pub metadata: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Serialize, ToSchema)]
pub struct RuntimeCatalog {
    pub runtime_id: String,
    pub templates: Vec<RuntimeTemplate>,
}

fn native_catalog() -> RuntimeCatalog {
    let definition = fred_rust_agent::DEFINITION;
    RuntimeCatalog {
        runtime_id: NATIVE_RUNTIME_ID.into(),
        templates: vec![RuntimeTemplate {
            template_agent_id: definition.id.into(),
            title: definition.title.into(),
            description: definition.description.into(),
            // Fixed response, with no ReAct loop or graph execution engine.
            kind: "static".into(),
            public_version: Some(definition.version.into()),
            metadata: BTreeMap::new(),
        }],
    }
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AgentCapabilityKind {
    Agent,
}

#[derive(Debug, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AgentScopePolicy {
    AdminGated,
}

/// The existing admin row's identity and organization default, without invented instance health.
#[derive(Debug, Serialize, ToSchema)]
pub struct AgentEnablement {
    pub id: Uuid,
    pub runtime_id: String,
    pub source_id: String,
    pub name: String,
    pub description: String,
    pub version: String,
    pub public_version: Option<String>,
    pub icon: String,
    pub kind: AgentCapabilityKind,
    pub team_scope: AgentScopePolicy,
    pub default_on: bool,
    pub default_capability_ids: Vec<String>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SetAgentDefaultOnRequest {
    pub default_on: bool,
}

#[derive(Serialize, ToSchema)]
pub struct AgentDefaultOnResult {
    pub capability_id: Uuid,
    pub default_on: bool,
}

/// Organization namespace and unambiguous provenance determine the FGA identity, not the label.
pub fn template_id(organization: Uuid, runtime: &str, template: &str) -> Uuid {
    let runtime_id = Uuid::new_v5(&organization, runtime.as_bytes());
    Uuid::new_v5(&runtime_id, template.as_bytes())
}

fn project(organization: Uuid, catalogs: Vec<RuntimeCatalog>) -> AppResult<Vec<AgentEnablement>> {
    let mut items = Vec::new();
    for catalog in catalogs {
        for template in catalog.templates {
            let dependencies = template
                .metadata
                .get("default_capability_ids")
                .map(|value| serde_json::from_value::<Vec<String>>(value.clone()))
                .transpose()
                .context("invalid template dependencies")?
                .unwrap_or_default();
            items.push(AgentEnablement {
                id: template_id(
                    organization,
                    &catalog.runtime_id,
                    &template.template_agent_id,
                ),
                runtime_id: catalog.runtime_id.clone(),
                source_id: template.template_agent_id,
                name: template.title,
                description: template.description,
                version: "1".into(),
                public_version: template.public_version,
                icon: "smart_toy".into(),
                kind: AgentCapabilityKind::Agent,
                team_scope: AgentScopePolicy::AdminGated,
                default_on: false,
                default_capability_ids: dependencies,
            });
        }
    }
    Ok(items)
}

pub fn routes() -> utoipa_axum::router::OpenApiRouter<crate::api::AppState> {
    utoipa_axum::router::OpenApiRouter::new()
        .routes(utoipa_axum::routes!(organization_agents))
        .routes(utoipa_axum::routes!(set_organization_agent_default))
}

#[utoipa::path(
    get, path = "/organizations/{organization_id}/agents",
    params(("organization_id" = uuid::Uuid, Path)),
    responses(
        (status = 200, body = [AgentEnablement]),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody)
    )
)]
async fn organization_agents(
    axum::extract::State(s): axum::extract::State<crate::api::AppState>,
    crate::onboarding::AdmittedUser(user): crate::onboarding::AdmittedUser,
    crate::extract::ApiPath(organization_id): crate::extract::ApiPath<uuid::Uuid>,
) -> crate::error::AppResult<axum::Json<Vec<AgentEnablement>>> {
    let organization = crate::spaces::authorize(
        &s.pool,
        &s.fga,
        &user.uid,
        organization_id,
        crate::domain::Permission::Manage,
    )
    .await?;
    if organization.kind != crate::domain::SpaceKind::Organization {
        return Err(crate::error::AppError::NotFound);
    }
    let mut items = project(organization_id, discover(&s.agent_catalog).await?)?;
    for item in &mut items {
        item.default_on = s.fga.agent_default_on(organization_id, item.id).await?;
    }
    Ok(axum::Json(items))
}

#[utoipa::path(
    put, path = "/organizations/{organization_id}/agents/{agent_id}/default-on",
    params(("organization_id" = Uuid, Path), ("agent_id" = Uuid, Path)),
    request_body = SetAgentDefaultOnRequest,
    responses(
        (status = 200, body = AgentDefaultOnResult),
        (status = 401, body = crate::error::ErrorBody),
        (status = 403, body = crate::error::ErrorBody),
        (status = 404, body = crate::error::ErrorBody),
        (status = 409, body = crate::error::ErrorBody),
        (status = 500, body = crate::error::ErrorBody),
        (status = 503, body = crate::error::ErrorBody)
    )
)]
async fn set_organization_agent_default(
    axum::extract::State(s): axum::extract::State<crate::api::AppState>,
    crate::onboarding::AdmittedUser(user): crate::onboarding::AdmittedUser,
    crate::extract::ApiPath((organization_id, agent_id)): crate::extract::ApiPath<(Uuid, Uuid)>,
    crate::extract::ApiJson(body): crate::extract::ApiJson<SetAgentDefaultOnRequest>,
) -> AppResult<axum::Json<AgentDefaultOnResult>> {
    let organization = spaces::authorize(
        &s.pool,
        &s.fga,
        &user.uid,
        organization_id,
        Permission::Manage,
    )
    .await?;
    if organization.kind != SpaceKind::Organization {
        return Err(AppError::NotFound);
    }
    // Runtime discovery never holds a SQL connection or transaction.
    let items = project(organization_id, discover(&s.agent_catalog).await?)?;
    let item = items
        .iter()
        .find(|item| item.id == agent_id)
        .ok_or(AppError::NotFound)?;
    if body.default_on && !item.default_capability_ids.is_empty() {
        return Err(AppError::problem(
            axum::http::StatusCode::CONFLICT,
            "agent_dependencies_unavailable",
            "Template tool dependencies are not enabled in this organization.",
        ));
    }
    let (mut tx, mut guard) = spaces::lock_for(&s.pool, &s.fga, &organization).await?;
    spaces::authorize_locked(
        &mut tx,
        &s.fga,
        &user.uid,
        organization_id,
        Permission::Manage,
    )
    .await?;
    let changed = s
        .fga
        .set_agent_default_on(&mut guard, organization_id, agent_id, body.default_on)
        .await?;
    tx.commit().await?;
    if changed {
        tracing::info!(target: "fred.security.audit", audit_event="agent.default_changed",
            actor_uid=%user.uid, organization_id=%organization_id, agent_id=%agent_id,
            default_on=body.default_on, "Organization agent default changed");
    }
    Ok(axum::Json(AgentDefaultOnResult {
        capability_id: agent_id,
        default_on: body.default_on,
    }))
}

/// Expects a configuration accepted by [`PlatformConfig::validate`].
pub async fn discover(config: &PlatformConfig) -> Result<Vec<RuntimeCatalog>> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()?;
    let mut catalogs = vec![native_catalog()];
    for source in config.runtime_catalog_sources.iter().filter(|s| s.enabled) {
        let response = client
            .get(format!(
                "{}/agents/templates",
                source.base_url.trim_end_matches('/')
            ))
            .send()
            .await
            .with_context(|| format!("runtime {} is unreachable", source.runtime_id))?;
        ensure!(
            response.status().is_success(),
            "runtime {} returned HTTP {} while listing templates",
            source.runtime_id,
            response.status()
        );
        let templates = response
            .json::<Vec<RuntimeTemplate>>()
            .await
            .with_context(|| format!("runtime {} returned invalid templates", source.runtime_id))?;
        catalogs.push(RuntimeCatalog {
            runtime_id: source.runtime_id.clone(),
            templates,
        });
    }
    Ok(catalogs)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{Json, Router, http::StatusCode, response::Redirect, routing::get};
    use serde_json::json;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };

    fn source(runtime_id: &str, base_url: &str) -> RuntimeCatalogSource {
        RuntimeCatalogSource {
            runtime_id: runtime_id.into(),
            base_url: base_url.into(),
            enabled: true,
        }
    }

    fn platform(runtime_catalog_sources: Vec<RuntimeCatalogSource>) -> PlatformConfig {
        PlatformConfig {
            runtime_catalog_sources,
        }
    }

    async fn runtime() -> (String, Arc<AtomicUsize>, tokio::task::JoinHandle<()>) {
        let disabled_hits = Arc::new(AtomicUsize::new(0));
        let hits = disabled_hits.clone();
        let app = Router::new()
            .route(
                "/ok/agents/templates",
                get(|| async {
                    Json(json!([{
                        "template_agent_id": "georges",
                        "title": "Georges",
                        "description": "Generalist",
                        "kind": "react",
                        "max_chat_input_chars": 20000
                    }]))
                }),
            )
            .route(
                "/failing/agents/templates",
                get(|| async { StatusCode::INTERNAL_SERVER_ERROR }),
            )
            .route(
                "/malformed/agents/templates",
                get(|| async { Json(json!([{"template_agent_id": "x"}])) }),
            )
            .route(
                "/redirect/agents/templates",
                get(|| async { Redirect::temporary("/ok/agents/templates") }),
            )
            .route(
                "/disabled/agents/templates",
                get(move || {
                    hits.fetch_add(1, Ordering::SeqCst);
                    async { Json(json!([])) }
                }),
            );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (base, disabled_hits, task)
    }

    #[test]
    fn validation_names_the_rejected_source_without_echoing_its_url() {
        for (sources, expected) in [
            (
                vec![source("", "http://h")],
                "runtime_id \"\" must be nonblank",
            ),
            (
                vec![source(" a ", "http://h")],
                "runtime_id \" a \" must be",
            ),
            (
                vec![source("a", "http://h"), source("a", "http://h")],
                "runtime_id a is duplicated",
            ),
            (vec![source("b", "not a url")], "runtime b base_url"),
            (vec![source("b", "ftp://h")], "runtime b base_url"),
            (vec![source("b", "http://u:p@h")], "runtime b base_url"),
            (vec![source("b", "http://h/?q")], "runtime b base_url"),
            (vec![source("b", "http://h/#f")], "runtime b base_url"),
        ] {
            let error = format!("{:#}", platform(sources).validate().unwrap_err());
            assert!(error.contains(expected), "{error}");
            assert!(!error.contains("u:p"), "{error}");
        }
        platform(vec![source("a", "https://h/fred/agents/v2/")])
            .validate()
            .unwrap();
    }

    #[tokio::test]
    async fn discovery_groups_enabled_sources_and_fails_on_any_source_error() {
        let (base, disabled_hits, task) = runtime().await;
        let ok = source("a", &format!("{base}/ok/"));
        let mut disabled = source("off", &format!("{base}/disabled"));
        disabled.enabled = false;

        let catalogs = discover(&platform(vec![ok.clone(), disabled]))
            .await
            .unwrap();
        assert_eq!(catalogs.len(), 2);
        assert_eq!(catalogs[0].runtime_id, NATIVE_RUNTIME_ID);
        assert_eq!(catalogs[1].runtime_id, "a");
        assert_eq!(catalogs[1].templates[0].template_agent_id, "georges");
        assert_eq!(
            catalogs[1].templates[0].metadata["max_chat_input_chars"],
            20000
        );
        assert_eq!(disabled_hits.load(Ordering::SeqCst), 0);

        for (path, expected) in [
            ("failing", "runtime b returned HTTP 500"),
            ("malformed", "runtime b returned invalid templates"),
            ("redirect", "runtime b returned HTTP 307"),
        ] {
            let failing = source("b", &format!("{base}/{path}"));
            let error = discover(&platform(vec![ok.clone(), failing]))
                .await
                .unwrap_err();
            assert!(error.to_string().contains(expected), "{error:#}");
        }
        task.abort();
    }

    #[tokio::test]
    async fn unreachable_runtime_keeps_its_cause() {
        let error = discover(&platform(vec![source("c", "http://127.0.0.1:1")]))
            .await
            .unwrap_err();
        assert!(
            format!("{error:#}").starts_with("runtime c is unreachable: "),
            "{error:#}"
        );
    }
}
