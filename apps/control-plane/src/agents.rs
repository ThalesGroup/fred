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

//! Live runtime template discovery. No enrollment or persistent catalog.

use std::{collections::BTreeMap, time::Duration};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

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

#[derive(Debug, Deserialize, Serialize)]
pub struct RuntimeTemplate {
    pub template_agent_id: String,
    pub title: String,
    pub description: String,
    pub kind: String,
    // Keep tuning, capabilities and future runtime metadata without a second SDK model.
    #[serde(flatten)]
    pub metadata: BTreeMap<String, serde_json::Value>,
}

#[derive(Debug, Serialize)]
pub struct RuntimeCatalog {
    pub runtime_id: String,
    pub templates: Vec<RuntimeTemplate>,
}

/// Expects a configuration accepted by [`PlatformConfig::validate`].
pub async fn discover(config: &PlatformConfig) -> Result<Vec<RuntimeCatalog>> {
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(10))
        .redirect(reqwest::redirect::Policy::none())
        .build()?;
    let mut catalogs = Vec::new();
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
        assert_eq!(catalogs.len(), 1);
        assert_eq!(catalogs[0].runtime_id, "a");
        assert_eq!(catalogs[0].templates[0].template_agent_id, "georges");
        assert_eq!(
            catalogs[0].templates[0].metadata["max_chat_input_chars"],
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
