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
        credential_binding: "provider".into(),
        url: "https://tools.invalid/mcp".into(),
        secret_env: "MCP_TEST_KEY".into(),
    }];
    let mut config = connection().configuration.0;
    config.authentication = McpAuthentication::Bearer {
        credential_binding: "provider".into(),
    };
    assert!(config.validate(&local).is_ok());
    config.url = "https://other.invalid/mcp".into();
    assert!(config.validate(&local).is_err());
    config.url = local[0].url.clone();
    config.authentication = McpAuthentication::ApiKey {
        credential_binding: "provider".into(),
        header: "x-fred-user".into(),
    };
    assert!(config.validate(&local).is_err());
    config.authentication = McpAuthentication::None;
    config.url = "http://internal/mcp".into();
    assert!(config.validate(&[]).is_err());
    config.allow_insecure_http = true;
    assert!(config.validate(&[]).is_ok());
}

/// Deterministic HTTP fixture implementing only negotiation/listing, never a tool call.
async fn server(mode: &'static str) -> (String, tokio::task::JoinHandle<()>) {
    use axum::{Json, Router, http::StatusCode, response::IntoResponse, routing::post};
    let app=Router::new().route("/mcp",post(move |Json(request):Json<Value>| async move {
        let id=request["id"].clone();
        match request["method"].as_str().unwrap_or_default() {
            "server/discover" => Json(json!({"jsonrpc":"2.0","id":id,"error":{"code":-32601,"message":"legacy fixture"}})).into_response(),
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
    let url = format!("http://{}/mcp", listener.local_addr().unwrap());
    let task = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
    (url, task)
}

#[tokio::test]
async fn discovery_paginates_and_rejects_partial_or_cyclic_inventory() {
    for mode in ["ok", "cycle", "rejected"] {
        let (url, task) = server(mode).await;
        let result = discovery::discover(
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
