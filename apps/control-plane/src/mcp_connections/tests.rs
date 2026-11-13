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
    let app=Router::new().route("/mcp/tabular",post(move |headers:axum::http::HeaderMap, axum::extract::RawQuery(query):axum::extract::RawQuery, Json(request):Json<Value>| async move {
        assert!(query.is_none());
        assert!(!headers.contains_key("authorization"));
        assert!(!headers.keys().any(|key| key.as_str().starts_with("x-fred-")));
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
fn internal_destination_is_deployment_owned_and_not_an_admin_authentication_mode() {
    assert_eq!(
        tabular_endpoint(Some("https://kf.invalid/api/")).unwrap(),
        "https://kf.invalid/api/mcp/tabular"
    );
    for base in [None, Some("https://kf.invalid/api?person=forged")] {
        assert!(tabular_endpoint(base).is_err());
    }
    assert!(
        serde_json::from_value::<McpConfiguration>(json!({
            "url":"https://kf.invalid/api/mcp/tabular",
            "authentication":{"kind":"knowledge_flow_tabular"}
        }))
        .is_err()
    );
    let value = serde_json::to_value(McpBinding::KnowledgeFlowTabular {
        url: tabular_endpoint(Some("https://kf.invalid/api")).unwrap(),
    })
    .unwrap();
    assert_eq!(
        value,
        json!({"kind":"knowledge_flow_tabular","url":"https://kf.invalid/api/mcp/tabular"})
    );
}

#[test]
fn native_tabular_survives_without_connections_for_selectable_and_fixed_templates() {
    use crate::agents::{AgentTemplateStatus, AgentTemplateSummary};
    for (selectable, category) in [(true, "react"), (true, "deep"), (false, "graph")] {
        let mut template = AgentTemplateSummary {
            template_id: Uuid::new_v4(), source_runtime_id: "pod".into(), source_agent_id: "assistant".into(),
            display_name: "Assistant".into(), description: "Tools".into(), description_by_lang: None,
            capabilities: vec![], category: category.into(), tags: vec![], team_instantiable: true,
            status: AgentTemplateStatus::Available, public_version: None, default_tuning_fields: vec![],
            max_chat_input_chars: None, supports_capabilities: selectable, supports_managed_mcp: true,
            supports_hitl: false, default_capability_ids: vec![TABULAR_CAPABILITY_ID.into()],
            available_capabilities: vec![serde_json::from_value(json!({"id":TABULAR_CAPABILITY_ID,"version":"1","config_fields":[{"key":"business_setting"}]})).unwrap()],
        };
        extend_template(&mut template, &[]);
        assert_eq!(template.available_capabilities.len(), 1);
        assert_eq!(
            template.available_capabilities[0]["id"],
            TABULAR_CAPABILITY_ID
        );
        let external = serde_json::from_value(connection().descriptor()).unwrap();
        extend_template(&mut template, &[external]);
        assert_eq!(
            template.available_capabilities.len(),
            if selectable { 2 } else { 1 }
        );
        assert_eq!(template.default_capability_ids, vec![TABULAR_CAPABILITY_ID]);
        if !selectable {
            crate::agent_instances::tuning::require_inventory(
                &template,
                &[TABULAR_CAPABILITY_ID.into()],
            )
            .unwrap();
            assert!(crate::agent_instances::tuning::require_inventory(&template, &[]).is_err());
        }
    }
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
