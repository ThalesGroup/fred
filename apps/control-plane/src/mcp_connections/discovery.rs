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
    space_id: uuid::Uuid,
    config: &McpConfiguration,
    bindings: &[McpCredentialBinding],
    knowledge_flow_url: Option<&str>,
    directory: Option<&crate::keycloak::Directory>,
) -> Result<Vec<McpTool>, &'static str> {
    config
        .validate(space_id, bindings)
        .map_err(|_| "destination_mismatch")?;
    config
        .trusted_destination(knowledge_flow_url)
        .map_err(|_| "destination_mismatch")?;
    let directory = if config.is_tabular() {
        Some(directory.ok_or("credential_missing")?.clone())
    } else {
        None
    };
    let secret = config
        .credential_reference()
        .map(|reference| {
            bindings
                .iter()
                .find(|b| {
                    b.space_id == space_id
                        && b.credential_binding == reference
                        && b.url == config.url
                })
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
            McpAuthentication::None | McpAuthentication::KnowledgeFlowTabular => {
                return Err("invalid_configuration");
            }
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
    let tokens = std::sync::Arc::new(tokio::sync::Mutex::new(Vec::<String>::new()));
    let transport = StreamableHttpClientTransport::with_client(
        DiscoveryClient {
            client,
            directory,
            destination: config.url.clone(),
            tokens: tokens.clone(),
        },
        transport_config,
    );
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
            let live_tokens = tokens.lock().await;
            if live_tokens.iter().any(|token| {
                serialized.contains(token)
                    || serde_json::to_string(token)
                        .is_ok_and(|encoded| serialized.contains(&encoded[1..encoded.len() - 1]))
            }) || serialized.len() > MAX_BYTES
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

use futures::stream::BoxStream;
use reqwest::header::{HeaderName, HeaderValue};
use rmcp::model::ClientJsonRpcMessage;
use rmcp::transport::streamable_http_client::{
    SseError, StreamableHttpClient, StreamableHttpError, StreamableHttpPostResponse,
};
use sse_stream::Sse;
use std::{collections::HashMap, sync::Arc};

type HttpError = StreamableHttpError<reqwest::Error>;

#[derive(Clone)]
struct DiscoveryClient {
    client: reqwest::Client,
    directory: Option<crate::keycloak::Directory>,
    destination: String,
    tokens: Arc<tokio::sync::Mutex<Vec<String>>>,
}

impl DiscoveryClient {
    async fn token(&self, uri: &str) -> Result<Option<String>, HttpError> {
        if uri != self.destination {
            return Err(HttpError::UnexpectedServerResponse(
                "destination_mismatch".into(),
            ));
        }
        let Some(directory) = &self.directory else {
            return Ok(None);
        };
        let token = directory
            .access_token()
            .await
            .map_err(|_| HttpError::UnexpectedServerResponse("credential_unavailable".into()))?;
        let mut tokens = self.tokens.lock().await;
        if !tokens.contains(&token) {
            tokens.push(token.clone());
        }
        Ok(Some(token))
    }

    async fn rejected(&self, error: Option<&HttpError>, token: Option<&str>) -> bool {
        let unauthorized = match error {
            Some(HttpError::AuthRequired(_)) => true,
            Some(HttpError::HttpStatus(error)) => {
                error.status == reqwest::StatusCode::UNAUTHORIZED.as_u16()
            }
            // rmcp 3.9's POST adapter encodes a challenge-free 401 in this
            // status prefix. Match the SDK prefix, never the response body.
            Some(HttpError::UnexpectedServerResponse(message)) => {
                message.starts_with("HTTP 401 Unauthorized:")
            }
            Some(HttpError::Client(error)) => {
                error.status() == Some(reqwest::StatusCode::UNAUTHORIZED)
            }
            _ => false,
        };
        if unauthorized && let (Some(directory), Some(token)) = (&self.directory, token) {
            directory.refresh_rejected(token).await;
            return true;
        }
        false
    }
}

impl StreamableHttpClient for DiscoveryClient {
    type Error = reqwest::Error;
    async fn post_message(
        &self,
        uri: Arc<str>,
        message: ClientJsonRpcMessage,
        session_id: Option<Arc<str>>,
        _auth: Option<String>,
        headers: HashMap<HeaderName, HeaderValue>,
    ) -> Result<StreamableHttpPostResponse, HttpError> {
        let token = self.token(&uri).await?;
        let result = self
            .client
            .post_message_with_max_sse_event_size(
                uri.clone(),
                message.clone(),
                session_id.clone(),
                token.clone(),
                headers.clone(),
                MAX_BYTES,
            )
            .await;
        if self.rejected(result.as_ref().err(), token.as_deref()).await {
            let token = self.token(&uri).await?;
            return self
                .client
                .post_message_with_max_sse_event_size(
                    uri,
                    message.clone(),
                    session_id.clone(),
                    token,
                    headers,
                    MAX_BYTES,
                )
                .await;
        }
        result
    }
    async fn delete_session(
        &self,
        uri: Arc<str>,
        session_id: Arc<str>,
        _auth: Option<String>,
        headers: HashMap<HeaderName, HeaderValue>,
    ) -> Result<(), HttpError> {
        let token = self.token(&uri).await?;
        let result = self
            .client
            .delete_session(
                uri.clone(),
                session_id.clone(),
                token.clone(),
                headers.clone(),
            )
            .await;
        if self.rejected(result.as_ref().err(), token.as_deref()).await {
            let token = self.token(&uri).await?;
            return self
                .client
                .delete_session(uri, session_id.clone(), token, headers)
                .await;
        }
        result
    }
    async fn get_stream(
        &self,
        uri: Arc<str>,
        session_id: Option<Arc<str>>,
        last_event_id: Option<String>,
        _auth: Option<String>,
        headers: HashMap<HeaderName, HeaderValue>,
    ) -> Result<BoxStream<'static, Result<Sse, SseError>>, HttpError> {
        let token = self.token(&uri).await?;
        let result = self
            .client
            .get_stream_with_max_sse_event_size(
                uri.clone(),
                session_id.clone(),
                last_event_id.clone(),
                token.clone(),
                headers.clone(),
                MAX_BYTES,
            )
            .await;
        if self.rejected(result.as_ref().err(), token.as_deref()).await {
            let token = self.token(&uri).await?;
            return self
                .client
                .get_stream_with_max_sse_event_size(
                    uri,
                    session_id.clone(),
                    last_event_id.clone(),
                    token,
                    headers,
                    MAX_BYTES,
                )
                .await;
        }
        result
    }
}
