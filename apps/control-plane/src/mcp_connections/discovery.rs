// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use super::{
    MAX_BYTES, MAX_TOOLS, McpAuthentication, McpConfiguration, McpCredentialBinding, McpTool,
};
use rmcp::{
    ServiceExt,
    model::PaginatedRequestParams,
    transport::{
        StreamableHttpClientTransport, streamable_http_client::StreamableHttpClientTransportConfig,
    },
};
use std::{collections::HashSet, time::Duration};

/// Stable diagnostic codes only: neither provider bodies nor credentials cross this boundary.
pub(super) async fn discover(
    config: &McpConfiguration,
    bindings: &[McpCredentialBinding],
) -> Result<Vec<McpTool>, &'static str> {
    config
        .validate(bindings)
        .map_err(|_| "destination_mismatch")?;
    let secret = config
        .credential_reference()
        .map(|reference| {
            bindings
                .iter()
                .find(|b| b.credential_binding == reference && b.url == config.url)
                .and_then(|b| std::env::var(&b.secret_env).ok())
                .filter(|v| !v.is_empty())
                .ok_or("credential_missing")
        })
        .transpose()?;
    let mut headers = reqwest::header::HeaderMap::new();
    if let Some(secret) = &secret {
        let (name, value) = match &config.authentication {
            McpAuthentication::Bearer { .. } => ("authorization", format!("Bearer {secret}")),
            McpAuthentication::ApiKey { header, .. } => (header.as_str(), secret.clone()),
            McpAuthentication::None => return Err("invalid_configuration"),
        };
        let mut value =
            reqwest::header::HeaderValue::from_str(&value).map_err(|_| "credential_invalid")?;
        value.set_sensitive(true);
        headers.insert(
            reqwest::header::HeaderName::from_bytes(name.as_bytes())
                .map_err(|_| "invalid_configuration")?,
            value,
        );
    }
    let client = reqwest::Client::builder()
        .default_headers(headers)
        .redirect(reqwest::redirect::Policy::none())
        .connect_timeout(Duration::from_secs(5))
        .timeout(Duration::from_secs(15))
        .build()
        .map_err(|_| "transport_unavailable")?;
    let transport_config = StreamableHttpClientTransportConfig::with_uri(config.url.clone())
        .max_sse_event_size(MAX_BYTES)
        .max_concurrent_requests(1)
        .control_request_timeout(Duration::from_secs(3))
        .reinit_on_expired_session(false);
    let transport = StreamableHttpClientTransport::with_client(client, transport_config);
    let mut service = tokio::time::timeout(Duration::from_secs(15), ().serve(transport))
        .await
        .map_err(|_| "timeout")?
        .map_err(|_| "connection_rejected")?;
    let outcome = tokio::time::timeout(Duration::from_secs(20), async {
        let mut tools = Vec::new();
        let mut names = HashSet::new();
        let mut cursors = HashSet::new();
        let mut cursor = None;
        for _ in 0..16 {
            let page = service
                .list_tools(Some(PaginatedRequestParams::default().with_cursor(cursor)))
                .await
                .map_err(|_| "inventory_unavailable")?;
            for tool in page.tools {
                if tools.len() >= MAX_TOOLS
                    || tool.name.is_empty()
                    || tool.name.len() > 128
                    || !names.insert(tool.name.to_string())
                {
                    return Err("invalid_inventory");
                }
                tools.push(McpTool {
                    name: tool.name.into_owned(),
                    description: tool.description.map(|s| s.into_owned()),
                    input_schema: serde_json::Value::Object((*tool.input_schema).clone()),
                    output_schema: tool
                        .output_schema
                        .map(|s| serde_json::Value::Object((*s).clone())),
                    annotations: tool
                        .annotations
                        .map(serde_json::to_value)
                        .transpose()
                        .map_err(|_| "invalid_inventory")?,
                });
            }
            let serialized = serde_json::to_string(&tools).map_err(|_| "invalid_inventory")?;
            if serialized.len() > MAX_BYTES
                || secret.as_ref().is_some_and(|secret| {
                    serialized.contains(secret)
                        || serde_json::to_string(secret).is_ok_and(|encoded| {
                            serialized.contains(&encoded[1..encoded.len() - 1])
                        })
                })
            {
                return Err("invalid_inventory");
            }
            cursor = page.next_cursor;
            match &cursor {
                None => {
                    tools.sort_by(|a, b| a.name.cmp(&b.name));
                    return Ok(tools);
                }
                Some(value) if !cursors.insert(value.clone()) => return Err("invalid_pagination"),
                Some(_) => {}
            }
        }
        Err("inventory_limit")
    })
    .await
    .unwrap_or(Err("timeout"));
    // SDK close terminates the session and its worker; bounded also on failure.
    let _ = service.close_with_timeout(Duration::from_secs(3)).await;
    outcome
}
