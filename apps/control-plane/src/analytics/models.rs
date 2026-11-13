// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

use std::collections::BTreeMap;

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use utoipa::ToSchema;
use uuid::Uuid;

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AnalyticsRequest {
    #[schema(min_items = 1, max_items = 8)]
    pub queries: Vec<AnalyticsQuery>,
}

#[derive(Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AnalyticsQuery {
    #[schema(min_length = 1, max_length = 64)]
    pub name: String,
    pub scope: AnalyticsScope,
    pub time: AnalyticsPeriod,
    #[schema(min_items = 1, max_items = 12)]
    pub measures: Vec<ConsumptionMeasure>,
    /// Consumption: total/time/agent/model; retained sessions: total; turns: total/agent/space; skills: skill.
    #[serde(default)]
    #[schema(max_items = 1)]
    pub group_by: Vec<AnalyticsGrouping>,
    /// Rankings only, default 100. Descending tokens, loads or turns, then stable identity.
    #[schema(minimum = 1, maximum = 100)]
    pub limit: Option<usize>,
}

#[derive(Clone, Debug, PartialEq, Eq, Deserialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum AnalyticsScope {
    #[serde(rename = "self")]
    Personal { organization_id: Uuid },
    /// Direct ReadUsage on a team/project. Teams include retired/purged projects.
    Space { id: Uuid },
}

#[derive(Clone, Debug, Deserialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AnalyticsPeriod {
    /// Inclusive instant with offset. Maximum duration: 366 days.
    pub since: DateTime<Utc>,
    /// Exclusive instant with offset.
    pub until: DateTime<Utc>,
    pub timezone: AnalyticsTimezone,
    /// Time grouping only. Omission chooses hour <=48h, day <=92d, week otherwise.
    pub bucket: Option<AnalyticsInterval>,
}

#[derive(Clone, Copy, Debug, Deserialize, Serialize, ToSchema)]
pub enum AnalyticsTimezone {
    #[serde(rename = "UTC")]
    Utc,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum AnalyticsInterval {
    Hour,
    Day,
    Week,
}

impl AnalyticsInterval {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            Self::Hour => "hour",
            Self::Day => "day",
            Self::Week => "week",
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum AnalyticsGrouping {
    Time,
    Agent,
    Model,
    Skill,
    Space,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize, ToSchema)]
pub enum ConsumptionMeasure {
    #[serde(rename = "usage.input_tokens")]
    InputTokens,
    #[serde(rename = "usage.output_tokens")]
    OutputTokens,
    #[serde(rename = "usage.cache_read_tokens")]
    CacheReadTokens,
    #[serde(rename = "usage.cache_creation_tokens")]
    CacheCreationTokens,
    /// Input + output; cache counters are not added again.
    #[serde(rename = "usage.total_tokens")]
    TotalTokens,
    /// Distinct recorded (session, exchange) at first consumption, including generated titles.
    /// HITL resumes add tokens without another exchange. Not additive across models; not messages.
    #[serde(rename = "usage.recorded_exchanges")]
    RecordedExchanges,
    #[serde(rename = "usage.cost_eur")]
    CostEur,
    #[serde(rename = "usage.co2e_grams")]
    Co2eGrams,
    #[serde(rename = "usage.energy_kwh")]
    EnergyKwh,
    #[serde(rename = "skills.user_loads")]
    UserSkillLoads,
    #[serde(rename = "skills.agent_loads")]
    AgentSkillLoads,
    #[serde(rename = "skills.total_loads")]
    TotalSkillLoads,
    /// Created in the window and still retained (not marked for deletion). SQL creation date.
    #[serde(rename = "activity.retained_conversations")]
    RetainedConversations,
    /// Observed agent.turn_completed events at completion, including errors and HITL resumes.
    /// Titles and retries that emit no completion event do not count; this is not unique messages.
    #[serde(rename = "activity.completed_turns")]
    CompletedTurns,
    /// Exact distinct stable instance UUIDs over all observed completed turns, before ranking limits.
    #[serde(rename = "activity.agents_used")]
    AgentsUsed,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum ReaderKind {
    Consumption,
    Skills,
    Turns,
    Conversations,
}

impl ConsumptionMeasure {
    pub(crate) fn historical(self) -> bool {
        matches!(
            self,
            Self::UserSkillLoads
                | Self::AgentSkillLoads
                | Self::TotalSkillLoads
                | Self::CompletedTurns
                | Self::AgentsUsed
        )
    }
    /// Fixed reader families, not an extensible query language.
    pub(crate) fn reader(self) -> ReaderKind {
        match self {
            Self::UserSkillLoads | Self::AgentSkillLoads | Self::TotalSkillLoads => {
                ReaderKind::Skills
            }
            Self::CompletedTurns | Self::AgentsUsed => ReaderKind::Turns,
            Self::RetainedConversations => ReaderKind::Conversations,
            _ => ReaderKind::Consumption,
        }
    }
    pub(crate) fn estimated(self) -> bool {
        matches!(self, Self::CostEur | Self::Co2eGrams | Self::EnergyKwh)
    }
    pub(crate) fn metadata(self) -> AnalyticsMeasure {
        AnalyticsMeasure {
            id: self,
            calculation: if self.estimated() {
                CalculationPrecision::Estimated
            } else {
                CalculationPrecision::Exact
            },
            unit: match self {
                Self::CostEur => AnalyticsUnit::Eur,
                Self::Co2eGrams => AnalyticsUnit::GramCo2e,
                Self::EnergyKwh => AnalyticsUnit::Kwh,
                Self::RecordedExchanges => AnalyticsUnit::Exchange,
                Self::RetainedConversations => AnalyticsUnit::Conversation,
                Self::CompletedTurns => AnalyticsUnit::Turn,
                Self::AgentsUsed => AnalyticsUnit::Agent,
                Self::UserSkillLoads | Self::AgentSkillLoads | Self::TotalSkillLoads => {
                    AnalyticsUnit::Load
                }
                _ => AnalyticsUnit::Token,
            },
            value_type: if self.estimated() {
                AnalyticsValueType::Decimal
            } else {
                AnalyticsValueType::Integer
            },
        }
    }
}

#[derive(Serialize, ToSchema)]
pub struct AnalyticsResponse {
    /// Batch summary; precision is also declared per measure.
    pub calculation: CalculationPrecision,
    pub collection_completeness: CollectionCompleteness,
    /// SQL results share one read-only snapshot. Historical batches are separate; mixed sources are refused.
    pub results: BTreeMap<String, AnalyticsResult>,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum CalculationPrecision {
    Exact,
    Estimated,
    Mixed,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum CollectionCompleteness {
    Unknown,
}

#[derive(Serialize, ToSchema)]
pub struct AnalyticsResult {
    pub since: DateTime<Utc>,
    pub until: DateTime<Utc>,
    pub timezone: AnalyticsTimezone,
    /// Present only for a time series; weeks start on Monday, all buckets use UTC.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bucket: Option<AnalyticsInterval>,
    pub measures: Vec<AnalyticsMeasure>,
    pub rows: Vec<AnalyticsRow>,
    /// Rankings may be truncated; SQL totals and estimates cover all recorded facts.
    pub truncated: bool,
}

#[derive(Serialize, ToSchema)]
pub struct AnalyticsMeasure {
    pub id: ConsumptionMeasure,
    pub unit: AnalyticsUnit,
    pub calculation: CalculationPrecision,
    pub value_type: AnalyticsValueType,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum AnalyticsUnit {
    Token,
    Exchange,
    Eur,
    GramCo2e,
    Kwh,
    Load,
    Conversation,
    Turn,
    Agent,
}

#[derive(Serialize, ToSchema)]
#[serde(rename_all = "snake_case")]
pub enum AnalyticsValueType {
    /// Non-negative decimal string, preserving integers beyond JavaScript and SQL bigint sums.
    Integer,
    Decimal,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
pub struct AnalyticsEstimate {
    #[schema(required)]
    pub value: Option<String>,
    pub coverage: EstimateCoverage,
    /// At least one model used the catalog's explicitly configured default factors.
    pub fallback: bool,
}

#[derive(Clone, Deserialize, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum EstimateCoverage {
    Complete,
    Partial,
    Unavailable,
}

#[derive(Serialize, ToSchema)]
pub struct AnalyticsRow {
    pub dimensions: AnalyticsDimensions,
    /// Exact decimal integer strings for matching facts; collection completeness is declared separately.
    pub values: BTreeMap<ConsumptionMeasure, String>,
    /// Estimated decimal values are separate from exact counters. Null is never zero.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub estimates: BTreeMap<ConsumptionMeasure, AnalyticsEstimate>,
}

#[derive(Serialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AnalyticsDimensions {
    Total,
    /// Swift groups by name, merging same-named skills across spaces and revisions.
    Skill {
        name: String,
    },
    Time {
        /// UTC bucket start; the first bucket may precede since, but counts are clipped to the period.
        start: DateTime<Utc>,
    },
    Agent {
        agent_instance_id: Uuid,
        space_id: Uuid,
        /// Current/retained session name (consumption), latest observed name (turns), or null. Never an identity key.
        #[schema(required)]
        display_name: Option<String>,
    },
    /// Current direct membership, including personal spaces and projects; zero activity is retained.
    Space {
        space_id: Uuid,
    },
    Model {
        model_source_id: String,
        upstream_model_id: String,
    },
}
