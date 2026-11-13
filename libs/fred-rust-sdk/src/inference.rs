// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Control Plane's admitted inference contract. No secret values cross this boundary.
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

#[derive(
    Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize, ToSchema, sqlx::FromRow,
)]
#[serde(deny_unknown_fields)]
pub struct ModelOfferKey {
    pub source_id: String,
    pub upstream_model_id: String,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelSelectionSource {
    UserChoice,
    InstanceRecommendation,
    Default,
    WithdrawalFallback,
}

#[derive(Debug, Clone, Default, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct EffectiveModelOptions {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub temperature: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_tokens: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub top_p: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reasoning_effort: Option<ReasoningEffort>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ReasoningEffort {
    High,
}

/// Browser-safe result; attribution to person/space/instance stays in RuntimeBinding.
#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct InferenceSelection {
    pub key: ModelOfferKey,
    pub source: ModelSelectionSource,
    pub options: EffectiveModelOptions,
    pub source_revision: i64,
    pub snapshot_revision: i64,
    pub policy_revision: i64,
}

/// Inference protocol. An attested embedding offer is called at `{api_root}/embeddings`;
/// a rerank offer is called at `{api_root}/rerank`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelWire {
    OpenaiChat,
    OpenaiResponses,
    Rerank,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelRoute {
    Standard,
    AzureDeployment,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelDialect {
    /// OpenAI and Azure OpenAI themselves.
    Openai,
    /// A server that reads the token ceiling only from `max_tokens`, with `stream_options`.
    OpenaiCompatible,
    Mistral,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ModelAuthKind {
    None,
    ApiKey,
    Entra,
}

/// Authentication facts only: the secrets stay in the workload's local binding.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelAuth {
    pub kind: ModelAuthKind,
    /// Required with kind `entra`, forbidden otherwise, like `client_id` and `scope`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tenant_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub client_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub scope: Option<String>,
    /// Name of the header carrying a gateway key, with any kind.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub gateway_key_header: Option<String>,
}

/// One destination, independent of the vendor: protocol, address and authentication.
/// Mirrored by `fred_sdk.contracts.weaver`; `inference_connections.json` pins both.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelConnection {
    /// Source-bound workload provisioning reference; never a credential value.
    pub credential_binding: String,
    /// Separately approved canonical root; never derived from a discovery URL.
    pub api_root: String,
    pub wire: ModelWire,
    pub route: ModelRoute,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub api_version: Option<String>,
    pub dialect: ModelDialect,
    pub auth: ModelAuth,
}

pub fn bounded_text(value: &str, max_bytes: usize) -> bool {
    !value.is_empty()
        && value.len() <= max_bytes
        && value.trim() == value
        && !value.chars().any(char::is_control)
}

/// Runtimes compare this root byte for byte, so the parser must have nothing to normalize:
/// host case, default port, dot segments. These characters exclude credentials, query,
/// fragment, percent-encoding and IPv6 literals (use a DNS name).
fn canonical_api_root(value: &str) -> bool {
    let Ok(url) = reqwest::Url::parse(value) else {
        return false;
    };
    let rendered = url.as_str();
    value.len() <= 2048
        && matches!(url.scheme(), "http" | "https")
        && url.port() != Some(0)
        && !url.path().contains("//")
        && rendered.strip_suffix('/').unwrap_or(rendered) == value
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._~:/-".contains(&c))
}

fn gateway_header(name: &str) -> bool {
    let lower = name.to_ascii_lowercase();
    name.len() <= 128
        && reqwest::header::HeaderName::from_bytes(name.as_bytes()).is_ok()
        && !matches!(
            lower.as_str(),
            "authorization" | "host" | "cookie" | "transfer-encoding"
        )
        && !lower.starts_with("content-")
}

impl ModelConnection {
    /// Shape only; `allow_insecure_http` remains the Control Plane's own rule.
    pub fn validate(&self) -> anyhow::Result<()> {
        let entra = self.auth.kind == ModelAuthKind::Entra;
        let entra_fact = |fact: &Option<String>, max_bytes| match fact {
            Some(value) => entra && bounded_text(value, max_bytes),
            None => !entra,
        };
        anyhow::ensure!(
            bounded_text(&self.credential_binding, 128)
                && canonical_api_root(&self.api_root)
                && (!entra || self.api_root.starts_with("https://"))
                && (self.route == ModelRoute::Standard
                    || (self.wire == ModelWire::OpenaiChat && self.api_version.is_some()))
                && (self.wire != ModelWire::Rerank || self.api_version.is_none())
                && self.api_version.as_deref().is_none_or(|version| {
                    !version.is_empty()
                        && version.len() <= 64
                        && version
                            .bytes()
                            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
                })
                && self
                    .auth
                    .gateway_key_header
                    .as_deref()
                    .is_none_or(gateway_header)
                && entra_fact(&self.auth.tenant_id, 128)
                && entra_fact(&self.auth.client_id, 128)
                && entra_fact(&self.auth.scope, 256),
            "Invalid inference connection"
        );
        Ok(())
    }
}

/// Internal or trusted delegated response only. Never put this in browser preparation.
#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct InferenceAdmission {
    pub selection: InferenceSelection,
    pub connection: ModelConnection,
}

/// Local deployment attestation, independent of the received admission.
#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct InferenceCredentialBinding {
    pub credential_binding: String,
    pub api_root: String,
    pub api_key_env: String,
}

impl InferenceCredentialBinding {
    pub fn validate(&self) -> anyhow::Result<()> {
        anyhow::ensure!(
            bounded_text(&self.credential_binding, 128)
                && canonical_api_root(&self.api_root)
                && self
                    .api_key_env
                    .starts_with(|c: char| c.is_ascii_alphabetic() || c == '_')
                && self
                    .api_key_env
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'_'),
            "Invalid inference provisioning"
        );
        Ok(())
    }

    /// Must succeed before reading the named environment variable. This workload only
    /// reaches a chat completions URL, without query, with this binding's own key.
    pub fn matches(&self, admission: &InferenceAdmission) -> bool {
        let connection = &admission.connection;
        self.validate().is_ok()
            && connection.wire == ModelWire::OpenaiChat
            && connection.route == ModelRoute::Standard
            && connection.api_version.is_none()
            && connection.auth.kind == ModelAuthKind::ApiKey
            && connection.auth.gateway_key_header.is_none()
            && self.api_root == connection.api_root
            && self.credential_binding == connection.credential_binding
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::Value;

    const CONNECTIONS: &str =
        include_str!("../../fred-sdk/tests/fixtures/inference_connections.json");

    fn parsed(connection: Value) -> anyhow::Result<ModelConnection> {
        let connection: ModelConnection = serde_json::from_value(connection)?;
        connection.validate()?;
        Ok(connection)
    }

    #[test]
    fn shared_fixture_decides_like_the_python_contract() {
        let fixture: Value = serde_json::from_str(CONNECTIONS).unwrap();
        for case in fixture["valid"].as_array().unwrap() {
            let connection = parsed(case["connection"].clone())
                .unwrap_or_else(|error| panic!("{}: {error}", case["name"]));
            assert_eq!(
                serde_json::to_value(&connection).unwrap(),
                case["connection"],
                "{}",
                case["name"]
            );
        }
        parsed(fixture["invalid_base"].clone()).unwrap();
        for case in fixture["invalid"].as_array().unwrap() {
            let mut connection = fixture["invalid_base"].clone();
            for (field, value) in case["changes"].as_object().unwrap() {
                match value {
                    Value::Null => connection.as_object_mut().unwrap().remove(field),
                    _ => connection
                        .as_object_mut()
                        .unwrap()
                        .insert(field.clone(), value.clone()),
                };
            }
            assert!(parsed(connection).is_err(), "{}", case["name"]);
        }
        let mut too_long = fixture["invalid_base"].clone();
        too_long["api_root"] = format!("https://gateway.invalid/{}", "a".repeat(2048)).into();
        assert!(parsed(too_long).is_err());
    }

    fn admission(changes: Value) -> InferenceAdmission {
        let mut value: Value = serde_json::from_str(include_str!(
            "../../fred-sdk/tests/fixtures/inference_admission.json"
        ))
        .unwrap();
        for (field, change) in changes.as_object().unwrap() {
            value["connection"][field] = change.clone();
        }
        serde_json::from_value(value).unwrap()
    }

    #[test]
    fn binding_only_matches_a_connection_this_workload_can_reach() {
        let binding = InferenceCredentialBinding {
            credential_binding: "source-account".into(),
            api_root: "https://source.invalid/v1".into(),
            api_key_env: "KEY".into(),
        };
        assert!(binding.matches(&admission(serde_json::json!({}))));
        for changes in [
            serde_json::json!({"wire": "openai_responses"}),
            serde_json::json!({"route": "azure_deployment", "api_version": "1"}),
            serde_json::json!({"api_version": "1"}),
            serde_json::json!({"auth": {"kind": "none"}}),
            serde_json::json!({"auth": {"kind": "api_key", "gateway_key_header": "x-key"}}),
            serde_json::json!({"auth": {"kind": "entra", "tenant_id": "t", "client_id": "c", "scope": "s"}}),
            serde_json::json!({"api_root": "https://other.invalid/v1"}),
            serde_json::json!({"credential_binding": "other"}),
        ] {
            assert!(!binding.matches(&admission(changes.clone())), "{changes}");
        }
    }

    #[test]
    fn binding_refuses_a_non_canonical_root_and_former_fields() {
        let binding = |api_root: &str| InferenceCredentialBinding {
            credential_binding: "binding".into(),
            api_root: api_root.into(),
            api_key_env: "KEY".into(),
        };
        assert!(binding("http://ollama:11434/v1").validate().is_ok());
        assert!(binding("https://source.invalid/v1/").validate().is_err());
        assert!(
            serde_json::from_value::<InferenceCredentialBinding>(serde_json::json!({
                "source_id": "s", "source_revision": 1, "credential_binding": "b",
                "api_root": "https://source.invalid/v1", "api_key_env": "KEY"
            }))
            .is_err()
        );
    }
}
