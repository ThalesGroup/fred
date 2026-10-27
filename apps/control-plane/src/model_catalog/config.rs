// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::HashSet;

use anyhow::{Result, ensure};
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
    pub inference: InferenceDestination,
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
#[serde(deny_unknown_fields)]
pub struct InferenceDestination {
    pub provider: String,
    /// Separately approved root; never derived from discovery_url.
    pub api_root: String,
    /// Source-bound pod provisioning reference. Rust never resolves this credential.
    pub credential_binding: String,
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

pub(super) fn bounded_text(value: &str, max_bytes: usize) -> bool {
    !value.is_empty()
        && value.len() <= max_bytes
        && value.trim() == value
        && !value.chars().any(char::is_control)
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
        ensure!(
            bounded_text(&self.source_id, 64)
                && self
                    .source_id
                    .starts_with(|c: char| c.is_ascii_alphanumeric())
                && self
                    .source_id
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || b"._-".contains(&c)),
            "invalid model source_id"
        );
        ensure!(self.revision > 0, "model source revision must be positive");
        ensure!(
            approved_url(&self.discovery_url, self.allow_insecure_http)
                && approved_url(&self.inference.api_root, self.allow_insecure_http),
            "model source requires separately approved HTTP(S) destinations without credentials, query or fragment"
        );
        ensure!(
            bounded_text(&self.visibility_scope, 256)
                && bounded_text(&self.inference.provider, 64)
                && bounded_text(&self.inference.credential_binding, 128),
            "invalid model source visibility or inference binding"
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
            && self.inference.provider == other.inference.provider
            && self.inference.api_root == other.inference.api_root
            && self.visibility_scope == other.visibility_scope
    }
}
