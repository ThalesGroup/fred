// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Space-owned MCP connections. Governance belongs to agents::enablement;
//! this module owns configuration, observation and admitted technical facts only.
mod discovery;
mod http;
mod store;

pub(crate) use http::routes;
pub(crate) use store::{available_offers, bindings, extend_template};

use anyhow::{Result, ensure};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use utoipa::ToSchema;
use uuid::Uuid;

pub const TABULAR_CAPABILITY_ID: &str = "mcp-knowledge-flow-mcp-tabular";

pub const SOURCE_ID: &str = "$mcp";
pub const MAX_TOOLS: usize = 256;
pub const MAX_BYTES: usize = 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum McpAuthentication {
    None,
    Bearer {
        credential_binding: String,
    },
    ApiKey {
        credential_binding: String,
        header: String,
    },
}

#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct McpConfiguration {
    pub url: String,
    pub authentication: McpAuthentication,
    #[serde(default)]
    pub allow_insecure_http: bool,
}

/// Local deployment attestation; names only. Never sent to browsers or admission.
#[derive(Debug, Clone, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct McpCredentialBinding {
    pub space_id: Uuid,
    pub credential_binding: String,
    pub url: String,
    pub secret_env: String,
}

impl McpConfiguration {
    pub fn validate(&self, space_id: Uuid, bindings: &[McpCredentialBinding]) -> Result<()> {
        ensure!(
            crate::model_catalog::config::approved_url(&self.url, self.allow_insecure_http),
            "invalid MCP destination"
        );
        if let McpAuthentication::ApiKey { header, .. } = &self.authentication {
            ensure!(
                header.to_ascii_lowercase().starts_with("x-")
                    && !header.to_ascii_lowercase().starts_with("x-fred-")
                    && header.len() > 2
                    && header[2..]
                        .bytes()
                        .all(|c| c.is_ascii_alphanumeric() || c == b'_' || c == b'-')
                    && reqwest::header::HeaderName::from_bytes(header.as_bytes()).is_ok(),
                "invalid MCP API key header"
            );
        }
        if let Some(reference) = self.credential_reference() {
            ensure!(
                bindings.iter().any(|b| b.space_id == space_id
                    && b.credential_binding == reference
                    && b.url == self.url),
                "MCP credential destination mismatch"
            );
        }
        Ok(())
    }

    pub fn credential_reference(&self) -> Option<&str> {
        match &self.authentication {
            McpAuthentication::None => None,
            McpAuthentication::Bearer { credential_binding }
            | McpAuthentication::ApiKey {
                credential_binding, ..
            } => Some(credential_binding),
        }
    }
}

pub fn tabular_endpoint(base: Option<&str>) -> Result<String> {
    let base = base.ok_or_else(|| anyhow::anyhow!("Knowledge Flow is not configured"))?;
    ensure!(
        crate::model_catalog::config::approved_url(base, true),
        "invalid Knowledge Flow destination"
    );
    Ok(format!("{}/mcp/tabular", base.trim_end_matches('/')))
}

pub fn validate_credentials(bindings: &[McpCredentialBinding]) -> Result<()> {
    let mut ids = std::collections::HashSet::new();
    for binding in bindings {
        ensure!(
            !binding.credential_binding.is_empty()
                && binding.credential_binding.len() <= 128
                && ids.insert(&binding.credential_binding),
            "invalid or duplicate MCP credential binding"
        );
        ensure!(
            crate::model_catalog::config::approved_url(&binding.url, true),
            "invalid approved MCP credential destination"
        );
        ensure!(
            binding
                .secret_env
                .as_bytes()
                .first()
                .is_some_and(|c| c.is_ascii_alphabetic() || *c == b'_')
                && binding
                    .secret_env
                    .bytes()
                    .all(|c| c.is_ascii_alphanumeric() || c == b'_'),
            "invalid MCP credential environment reference"
        );
    }
    Ok(())
}

/// Reviewed contract, not a permission per tool. Additional remote tools are ignored.
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct McpTool {
    pub name: String,
    pub description: Option<String>,
    pub input_schema: Value,
    pub output_schema: Option<Value>,
    pub annotations: Option<Value>,
}

/// Differences from the reviewed inventory, using the same complete contracts as admission.
#[derive(Serialize, ToSchema)]
pub struct McpToolChanges {
    pub added: Vec<String>,
    pub modified: Vec<String>,
    pub removed: Vec<String>,
}

#[derive(Clone, Serialize, Deserialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum McpBinding {
    Connection {
        connection_id: Uuid,
        capability_id: String,
        revision: i64,
        display_name: String,
        configuration: McpConfiguration,
        tools: Vec<McpTool>,
    },
    /// Internal Fred service: no connection, publication or second permission.
    KnowledgeFlowTabular { url: String },
}

#[derive(Clone, sqlx::FromRow)]
pub(super) struct Connection {
    pub space_id: Uuid,
    pub id: Uuid,
    pub logical_name: String,
    pub display_name: String,
    pub description: String,
    pub revision: i64,
    pub configuration: sqlx::types::Json<McpConfiguration>,
    pub enabled: bool,
    pub observation_revision: Option<i64>,
    pub observation_state: String,
    pub error_code: Option<String>,
    pub checked_at: Option<chrono::DateTime<chrono::Utc>>,
    pub last_success_at: Option<chrono::DateTime<chrono::Utc>>,
    pub observed_tools: sqlx::types::Json<Vec<McpTool>>,
    pub published_tools: sqlx::types::Json<Vec<McpTool>>,
    pub published_revision: Option<i64>,
}

impl Connection {
    pub fn tool_changes(&self) -> Option<McpToolChanges> {
        if self.observation_state != "available" || self.observation_revision != Some(self.revision)
        {
            return None;
        }
        let mut changes = McpToolChanges {
            added: vec![],
            modified: vec![],
            removed: vec![],
        };
        for tool in self.observed_tools.iter() {
            match self
                .published_tools
                .iter()
                .find(|previous| previous.name == tool.name)
            {
                None => changes.added.push(tool.name.clone()),
                Some(previous) if previous != tool => changes.modified.push(tool.name.clone()),
                Some(_) => {}
            }
        }
        changes.removed = self
            .published_tools
            .iter()
            .filter(|tool| {
                !self
                    .observed_tools
                    .iter()
                    .any(|current| current.name == tool.name)
            })
            .map(|tool| tool.name.clone())
            .collect();
        Some(changes)
    }

    pub fn capability_id(&self) -> String {
        format!("managed-mcp:{}", self.id)
    }

    pub fn available(&self) -> bool {
        self.enabled
            && self.observation_state == "available"
            && self.observation_revision == Some(self.revision)
            && self.published_revision == Some(self.revision)
            && !self.published_tools.0.is_empty()
            && self
                .published_tools
                .iter()
                .all(|tool| self.observed_tools.contains(tool))
    }

    pub fn descriptor(&self) -> Value {
        json!({"id": self.capability_id(), "source_id": self.logical_name,
            "runtime_id": null, "version": "1", "public_version": null,
            "name": self.display_name, "description": self.description,
            "icon": "extension", "kind": "tool", "origin": "managed_mcp",
            "config_fields": [], "team_settings_fields": [], "execution_models": ["react", "graph"]})
    }
}

#[cfg(test)]
mod tests;
