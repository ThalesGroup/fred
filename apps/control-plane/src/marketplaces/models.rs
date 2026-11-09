// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::BTreeMap;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum MarketplaceKind {
    Prompt,
    Skill,
    Agent,
}

impl MarketplaceKind {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Prompt => "prompt",
            Self::Skill => "skill",
            Self::Agent => "agent",
        }
    }
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct PromptPackage {
    pub logical_name: String,
    pub display_name: String,
    pub description: Option<String>,
    pub tags: Vec<String>,
    pub text: String,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SkillPackage {
    pub name: String,
    pub files: BTreeMap<String, String>,
}

/// Capability owners interpret these versioned envelopes; CP never copies raw tuning.
#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportedCapability {
    pub schema_version: String,
    pub config: BTreeMap<String, serde_json::Value>,
    /// Exported configuration files, indexed by asset key and encoded as base64.
    pub files: BTreeMap<String, String>,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AgentPackage {
    pub runtime_id: String,
    pub template_agent_id: String,
    pub logical_name: String,
    pub display_name: String,
    pub description: Option<String>,
    pub role: String,
    pub usage_statement: String,
    /// Only fields certified exportable by the owning pod, never opaque saved tuning.
    pub tuning_field_values: BTreeMap<String, serde_json::Value>,
    pub capabilities: BTreeMap<String, ExportedCapability>,
    pub recommended_model: Option<crate::model_catalog::instance::ModelOfferKey>,
    pub model_options: crate::model_catalog::instance::ModelOptions,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(
    tag = "kind",
    content = "content",
    rename_all = "snake_case",
    deny_unknown_fields
)]
pub enum MarketplacePackage {
    Prompt(PromptPackage),
    Skill(SkillPackage),
    Agent(AgentPackage),
}

impl MarketplacePackage {
    pub(super) fn kind(&self) -> MarketplaceKind {
        match self {
            Self::Prompt(_) => MarketplaceKind::Prompt,
            Self::Skill(_) => MarketplaceKind::Skill,
            Self::Agent(_) => MarketplaceKind::Agent,
        }
    }
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct SubmitProposalRequest {
    pub source_space_id: Uuid,
    pub source_resource_id: Uuid,
    pub kind: MarketplaceKind,
    /// Prompt updated_at, skill revision, or agent configuration_revision as a string.
    pub expected_revision: String,
    /// Absent creates an independent entry. Set explicitly for a replacement proposal.
    pub entry_id: Option<Uuid>,
}

#[derive(Clone, Copy, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum ProposalState {
    Pending,
    Approved,
    Rejected,
    Cancelled,
}

impl ProposalState {
    pub(super) fn as_str(self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Approved => "approved",
            Self::Rejected => "rejected",
            Self::Cancelled => "cancelled",
        }
    }
}

#[derive(Default, Serialize, ToSchema, sqlx::FromRow)]
pub struct ProposalActions {
    pub can_decide: bool,
    pub can_cancel: bool,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct ProposalSummary {
    pub proposal_id: Uuid,
    pub entry_id: Uuid,
    pub marketplace_space_id: Uuid,
    pub proposing_space_id: Option<Uuid>,
    #[sqlx(try_from = "String")]
    pub kind: MarketplaceKind,
    pub origin_name: String,
    pub display_name: String,
    pub description: String,
    pub package_hash: String,
    pub submitted_by: String,
    pub submitted_at: DateTime<Utc>,
    #[sqlx(try_from = "String")]
    pub state: ProposalState,
    pub decided_by: Option<String>,
    pub decided_at: Option<DateTime<Utc>>,
    pub decision_reason: Option<String>,
    /// Current catalogue version, independent of this proposal's terminal decision.
    pub publication_version: i64,
    pub published_proposal_id: Option<Uuid>,
    #[sqlx(flatten)]
    pub actions: ProposalActions,
}

#[derive(Serialize, ToSchema)]
pub struct MarketplaceProposal {
    #[serde(flatten)]
    pub proposal: ProposalSummary,
    pub package: MarketplacePackage,
}

#[derive(Serialize, ToSchema)]
pub struct ProposalPage {
    #[schema(max_items = 100)]
    pub items: Vec<ProposalSummary>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct MarketplaceEntrySummary {
    pub entry_id: Uuid,
    pub marketplace_space_id: Uuid,
    #[sqlx(try_from = "String")]
    pub kind: MarketplaceKind,
    pub proposal_id: Uuid,
    pub publication_version: i64,
    pub published_at: DateTime<Utc>,
    pub display_name: String,
    pub description: String,
    pub origin_name: String,
    pub package_hash: String,
    pub can_withdraw: bool,
}

#[derive(Serialize, ToSchema)]
pub struct MarketplaceEntryDetail {
    #[serde(flatten)]
    pub entry: MarketplaceEntrySummary,
    pub package: MarketplacePackage,
}

#[derive(Serialize, ToSchema)]
pub struct MarketplaceEntryPage {
    #[schema(max_items = 100)]
    pub items: Vec<MarketplaceEntrySummary>,
    #[schema(required = true)]
    pub next_cursor: Option<Uuid>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct ProposalDecisionRequest {
    pub approve: bool,
    pub reason: Option<String>,
    pub expected_publication_version: i64,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct WithdrawRequest {
    pub expected_publication_version: i64,
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum InstallOptions {
    Prompt {
        logical_name: String,
        category_id: Option<Uuid>,
    },
    Skill,
    Agent {
        logical_name: Option<String>,
        display_name: String,
    },
}

#[derive(Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct InstallRequest {
    pub proposal_id: Uuid,
    pub destination_space_id: Uuid,
    pub options: InstallOptions,
}

#[derive(Serialize, ToSchema, sqlx::FromRow)]
pub struct InstallationReceipt {
    pub installation_id: Uuid,
    pub entry_id: Uuid,
    pub proposal_id: Uuid,
    pub package_hash: String,
    #[sqlx(try_from = "String")]
    pub kind: MarketplaceKind,
    pub space_id: Uuid,
    pub resource_id: Uuid,
    pub installed_at: DateTime<Utc>,
    pub resource_exists: bool,
}

impl TryFrom<String> for MarketplaceKind {
    type Error = anyhow::Error;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        Ok(serde_json::from_value(serde_json::Value::String(value))?)
    }
}

impl TryFrom<String> for ProposalState {
    type Error = anyhow::Error;
    fn try_from(value: String) -> Result<Self, Self::Error> {
        Ok(serde_json::from_value(serde_json::Value::String(value))?)
    }
}
