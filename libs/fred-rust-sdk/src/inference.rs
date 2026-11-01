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

#[derive(Debug, Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ModelConnection {
    pub provider: String,
    pub api_root: String,
    pub credential_binding: String,
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
    pub source_id: String,
    pub source_revision: i64,
    pub api_root: String,
    pub credential_binding: String,
    pub api_key_env: String,
}

impl InferenceCredentialBinding {
    pub fn validate(&self) -> anyhow::Result<()> {
        let url = reqwest::Url::parse(&self.api_root)?;
        anyhow::ensure!(
            self.source_revision > 0
                && !self.source_id.trim().is_empty()
                && !self.credential_binding.trim().is_empty()
                && matches!(url.scheme(), "http" | "https")
                && url.host_str().is_some()
                && url.username().is_empty()
                && url.password().is_none()
                && url.query().is_none()
                && url.fragment().is_none()
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

    /// Must succeed before reading the named environment variable.
    pub fn matches(&self, admission: &InferenceAdmission) -> bool {
        self.validate().is_ok()
            && admission.connection.provider == "openai"
            && self.source_id == admission.selection.key.source_id
            && self.source_revision == admission.selection.source_revision
            && self.api_root == admission.connection.api_root
            && self.credential_binding == admission.connection.credential_binding
    }
}
