// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::{collections::HashSet, sync::OnceLock, time::Duration};

use reqwest::{StatusCode, header};
use serde::{Deserialize, Serialize};
use serde_json::Value;

use super::config::{
    DeclaredModel, DiscoveryAuthentication, ModelSource, Qualification, SourceInventory,
    bounded_text,
};

const TIMEOUT: Duration = Duration::from_secs(5);
const MAX_BYTES: usize = 1024 * 1024;

/// Closed error vocabulary: never contains provider bodies, URLs, headers or secrets.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum DiscoveryFailure {
    #[error("transport_unavailable")]
    TransportUnavailable,
    #[error("http_unavailable")]
    HttpUnavailable,
    #[error("credential_unavailable")]
    CredentialUnavailable,
    #[error("redirect_refused")]
    RedirectRefused,
    #[error("invalid_response")]
    InvalidResponse,
    #[error("response_too_large")]
    TooLarge,
    #[error("incomplete_inventory")]
    Incomplete,
}

impl DiscoveryFailure {
    pub(super) fn state(self) -> &'static str {
        match self {
            Self::TransportUnavailable | Self::HttpUnavailable | Self::CredentialUnavailable => {
                "unavailable"
            }
            Self::RedirectRefused | Self::InvalidResponse | Self::TooLarge => "invalid",
            Self::Incomplete => "incomplete",
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, utoipa::ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ChatProvenance {
    SourceGuarantee,
    ApiMetadata,
}

/// Only supported typed extensions are retained; all other feature facts stay unknown.
/// Labels and limits, when present, are source-reported, never independently verified.
#[derive(Debug, Clone, Serialize, Deserialize, utoipa::ToSchema)]
pub struct ModelMetadata {
    pub chat: Option<bool>,
    pub chat_provenance: Option<ChatProvenance>,
    /// Source-reported aptitude; absent means unknown, not unsupported.
    pub reasoning: Option<bool>,
    /// Platform-attested embedding offer; such an offer is never chat.
    #[serde(default)]
    pub embedding: Option<bool>,
    /// Source-reported image input; absent means unknown, not unsupported.
    #[serde(default)]
    pub vision: Option<bool>,
    pub display_name: Option<String>,
    pub context_window_tokens: Option<i64>,
    pub max_input_tokens: Option<i64>,
    pub max_output_tokens: Option<i64>,
}

#[derive(Serialize)]
pub(super) struct DiscoveredOffer {
    pub upstream_model_id: String,
    pub metadata: ModelMetadata,
}

fn metadata(item: &Value, qualification: Qualification) -> ModelMetadata {
    let (chat, chat_provenance) = match qualification {
        Qualification::ChatSource => (Some(true), Some(ChatProvenance::SourceGuarantee)),
        Qualification::MixedCapabilitiesV1 => {
            let chat = item
                .get("capabilities")
                .and_then(|v| v.get("completion_chat"))
                .and_then(Value::as_bool);
            (chat, chat.map(|_| ChatProvenance::ApiMetadata))
        }
    };
    let positive = |key| item.get(key).and_then(Value::as_i64).filter(|v| *v > 0);
    let capability = |name: &str| match qualification {
        Qualification::MixedCapabilitiesV1 => item
            .get("capabilities")
            .and_then(|v| v.get(name))
            .and_then(Value::as_bool),
        Qualification::ChatSource => None,
    };
    ModelMetadata {
        chat,
        chat_provenance,
        reasoning: capability("reasoning"),
        embedding: None,
        vision: capability("vision"),
        display_name: ["name", "display_name"].iter().find_map(|key| {
            item.get(key)
                .and_then(Value::as_str)
                .filter(|s| bounded_text(s, 256))
                .map(str::to_owned)
        }),
        context_window_tokens: ["context_length", "max_model_len", "max_context_length"]
            .iter()
            .find_map(|key| positive(*key)),
        max_input_tokens: positive("max_input_tokens"),
        max_output_tokens: positive("max_output_tokens"),
    }
}

fn parse(
    bytes: &[u8],
    qualification: Qualification,
    complete_inventory_guaranteed: bool,
) -> Result<Vec<DiscoveredOffer>, DiscoveryFailure> {
    let payload: Value = serde_json::from_slice(bytes).map_err(|error| {
        if error.is_eof() {
            DiscoveryFailure::Incomplete
        } else {
            DiscoveryFailure::InvalidResponse
        }
    })?;
    let object = payload
        .as_object()
        .ok_or(DiscoveryFailure::InvalidResponse)?;
    let data = object
        .get("data")
        .and_then(Value::as_array)
        .ok_or(DiscoveryFailure::InvalidResponse)?;
    // This adapter has no pagination. Unknown envelope fields fail closed rather
    // than silently ignoring a provider-specific cursor, count or partial marker.
    for (key, value) in object {
        let supported = match key.as_str() {
            "data" => true,
            "object" => value.as_str() == Some("list"),
            "complete" => value.as_bool() == Some(true),
            "has_more" | "partial" | "truncated" => value.as_bool() == Some(false),
            _ => false,
        };
        if !supported {
            return Err(DiscoveryFailure::Incomplete);
        }
    }
    let mut seen = HashSet::new();
    let mut offers = Vec::with_capacity(data.len());
    for item in data {
        let id = item
            .get("id")
            .and_then(Value::as_str)
            .filter(|s| bounded_text(s, 256))
            .ok_or(DiscoveryFailure::InvalidResponse)?;
        if !seen.insert(id) {
            return Err(DiscoveryFailure::InvalidResponse);
        }
        offers.push(DiscoveredOffer {
            upstream_model_id: id.to_owned(),
            metadata: metadata(item, qualification),
        });
    }
    if !complete_inventory_guaranteed {
        return Err(DiscoveryFailure::Incomplete);
    }
    Ok(offers)
}

fn client() -> Result<&'static reqwest::Client, DiscoveryFailure> {
    static CLIENT: OnceLock<Result<reqwest::Client, reqwest::Error>> = OnceLock::new();
    CLIENT
        .get_or_init(|| {
            reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .timeout(TIMEOUT)
                .build()
        })
        .as_ref()
        .map_err(|_| DiscoveryFailure::TransportUnavailable)
}

async fn fetch(
    url: &str,
    authentication: &DiscoveryAuthentication,
    qualification: Qualification,
    complete_inventory_guaranteed: bool,
) -> Result<Vec<DiscoveredOffer>, DiscoveryFailure> {
    let mut request = client()?
        .get(url)
        .header(header::ACCEPT, "application/json");
    if let DiscoveryAuthentication::Bearer { secret_env_var, .. } = authentication {
        // Reuse the process environment loaded by ENV_FILE/dotenvy. No pod lookup.
        let secret = crate::config::opt_env(secret_env_var)
            .ok_or(DiscoveryFailure::CredentialUnavailable)?;
        let mut bearer = header::HeaderValue::from_str(&format!("Bearer {secret}"))
            .map_err(|_| DiscoveryFailure::CredentialUnavailable)?;
        bearer.set_sensitive(true);
        request = request.header(header::AUTHORIZATION, bearer);
    }
    let mut response = request
        .send()
        .await
        .map_err(|_| DiscoveryFailure::TransportUnavailable)?;
    if response.status().is_redirection() {
        return Err(DiscoveryFailure::RedirectRefused);
    }
    if response.status() == StatusCode::PARTIAL_CONTENT {
        return Err(DiscoveryFailure::Incomplete);
    }
    if response.status() != StatusCode::OK {
        return Err(DiscoveryFailure::HttpUnavailable);
    }
    // Any HTTP-level pagination/range or unsupported content encoding is refused.
    if response.headers().contains_key(header::LINK)
        || response.headers().contains_key(header::CONTENT_RANGE)
    {
        return Err(DiscoveryFailure::Incomplete);
    }
    if response
        .headers()
        .get(header::CONTENT_ENCODING)
        .is_some_and(|v| v != "identity")
    {
        return Err(DiscoveryFailure::InvalidResponse);
    }
    let expected_length = response.content_length();
    if expected_length.is_some_and(|size| size > MAX_BYTES as u64) {
        return Err(DiscoveryFailure::TooLarge);
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response
        .chunk()
        .await
        .map_err(|_| DiscoveryFailure::Incomplete)?
    {
        if bytes.len() + chunk.len() > MAX_BYTES {
            return Err(DiscoveryFailure::TooLarge);
        }
        bytes.extend_from_slice(&chunk);
    }
    if expected_length.is_some_and(|size| size != bytes.len() as u64) {
        return Err(DiscoveryFailure::Incomplete);
    }
    parse(&bytes, qualification, complete_inventory_guaranteed)
}

fn declared_offer(model: &DeclaredModel) -> DiscoveredOffer {
    DiscoveredOffer {
        upstream_model_id: model.id.clone(),
        metadata: ModelMetadata {
            chat: Some(true),
            chat_provenance: Some(ChatProvenance::SourceGuarantee),
            reasoning: model.reasoning,
            embedding: None,
            vision: None,
            display_name: model.display_name.clone(),
            context_window_tokens: model.context_window_tokens,
            max_input_tokens: model.max_input_tokens,
            max_output_tokens: model.max_output_tokens,
        },
    }
}

pub(super) async fn discover(
    source: &ModelSource,
) -> Result<Vec<DiscoveredOffer>, DiscoveryFailure> {
    let mut offers = inventory(source).await?;
    for offer in &mut offers {
        if source.embedding_models.contains(&offer.upstream_model_id) {
            attest_embedding(&mut offer.metadata);
        }
    }
    Ok(offers)
}

/// The platform attestation overrides any chat qualification of the same offer.
fn attest_embedding(metadata: &mut ModelMetadata) {
    metadata.chat = Some(false);
    metadata.chat_provenance = Some(ChatProvenance::SourceGuarantee);
    metadata.reasoning = None;
    metadata.embedding = Some(true);
    metadata.vision = Some(false);
}

async fn inventory(source: &ModelSource) -> Result<Vec<DiscoveredOffer>, DiscoveryFailure> {
    match &source.inventory {
        SourceInventory::Declared { models } => Ok(models.iter().map(declared_offer).collect()),
        SourceInventory::Discovered {
            url,
            authentication,
            qualification,
            complete_inventory_guaranteed,
        } => tokio::time::timeout(
            TIMEOUT,
            fetch(
                url,
                authentication,
                *qualification,
                *complete_inventory_guaranteed,
            ),
        )
        .await
        .unwrap_or(Err(DiscoveryFailure::TransportUnavailable)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn a_declared_list_is_published_without_network_or_secret() {
        let source: ModelSource = serde_json::from_value(serde_json::json!({
            "source_id":"apim","revision":1,"enabled":true,
            "inventory":{"kind":"declared","models":[
                {"id":"gpt-4o","display_name":"GPT-4o","reasoning":false,
                    "context_window_tokens":128000,"max_input_tokens":100,"max_output_tokens":200},
                {"id":"bare"},
            ]},
            "inference":{"credential_binding":"b","api_root":"https://gateway.invalid/v1",
                "wire":"openai_chat","route":"standard","dialect":"openai_compatible",
                "auth":{"kind":"none"}},
            "visibility_scope":"account"}))
        .unwrap();
        let offers = discover(&source).await.unwrap();
        assert_eq!(
            serde_json::to_value(&offers).unwrap(),
            serde_json::json!([
                {"upstream_model_id":"gpt-4o","metadata":{"chat":true,
                    "chat_provenance":"source_guarantee","reasoning":false,
                    "embedding":null,"vision":null,"display_name":"GPT-4o","context_window_tokens":128000,
                    "max_input_tokens":100,"max_output_tokens":200}},
                {"upstream_model_id":"bare","metadata":{"chat":true,
                    "chat_provenance":"source_guarantee","reasoning":null,
                    "embedding":null,"vision":null,"display_name":null,"context_window_tokens":null,
                    "max_input_tokens":null,"max_output_tokens":null}},
            ])
        );
    }

    #[test]
    fn reasoning_is_a_discovered_boolean_never_a_name_guess() {
        for (value, expected) in [
            (serde_json::json!(true), Some(true)),
            (serde_json::json!(false), Some(false)),
            (serde_json::json!(null), None),
            (serde_json::json!("true"), None),
        ] {
            let item =
                serde_json::json!({"id": "arbitrary-model", "capabilities": {"reasoning": value}});
            assert_eq!(
                metadata(&item, Qualification::MixedCapabilitiesV1).reasoning,
                expected
            );
        }
        let item = serde_json::json!({"id": "mistral-small-latest"});
        assert_eq!(
            metadata(&item, Qualification::MixedCapabilitiesV1).reasoning,
            None
        );
    }

    #[tokio::test]
    async fn an_attested_embedding_offer_is_never_chat() {
        let source: ModelSource = serde_json::from_value(serde_json::json!({
            "source_id":"s","revision":1,"enabled":true,
            "inventory":{"kind":"declared","models":[{"id":"chat"},{"id":"embed"}]},
            "inference":{"credential_binding":"b","api_root":"https://gateway.invalid/v1",
                "wire":"openai_chat","route":"standard","dialect":"openai",
                "auth":{"kind":"api_key"}},
            "visibility_scope":"account","embedding_models":["embed"]}))
        .unwrap();
        let offers = discover(&source).await.unwrap();
        let (chat, embed) = (&offers[0].metadata, &offers[1].metadata);
        assert_eq!((chat.chat, chat.embedding), (Some(true), None));
        assert_eq!(
            (embed.chat, embed.embedding, embed.vision),
            (Some(false), Some(true), Some(false))
        );
    }

    #[test]
    fn vision_is_a_discovered_boolean() {
        let item =
            serde_json::json!({"id":"m","capabilities":{"completion_chat":true,"vision":true}});
        assert_eq!(
            metadata(&item, Qualification::MixedCapabilitiesV1).vision,
            Some(true)
        );
        assert_eq!(metadata(&item, Qualification::ChatSource).vision, None);
    }
}
