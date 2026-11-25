// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use crate::{agents::PlatformConfig, error::AppResult};
use chrono::NaiveDate;
use futures::{StreamExt, stream};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Each runtime owns its defaults. None means unavailable/unsupported, never empty.
#[derive(Serialize, ToSchema)]
pub struct RuntimePromptDefaults {
    pub runtime_id: String,
    pub source_unavailable: bool,
    pub platform_prompt: Option<String>,
    pub platform_instructions: Option<String>,
    pub creation_assistant_prompt: Option<String>,
    pub creation_assistant_prompt_revised_at: Option<NaiveDate>,
}

#[derive(Deserialize)]
struct PodDefaults {
    platform_prompt: String,
    platform_instructions: String,
    creation_assistant_prompt: Option<String>,
    creation_assistant_prompt_revised_at: Option<NaiveDate>,
}

pub(super) async fn read(platform: &PlatformConfig) -> AppResult<Vec<RuntimePromptDefaults>> {
    let client = crate::agents::catalog_client()?;
    let sources: Vec<_> = platform
        .runtime_catalog_sources
        .iter()
        .filter(|s| s.enabled)
        .cloned()
        .collect();
    let mut defaults = stream::iter(sources)
        .map(|source| {
            let client = client.clone();
            async move {
                let fetch = async {
                    let mut response = client
                        .get(format!(
                            "{}/agents/platform-prompt",
                            source.base_url.trim_end_matches('/')
                        ))
                        .timeout(std::time::Duration::from_secs(5))
                        .send()
                        .await
                        .ok()?;
                    if !response.status().is_success() {
                        return None;
                    }
                    let body =
                        crate::agent_instances::tuning::read_limited(&mut response, 256 * 1024)
                            .await?;
                    serde_json::from_slice::<PodDefaults>(&body).ok()
                }
                .await;
                RuntimePromptDefaults {
                    runtime_id: source.runtime_id.clone(),
                    source_unavailable: fetch.is_none(),
                    platform_prompt: fetch.as_ref().map(|v| v.platform_prompt.clone()),
                    platform_instructions: fetch.as_ref().map(|v| v.platform_instructions.clone()),
                    creation_assistant_prompt: fetch
                        .as_ref()
                        .and_then(|v| v.creation_assistant_prompt.clone()),
                    creation_assistant_prompt_revised_at: fetch
                        .and_then(|v| v.creation_assistant_prompt_revised_at),
                }
            }
        })
        .buffer_unordered(8)
        .collect::<Vec<_>>()
        .await;
    defaults.push(RuntimePromptDefaults {
        runtime_id: fred_rust_agent::DEFINITION.provider.into(),
        source_unavailable: false,
        platform_prompt: Some(fred_rust_agent::DEFAULT_PLATFORM_PROMPT.into()),
        platform_instructions: Some(fred_rust_agent::PLATFORM_INSTRUCTIONS.into()),
        creation_assistant_prompt: None,
        creation_assistant_prompt_revised_at: None,
    });
    defaults.sort_by(|a, b| a.runtime_id.cmp(&b.runtime_id));
    Ok(defaults)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agents::RuntimeCatalogSource;
    use axum::{Json, Router, routing::get};
    use serde_json::json;

    #[tokio::test]
    async fn defaults_keep_runtime_provenance_empty_and_unavailable_distinct() {
        let app = Router::new()
            .route("/one/agents/platform-prompt", get(|| async { Json(json!({"platform_prompt":"one", "platform_instructions":"rules", "creation_assistant_prompt":"draft {language}", "creation_assistant_prompt_revised_at":"2026-11-19"})) }))
            .route("/two/agents/platform-prompt", get(|| async { Json(json!({"platform_prompt":"", "platform_instructions":"different"})) }));
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        let config = PlatformConfig {
            runtime_catalog_sources: ["one", "two", "missing"]
                .into_iter()
                .map(|id| RuntimeCatalogSource {
                    runtime_id: id.into(),
                    base_url: format!("{base}/{id}"),
                    public_base_url: None,
                    enabled: true,
                })
                .collect(),
            ..Default::default()
        };
        let defaults = read(&config).await.unwrap();
        let one = defaults.iter().find(|d| d.runtime_id == "one").unwrap();
        assert_eq!(one.platform_prompt.as_deref(), Some("one"));
        assert_eq!(
            one.creation_assistant_prompt_revised_at
                .unwrap()
                .to_string(),
            "2026-11-19"
        );
        let two = defaults.iter().find(|d| d.runtime_id == "two").unwrap();
        assert_eq!(two.platform_prompt.as_deref(), Some(""));
        assert!(!two.source_unavailable);
        let missing = defaults.iter().find(|d| d.runtime_id == "missing").unwrap();
        assert!(missing.source_unavailable);
        assert!(missing.platform_prompt.is_none());
        server.abort();
    }
}
