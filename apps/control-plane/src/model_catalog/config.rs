// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::HashSet;

use anyhow::{Result, ensure};
use fred_rust_sdk::inference::ModelConnection;
pub(super) use fred_rust_sdk::inference::bounded_text;
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;

/// Platform approval of one source. Contains references only, never secret values.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelSource {
    pub source_id: String,
    /// Strictly increase for every configuration change, including secret rotation.
    pub revision: i64,
    #[serde(default)]
    pub enabled: bool,
    pub discovery_url: String,
    pub inference: ModelConnection,
    /// Stable provider account, model namespace and list visibility contract.
    /// A changed account/namespace/scope needs a new source_id, even with the same URL.
    pub visibility_scope: String,
    pub authentication: DiscoveryAuthentication,
    pub qualification: Qualification,
    /// Platform attests that an unpaginated response lists the entire visibility scope.
    /// Without this guarantee, discovery cannot publish an authoritative inventory.
    pub complete_inventory_guaranteed: bool,
    /// Explicit platform approval for internal HTTP routes; HTTPS is the default.
    #[serde(default)]
    pub allow_insecure_http: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(tag = "mode", rename_all = "snake_case", deny_unknown_fields)]
pub enum DiscoveryAuthentication {
    Public,
    Bearer {
        secret_env_var: String,
        /// Actual provider scopes, reviewed by the platform; a separate key proves nothing.
        provider_scopes: Vec<String>,
        authority: CredentialAuthority,
        #[serde(default)]
        accept_inference_authority: bool,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum CredentialAuthority {
    DiscoveryOnly,
    DiscoveryAndInference,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum Qualification {
    /// Platform guarantees chat for every advertised model.
    ChatSource,
    /// Platform trusts the boolean capabilities.completion_chat and reasoning extensions.
    MixedCapabilitiesV1,
}

pub(crate) fn valid_source_id(value: &str) -> bool {
    bounded_text(value, 64)
        && value.starts_with(|c: char| c.is_ascii_alphanumeric())
        && value
            .bytes()
            .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c))
}

fn approved_url(value: &str, allow_http: bool) -> bool {
    bounded_text(value, 2048)
        && reqwest::Url::parse(value).is_ok_and(|url| {
            (url.scheme() == "https" || (allow_http && url.scheme() == "http"))
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
        })
}

pub fn validate_sources(sources: &[ModelSource]) -> Result<()> {
    let mut ids = HashSet::new();
    for source in sources {
        source.validate()?;
        ensure!(ids.insert(&source.source_id), "duplicate model source_id");
    }
    Ok(())
}

impl ModelSource {
    pub fn validate(&self) -> Result<()> {
        ensure!(valid_source_id(&self.source_id), "invalid model source_id");
        ensure!(self.revision > 0, "model source revision must be positive");
        ensure!(
            approved_url(&self.discovery_url, self.allow_insecure_http)
                && approved_url(&self.inference.api_root, self.allow_insecure_http),
            "model source requires separately approved HTTP(S) destinations without credentials, query or fragment"
        );
        self.inference.validate()?;
        ensure!(
            bounded_text(&self.visibility_scope, 256),
            "invalid model source visibility"
        );
        if let DiscoveryAuthentication::Bearer {
            secret_env_var,
            provider_scopes,
            authority,
            accept_inference_authority,
        } = &self.authentication
        {
            ensure!(
                bounded_text(secret_env_var, 128)
                    && secret_env_var.starts_with(|c: char| c.is_ascii_alphabetic() || c == '_')
                    && secret_env_var
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_'),
                "invalid discovery secret environment reference"
            );
            ensure!(
                !provider_scopes.is_empty()
                    && provider_scopes.len() <= 32
                    && provider_scopes.iter().all(|s| bounded_text(s, 128)),
                "discovery credential requires explicit actual provider scopes"
            );
            ensure!(
                *authority != CredentialAuthority::DiscoveryAndInference
                    || *accept_inference_authority,
                "discovery credential inference authority requires explicit platform acceptance"
            );
        }
        Ok(())
    }

    pub(super) fn same_identity(&self, other: &Self) -> bool {
        self.source_id == other.source_id
            && self.discovery_url == other.discovery_url
            && self.inference.api_root == other.inference.api_root
            && self.inference.wire == other.inference.wire
            && self.inference.route == other.inference.route
            && self.visibility_scope == other.visibility_scope
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{Value, json};

    fn source(changes: Value) -> Result<ModelSource> {
        let mut value = json!({"source_id":"s","revision":1,"enabled":true,
            "discovery_url":"https://catalog.invalid/models",
            "inference":{"credential_binding":"b","api_root":"https://gateway.invalid/v1",
                "wire":"openai_chat","route":"standard","dialect":"openai",
                "auth":{"kind":"api_key"}},
            "visibility_scope":"account","authentication":{"mode":"public"},
            "qualification":"chat_source","complete_inventory_guaranteed":true});
        for (field, change) in changes.as_object().unwrap() {
            value["inference"][field] = change.clone();
        }
        let source: ModelSource = serde_json::from_value(value)?;
        source.validate()?;
        Ok(source)
    }

    #[test]
    fn insecure_http_needs_the_platform_approval_and_never_serves_entra() {
        let http = json!({"api_root":"http://ollama:11434/v1","auth":{"kind":"none"}});
        assert!(source(http.clone()).is_err());
        let mut approved = serde_json::to_value(source(json!({})).unwrap()).unwrap();
        approved["allow_insecure_http"] = true.into();
        approved["discovery_url"] = "http://ollama:11434/v1/models".into();
        approved["inference"]["api_root"] = "http://ollama:11434/v1".into();
        approved["inference"]["auth"] = json!({"kind":"none"});
        let approved: ModelSource = serde_json::from_value(approved.clone()).unwrap();
        approved.validate().unwrap();
        let mut entra = approved.clone();
        entra.inference.auth.kind = fred_rust_sdk::inference::ModelAuthKind::Entra;
        entra.inference.auth.tenant_id = Some("t".into());
        entra.inference.auth.client_id = Some("c".into());
        entra.inference.auth.scope = Some("s".into());
        assert!(entra.validate().is_err());
    }

    #[test]
    fn identity_is_the_destination_and_its_protocol_not_its_authentication() {
        let base = source(json!({})).unwrap();
        for changes in [
            json!({"api_root":"https://other.invalid/v1"}),
            json!({"wire":"openai_responses"}),
            json!({"route":"azure_deployment","api_version":"1"}),
        ] {
            assert!(
                !base.same_identity(&source(changes.clone()).unwrap()),
                "{changes}"
            );
        }
        for changes in [
            json!({"dialect":"mistral"}),
            json!({"api_version":"1"}),
            json!({"credential_binding":"other"}),
            json!({"auth":{"kind":"none"}}),
            json!({"auth":{"kind":"api_key","gateway_key_header":"x-key"}}),
        ] {
            assert!(
                base.same_identity(&source(changes.clone()).unwrap()),
                "{changes}"
            );
        }
    }

    #[test]
    fn the_former_format_is_refused() {
        assert!(source(json!({"provider":"openai"})).is_err());
    }
}
