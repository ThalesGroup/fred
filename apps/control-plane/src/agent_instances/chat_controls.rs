// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Pod-owned capability controls, evaluated in one batch after admission checks.

use std::collections::BTreeMap;

use axum::http::HeaderValue;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::agents::{AgentTemplateSummary, PlatformConfig};

use super::{preparation::ChatControlDescriptor, tuning};

// Mirrors fred-sdk/contracts/capability/chat_controls.py; capability config and
// widget params remain opaque. The pod owns defaults and schema upgrades.
#[derive(Serialize)]
struct RequestItem<'a> {
    capability_id: &'a str,
    config_envelope: Option<&'a Value>,
}

#[derive(Serialize)]
struct Request<'a> {
    items: Vec<RequestItem<'a>>,
}

#[derive(Deserialize)]
struct Control {
    widget: String,
    params: Option<BTreeMap<String, Value>>,
}

#[derive(Deserialize)]
struct ResultItem {
    capability_id: String,
    #[serde(default)]
    controls: Vec<Control>,
    error: Option<String>,
}

#[derive(Deserialize)]
struct Response {
    #[serde(default)]
    results: Vec<ResultItem>,
}

pub(super) async fn resolve(
    platform: &PlatformConfig,
    template: &AgentTemplateSummary,
    saved: &Value,
    selected: &[String],
    authorization: Option<&HeaderValue>,
) -> Vec<ChatControlDescriptor> {
    let request = request(template, saved, selected);
    if request.items.is_empty() {
        return Vec::new();
    }
    let Some(response) = fetch(
        platform,
        &template.source_runtime_id,
        authorization,
        &request,
    )
    .await
    else {
        // Never log the bearer, stored config, pod response body or transport URL.
        tracing::warn!(runtime_id = %template.source_runtime_id, "Pod chat controls unavailable");
        return Vec::new();
    };
    let mut results: BTreeMap<_, _> = response
        .results
        .into_iter()
        .map(|result| (result.capability_id.clone(), result))
        .collect();
    let mut controls = Vec::new();
    for item in request.items {
        let Some(result) = results.remove(item.capability_id) else {
            tracing::warn!(
                capability_id = item.capability_id,
                "Pod omitted capability chat controls"
            );
            continue;
        };
        if result.error.as_ref().is_some_and(|error| !error.is_empty()) {
            tracing::warn!(
                capability_id = item.capability_id,
                "Pod could not evaluate capability chat controls"
            );
            continue;
        }
        controls.extend(
            result
                .controls
                .into_iter()
                .map(|control| ChatControlDescriptor {
                    capability_id: item.capability_id.to_owned(),
                    widget: control.widget,
                    params: control.params,
                }),
        );
    }
    controls
}

fn request<'a>(
    template: &'a AgentTemplateSummary,
    saved: &'a Value,
    selected: &[String],
) -> Request<'a> {
    let items = template
        .available_capabilities
        .iter()
        .filter_map(|entry| entry.get("id").and_then(Value::as_str))
        .filter(|id| selected.iter().any(|selected| selected == id))
        .filter_map(|capability_id| {
            // Swift evaluates an absent/non-object slice against the pod defaults.
            let config_envelope = saved["capability_config"]
                .get(capability_id)
                .filter(|envelope| envelope.is_object());
            if config_envelope.is_some_and(|envelope| {
                !envelope["schema_version"]
                    .as_str()
                    .is_some_and(|version| !version.is_empty())
                    || envelope
                        .get("config")
                        .is_some_and(|config| !config.is_object())
            }) {
                tracing::warn!(
                    capability_id,
                    "Unreadable capability config; skipping chat controls"
                );
                return None;
            }
            Some(RequestItem {
                capability_id,
                config_envelope,
            })
        })
        .collect();
    Request { items }
}

async fn fetch(
    platform: &PlatformConfig,
    runtime_id: &str,
    authorization: Option<&HeaderValue>,
    request: &Request<'_>,
) -> Option<Response> {
    let mut response =
        tuning::capability_request(platform, runtime_id, authorization, "chat-controls")
            .ok()?
            .json(request)
            .send()
            .await
            .ok()?;
    if response.status() != axum::http::StatusCode::OK {
        return None;
    }
    let bytes = tuning::read_limited(&mut response, 2 * 1024 * 1024).await?;
    let response: Response = serde_json::from_slice(&bytes).ok()?;
    // These are the SDK's min_length=1 constraints; unknown widgets are valid.
    response
        .results
        .iter()
        .all(|result| {
            !result.capability_id.is_empty()
                && result
                    .controls
                    .iter()
                    .all(|control| !control.widget.is_empty())
        })
        .then_some(response)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::agents::{AgentTemplateStatus, RuntimeCatalogSource};
    use axum::{
        Json, Router,
        http::{HeaderMap, StatusCode, header},
        routing::post,
    };
    use serde_json::json;
    use std::sync::{
        Arc,
        atomic::{AtomicUsize, Ordering},
    };

    fn template() -> AgentTemplateSummary {
        AgentTemplateSummary {
            template_id: uuid::Uuid::nil(),
            source_runtime_id: "pod".into(),
            source_agent_id: "custom".into(),
            display_name: "Custom".into(),
            description: String::new(),
            description_by_lang: None,
            category: "react".into(),
            tags: vec![],
            capabilities: vec![],
            team_instantiable: true,
            status: AgentTemplateStatus::Available,
            public_version: None,
            default_tuning_fields: vec![],
            max_chat_input_chars: None,
            available_capabilities: ["first", "broken", "defaults", "unselected"]
                .map(|id| BTreeMap::from([("id".into(), json!(id))]))
                .to_vec(),
            supports_capabilities: true,
            default_capability_ids: vec!["unselected".into()],
        }
    }

    async fn serve(app: Router) -> (PlatformConfig, tokio::task::JoinHandle<()>) {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base_url = format!("http://{}", listener.local_addr().unwrap());
        let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        (
            PlatformConfig {
                runtime_catalog_sources: vec![RuntimeCatalogSource {
                    runtime_id: "pod".into(),
                    base_url,
                    public_base_url: None,
                    enabled: true,
                }],
                ..Default::default()
            },
            task,
        )
    }

    #[tokio::test]
    async fn batches_saved_configs_with_bearer_and_keeps_catalog_order() {
        let calls = Arc::new(AtomicUsize::new(0));
        let observed = Arc::clone(&calls);
        let app = Router::new().route("/agents/capabilities/chat-controls", post(
            move |headers: HeaderMap, Json(body): Json<Value>| {
                let observed = Arc::clone(&observed);
                async move {
                    observed.fetch_add(1, Ordering::SeqCst);
                    assert_eq!(headers[header::AUTHORIZATION], "Bearer test-user");
                    assert_eq!(body, json!({"items": [
                        {"capability_id": "first", "config_envelope": {"schema_version": "old-version", "config": {"opaque": [42]}}},
                        {"capability_id": "broken", "config_envelope": null},
                        {"capability_id": "defaults", "config_envelope": null}
                    ]}));
                    Json(json!({"results": [
                        {"capability_id": "defaults", "controls": [{"widget": "future_widget"}]},
                        {"capability_id": "broken", "error": "private diagnostic", "controls": [{"widget": "ignored"}]},
                        {"capability_id": "unselected", "controls": [{"widget": "ignored"}]},
                        {"capability_id": "first", "controls": [
                            {"widget": "a", "params": {"opaque": [true]}}, {"widget": "b", "params": null}
                        ]}
                    ]}))
                }
            }
        ));
        let (platform, server) = serve(app).await;
        let saved = json!({"capability_config": {"first": {"schema_version": "old-version", "config": {"opaque": [42]}}}});
        let controls = resolve(
            &platform,
            &template(),
            &saved,
            &["defaults".into(), "broken".into(), "first".into()],
            Some(&HeaderValue::from_static("Bearer test-user")),
        )
        .await;
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(
            serde_json::to_value(controls).unwrap(),
            json!([
                {"capability_id": "first", "widget": "a", "params": {"opaque": [true]}},
                {"capability_id": "first", "widget": "b"},
                {"capability_id": "defaults", "widget": "future_widget"}
            ])
        );
        assert!(
            resolve(&platform, &template(), &saved, &[], None)
                .await
                .is_empty()
        );
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        server.abort();
    }

    #[test]
    fn malformed_envelopes_are_skipped_without_losing_pod_defaults() {
        let template = template();
        let selected = vec!["first".into(), "broken".into(), "defaults".into()];
        for malformed in [
            json!({}),
            json!({"schema_version": ""}),
            json!({"schema_version": "1", "config": null}),
        ] {
            let saved = json!({"capability_config": {"first": malformed, "broken": {"schema_version": "1"}}});
            let body = serde_json::to_value(request(&template, &saved, &selected)).unwrap();
            assert_eq!(
                body,
                json!({"items": [
                    {"capability_id": "broken", "config_envelope": {"schema_version": "1"}},
                    {"capability_id": "defaults", "config_envelope": null}
                ]})
            );
        }
    }

    #[tokio::test]
    async fn unavailable_or_invalid_pod_response_omits_capability_controls() {
        for (status, body) in [
            (StatusCode::UNAUTHORIZED, "private response".into()),
            (StatusCode::SERVICE_UNAVAILABLE, "private response".into()),
            (StatusCode::TEMPORARY_REDIRECT, json!({"results": [{"capability_id": "first", "controls": [{"widget": "must_not_appear"}]}]}).to_string()),
            (StatusCode::OK, "invalid json".into()),
            (
                StatusCode::OK,
                json!({"results": [{"capability_id": "first", "controls": [{"widget": ""}]}]})
                    .to_string(),
            ),
            (StatusCode::OK, "x".repeat(2 * 1024 * 1024 + 1)),
        ] {
            let app = Router::new().route(
                "/agents/capabilities/chat-controls",
                post(move || async move { (status, body) }),
            );
            let (platform, server) = serve(app).await;
            assert!(
                resolve(&platform, &template(), &json!({}), &["first".into()], None)
                    .await
                    .is_empty()
            );
            server.abort();
        }
    }
}
