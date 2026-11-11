// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
use super::*;
use sqlx::types::Json;

fn connection() -> Connection {
    let tool = McpTool {
        name: "search".into(),
        description: None,
        input_schema: json!({"type":"object"}),
        output_schema: None,
        annotations: None,
    };
    Connection {
        space_id: Uuid::nil(),
        id: Uuid::new_v4(),
        logical_name: "search".into(),
        display_name: "Search".into(),
        description: "Tools".into(),
        revision: 1,
        configuration: Json(McpConfiguration {
            url: "https://tools.invalid/mcp".into(),
            authentication: McpAuthentication::None,
            allow_insecure_http: false,
        }),
        enabled: true,
        observation_revision: Some(1),
        observation_state: "available".into(),
        error_code: None,
        checked_at: None,
        last_success_at: None,
        observed_tools: Json(vec![tool.clone()]),
        published_tools: Json(vec![tool]),
        published_revision: Some(1),
    }
}

#[test]
fn publication_is_distinct_from_observation_and_configuration() {
    let mut c = connection();
    assert!(c.available());
    c.observed_tools.0.push(McpTool {
        name: "new".into(),
        ..c.published_tools[0].clone()
    });
    assert!(c.available());
    assert_eq!(c.published_tools.len(), 1);
    c.observed_tools.0[0].description = Some("changed".into());
    assert!(!c.available());
    c.observed_tools = c.published_tools.clone();
    c.observation_state = "unavailable".into();
    assert!(!c.available());
    assert_eq!(c.published_tools.len(), 1);
    c.observation_state = "available".into();
    c.revision = 2;
    assert!(!c.available());
    c.observation_revision = Some(2);
    assert!(!c.available());
    c.published_revision = Some(2);
    assert!(c.available());
    c.enabled = false;
    assert!(!c.available());
}

#[test]
fn credential_destination_and_reserved_headers_are_checked() {
    let local = vec![McpCredentialBinding {
        space_id: Uuid::nil(),
        credential_binding: "provider".into(),
        url: "https://tools.invalid/mcp".into(),
        secret_env: "MCP_TEST_KEY".into(),
    }];
    let mut config = connection().configuration.0;
    config.authentication = McpAuthentication::Bearer {
        credential_binding: "provider".into(),
    };
    assert!(config.validate(Uuid::nil(), &local).is_ok());
    assert!(config.validate(Uuid::new_v4(), &local).is_err());
    config.url = "https://other.invalid/mcp".into();
    assert!(config.validate(Uuid::nil(), &local).is_err());
    config.url = local[0].url.clone();
    config.authentication = McpAuthentication::ApiKey {
        credential_binding: "provider".into(),
        header: "x-fred-user".into(),
    };
    assert!(config.validate(Uuid::nil(), &local).is_err());
    config.authentication = McpAuthentication::None;
    config.url = "http://internal/mcp".into();
    assert!(config.validate(Uuid::nil(), &[]).is_err());
    config.allow_insecure_http = true;
    assert!(config.validate(Uuid::nil(), &[]).is_ok());
}

/// Deterministic HTTP fixture implementing only negotiation/listing, never a tool call.
async fn server(mode: &'static str) -> (String, tokio::task::JoinHandle<()>) {
    use axum::{Json, Router, http::StatusCode, response::IntoResponse, routing::post};
    let tokens = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let app=Router::new().route("/realms/mcp/protocol/openid-connect/token", post(move || {
        let tokens = tokens.clone();
        async move { Json(json!({"access_token":format!("service-{}",tokens.fetch_add(1, std::sync::atomic::Ordering::SeqCst)),"expires_in":300})) }
    })).route("/mcp/tabular",post(move |headers:axum::http::HeaderMap, axum::extract::RawQuery(query):axum::extract::RawQuery, Json(request):Json<Value>| async move {
        if matches!(mode, "trusted" | "forbidden") {
            assert!(query.is_none());
            assert!(!headers.keys().any(|key| key.as_str().starts_with("x-fred-")));
            let auth = headers.get("authorization").and_then(|h| h.to_str().ok()).unwrap_or_default();
            if mode == "forbidden" { return StatusCode::FORBIDDEN.into_response(); }
            if auth == "Bearer service-0" { return StatusCode::UNAUTHORIZED.into_response(); }
            assert_eq!(auth, "Bearer service-1");
        }
        let id=request["id"].clone();
        match request["method"].as_str().unwrap_or_default() {
            "server/discover" => Json(json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"legacy fixture"}})).into_response(),
            // Strict like MCP Toolbox: protocol 2026-07-28 removed `initialize`, so a handshake
            // naming it (or a later revision) is refused instead of being silently downgraded.
            "initialize" if request["params"]["protocolVersion"].as_str().is_none_or(|v| v >= "2026-07-28") => (StatusCode::NOT_FOUND, Json(json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"invalid method initialize"}}))).into_response(),
            "initialize" => Json(json!({"jsonrpc":"2.0","id":id,"result":{"protocolVersion":"2025-03-26","capabilities":{"tools":{}},"serverInfo":{"name":"fixture","version":"1"}}})).into_response(),
            "notifications/initialized" => StatusCode::ACCEPTED.into_response(),
            "tools/list" if mode=="rejected" && request["params"]["cursor"].as_str()==Some("next") => StatusCode::UNAUTHORIZED.into_response(),
            "tools/list" => {
                let second=request["params"]["cursor"].as_str()==Some("next");
                let mut result=json!({"tools":[{"name":if second {"second"}else{"first"},"inputSchema":{"type":"object"}}]});
                if !second || mode=="cycle" {result["nextCursor"]=json!("next");}
                Json(json!({"jsonrpc":"2.0","id":id,"result":result})).into_response()
            },
            _ => StatusCode::BAD_REQUEST.into_response(),
        }
    }));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}/mcp/tabular", listener.local_addr().unwrap());
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (url, task)
}

#[tokio::test]
async fn discovery_paginates_and_rejects_partial_or_cyclic_inventory() {
    for mode in ["ok", "cycle", "rejected"] {
        let (url, task) = server(mode).await;
        let result = discovery::discover(
            Uuid::nil(),
            &McpConfiguration {
                url,
                authentication: McpAuthentication::None,
                allow_insecure_http: true,
            },
            &[],
            None,
            None,
        )
        .await;
        task.abort();
        if mode == "ok" {
            assert_eq!(result.unwrap().len(), 2);
        } else {
            assert!(result.is_err());
        }
    }
}

#[test]
fn trusted_service_identity_cannot_be_repointed_or_inferred_from_names() {
    let mut c = connection();
    c.logical_name = "knowledge-flow-tabular".into();
    c.display_name = "Knowledge Flow Tabular".into();
    c.configuration.url = "https://kf.invalid/api/mcp/tabular".into();
    assert!(c.descriptor()["mcp_service"].is_null());
    c.configuration.authentication = McpAuthentication::KnowledgeFlowTabular;
    assert_eq!(c.descriptor()["mcp_service"], "knowledge_flow_tabular");
    assert!(
        c.configuration
            .trusted_destination(Some("https://kf.invalid/api/"))
            .is_ok()
    );
    for base in [
        None,
        Some("https://external.invalid/api"),
        Some("https://kf.invalid/api?person=forged"),
    ] {
        assert!(c.configuration.trusted_destination(base).is_err());
    }
    assert!(c.configuration.credential_reference().is_none());
}

#[test]
fn two_pods_resolve_one_service_offer_without_a_native_duplicate() {
    use crate::agents::{AgentTemplateStatus, AgentTemplateSummary};
    let mut c = connection();
    c.configuration.authentication = McpAuthentication::KnowledgeFlowTabular;
    let offer: std::collections::BTreeMap<String, Value> =
        serde_json::from_value(c.descriptor()).unwrap();
    let owner = "mcp-knowledge-flow-mcp-tabular";
    for (pod, selectable, category) in [("first", true, "react"), ("second", false, "graph")] {
        let mut template = AgentTemplateSummary {
            template_id: Uuid::new_v4(), source_runtime_id: pod.into(), source_agent_id: "flexible".into(),
            display_name: "Flexible".into(), description: "Tools".into(), description_by_lang: None,
            capabilities: vec![], category: category.into(), tags: vec![], team_instantiable: true,
            status: AgentTemplateStatus::Available, public_version: None, default_tuning_fields: vec![],
            max_chat_input_chars: None, supports_capabilities: selectable, supports_managed_mcp: true,
            supports_hitl: false, default_capability_ids: vec![owner.into()],
            available_capabilities: vec![serde_json::from_value(json!({"id":owner,"mcp_service":"knowledge_flow_tabular","version":"1","config_fields":[{"key":"business_setting"}]})).unwrap()],
        };
        let unresolved = template.default_capability_ids.clone();
        let contributions = template.available_capabilities.clone();
        extend_template(&mut template, &[]);
        assert!(template.available_capabilities.is_empty());
        assert_eq!(template.default_capability_ids, unresolved); // explicit unavailable dependency, never YAML fallback
        template.available_capabilities = contributions.clone();
        extend_template(&mut template, std::slice::from_ref(&offer));
        assert_eq!(template.available_capabilities.len(), 1);
        assert_eq!(template.available_capabilities[0]["id"], c.capability_id());
        assert_eq!(
            template.available_capabilities[0]["config_fields"][0]["key"],
            "business_setting"
        );
        assert_eq!(template.default_capability_ids, vec![c.capability_id()]);
        assert_eq!(capability_owner(&template, &c.capability_id()), owner);
        let external = serde_json::from_value(connection().descriptor()).unwrap();
        template.available_capabilities = contributions;
        template.default_capability_ids = vec![owner.into()];
        extend_template(&mut template, &[offer.clone(), external]);
        assert_eq!(
            template.available_capabilities.len(),
            if selectable { 2 } else { 1 }
        );
        if !selectable {
            crate::agent_instances::tuning::require_inventory(&template, &[c.capability_id()])
                .unwrap();
            assert!(crate::agent_instances::tuning::require_inventory(&template, &[]).is_err());
            assert!(
                crate::agent_instances::tuning::require_inventory(
                    &template,
                    &[c.capability_id(), "managed-mcp:arbitrary".into()]
                )
                .is_err()
            );
            template.default_capability_ids.clear();
            template.available_capabilities = vec![
                serde_json::from_value(json!({"id":owner,"mcp_service":"knowledge_flow_tabular"}))
                    .unwrap(),
            ];
            extend_template(&mut template, std::slice::from_ref(&offer));
            assert!(template.available_capabilities.is_empty());
        }
    }
}

#[tokio::test]
async fn trusted_discovery_uses_shared_m2m_renewal_without_document_context() {
    let (url, task) = server("trusted").await;
    let base = url.strip_suffix("/mcp/tabular").unwrap();
    let directory = crate::keycloak::Directory::new(
        &format!("{base}/realms/mcp"),
        "control-plane",
        "fixture-secret".into(),
    )
    .unwrap();
    let config = McpConfiguration {
        url: url.clone(),
        authentication: McpAuthentication::KnowledgeFlowTabular,
        allow_insecure_http: true,
    };
    let tools = discovery::discover(Uuid::nil(), &config, &[], Some(base), Some(&directory))
        .await
        .unwrap();
    assert_eq!(tools.len(), 2);
    assert_eq!(directory.access_token().await.unwrap(), "service-1");
    task.abort();
}

#[tokio::test]
async fn trusted_discovery_does_not_renew_a_forbidden_credential() {
    let (url, task) = server("forbidden").await;
    let base = url.strip_suffix("/mcp/tabular").unwrap();
    let directory = crate::keycloak::Directory::new(
        &format!("{base}/realms/mcp"),
        "control-plane",
        "fixture-secret".into(),
    )
    .unwrap();
    let config = McpConfiguration {
        url: url.clone(),
        authentication: McpAuthentication::KnowledgeFlowTabular,
        allow_insecure_http: true,
    };
    assert_eq!(
        discovery::discover(Uuid::nil(), &config, &[], Some(base), Some(&directory)).await,
        Err("connection_rejected")
    );
    assert_eq!(directory.access_token().await.unwrap(), "service-0");
    task.abort();
}

#[test]
fn inventory_changes_compare_complete_contracts_and_require_a_fresh_observation() {
    let mut c = connection();
    let changes = c.tool_changes().unwrap();
    assert!(changes.added.is_empty() && changes.modified.is_empty() && changes.removed.is_empty());
    for changed in [
        McpTool {
            description: Some("new description".into()),
            ..c.observed_tools[0].clone()
        },
        McpTool {
            input_schema: json!({"type":"object","required":["query"]}),
            ..c.observed_tools[0].clone()
        },
        McpTool {
            output_schema: Some(json!({"type":"array"})),
            ..c.observed_tools[0].clone()
        },
        McpTool {
            annotations: Some(json!({"readOnlyHint":true})),
            ..c.observed_tools[0].clone()
        },
    ] {
        c.observed_tools.0 = vec![changed];
        assert_eq!(c.tool_changes().unwrap().modified, vec!["search"]);
    }
    c.published_tools.0.push(McpTool {
        name: "removed".into(),
        ..c.published_tools[0].clone()
    });
    c.observed_tools.0.push(McpTool {
        name: "added".into(),
        ..c.observed_tools[0].clone()
    });
    let changes = c.tool_changes().unwrap();
    assert_eq!(changes.added, vec!["added"]);
    assert_eq!(changes.removed, vec!["removed"]);
    c.observation_state = "unavailable".into();
    assert!(c.tool_changes().is_none());
    c.observation_state = "available".into();
    c.revision += 1;
    assert!(c.tool_changes().is_none());
}

#[test]
fn display_name_does_not_change_identity_or_inventory() {
    let mut c = connection();
    let id = c.capability_id();
    c.display_name = "Postal Demo".into();
    assert_eq!(c.capability_id(), id);
    assert_eq!(c.descriptor()["name"], "Postal Demo");
    assert_eq!(c.descriptor()["source_id"], "search");
    assert!(c.available());
    assert!(c.tool_changes().unwrap().modified.is_empty());
}
