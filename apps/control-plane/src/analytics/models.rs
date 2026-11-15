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

impl AnalyticsRequest {
    pub(crate) fn calculation(&self) -> CalculationPrecision {
        let mut kinds = self
            .queries
            .iter()
            .flat_map(|q| &q.measures)
            .map(|m| m.metadata().calculation);
        let first = kinds.next().unwrap_or(CalculationPrecision::Exact);
        if kinds.all(|kind| kind == first) {
            first
        } else {
            CalculationPrecision::Mixed
        }
    }
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
    /// Consumption: total/time/agent/model; catalogues: total; turns: total/time/agent (self also space); skills: skill; tools: total/tool.
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
    /// Direct ReadUsage for collective consumption, retained creations, turns and skill loads.
    /// Teams include their projects (also retired/purged); projects never expand.
    /// Aggregates grant no conversation content or individual-user access.
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
    /// UTC dates, French national holidays (metropole, excluding local additions).
    #[serde(default)]
    pub calendar: AnalyticsCalendar,
    /// Time grouping only. Omission chooses hour <=48h, day <=92d, week otherwise.
    pub bucket: Option<AnalyticsInterval>,
}

#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Deserialize, Serialize, ToSchema)]
#[serde(deny_unknown_fields)]
pub struct AnalyticsCalendar {
    #[serde(default)]
    pub exclude_weekends: bool,
    #[serde(default)]
    pub exclude_holidays: bool,
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
    Tool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Deserialize, Serialize, ToSchema)]
pub enum ConsumptionMeasure {
    #[serde(rename = "activity.median_usage_days")]
    MedianUsageDays,
    #[serde(rename = "activity.median_days_per_week")]
    MedianDaysPerWeek,
    #[serde(rename = "activity.mean_daily_active")]
    MeanDailyActive,
    #[serde(rename = "activity.daily_usage_share")]
    DailyUsageShare,
    #[serde(rename = "activity.median_turns_per_conversation")]
    MedianTurns,
    #[serde(rename = "activity.failure_rate")]
    FailureRate,
    #[serde(rename = "activity.single_turn_rate")]
    SingleTurnRate,
    #[serde(rename = "activity.retained_conversations_per_creator_median")]
    ConversationMedian,
    #[serde(rename = "activity.retained_conversations_top_decile_share")]
    ConversationConcentration,
    #[serde(rename = "activity.creators_1")]
    CreatorsOne,
    #[serde(rename = "activity.creators_2_3")]
    CreatorsTwoThree,
    #[serde(rename = "activity.creators_4_10")]
    CreatorsFourTen,
    #[serde(rename = "activity.creators_11_30")]
    CreatorsElevenThirty,
    #[serde(rename = "activity.creators_31_plus")]
    CreatorsThirtyPlus,
    #[serde(rename = "inventory.enabled_agents")]
    AgentsAvailable,
    #[serde(rename = "inventory.retained_agents_created")]
    AgentsCreated,
    #[serde(rename = "inventory.agents_published")]
    AgentsPublished,
    #[serde(rename = "inventory.documents_added")]
    DocumentsAdded,
    #[serde(rename = "tools.attempts")]
    ToolAttempts,
    #[serde(rename = "tools.successes")]
    ToolSuccesses,
    #[serde(rename = "tools.failures")]
    ToolFailures,
    #[serde(rename = "tools.cancelled")]
    ToolCancelled,
    #[serde(rename = "tools.awaiting_human")]
    ToolWaiting,
    #[serde(rename = "tools.failure_rate")]
    ToolFailureRate,

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
    /// Distinct attributed users in observed completed turns. Absent if identities were erased/missing.
    #[serde(rename = "activity.active_users")]
    ActiveUsers,
    /// Distinct attributed conversations with a completed turn in the period, not new creations.
    /// Absent if conversation identities were erased/missing. Never exposes identities or content.
    #[serde(rename = "activity.observed_conversations")]
    ObservedConversations,
    /// Completed turns with finish_reason=error; absent if any finish_reason is missing.
    #[serde(rename = "activity.failed_turns")]
    FailedTurns,
    /// Conversations with exactly one observed completed turn within the period (not lifetime).
    #[serde(rename = "activity.single_turn_conversations")]
    SingleTurnConversations,
}

#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum ReaderKind {
    Consumption,
    Skills,
    Turns,
    Conversations,
    Inventory,
    Tools,
}

impl ConsumptionMeasure {
    pub(crate) fn historical(self) -> bool {
        matches!(
            self.reader(),
            ReaderKind::Skills | ReaderKind::Turns | ReaderKind::Tools
        )
    }
    /// Fixed reader families, not an extensible query language.
    pub(crate) fn reader(self) -> ReaderKind {
        match self {
            Self::MedianUsageDays
            | Self::MedianDaysPerWeek
            | Self::MeanDailyActive
            | Self::DailyUsageShare
            | Self::MedianTurns
            | Self::FailureRate
            | Self::SingleTurnRate => ReaderKind::Turns,
            Self::ToolAttempts
            | Self::ToolSuccesses
            | Self::ToolFailures
            | Self::ToolCancelled
            | Self::ToolWaiting
            | Self::ToolFailureRate => ReaderKind::Tools,
            Self::AgentsAvailable
            | Self::AgentsCreated
            | Self::AgentsPublished
            | Self::DocumentsAdded => ReaderKind::Inventory,
            Self::ConversationMedian
            | Self::ConversationConcentration
            | Self::CreatorsOne
            | Self::CreatorsTwoThree
            | Self::CreatorsFourTen
            | Self::CreatorsElevenThirty
            | Self::CreatorsThirtyPlus => ReaderKind::Conversations,
            Self::UserSkillLoads | Self::AgentSkillLoads | Self::TotalSkillLoads => {
                ReaderKind::Skills
            }
            Self::CompletedTurns
            | Self::AgentsUsed
            | Self::ActiveUsers
            | Self::ObservedConversations
            | Self::FailedTurns
            | Self::SingleTurnConversations => ReaderKind::Turns,
            Self::RetainedConversations => ReaderKind::Conversations,
            _ => ReaderKind::Consumption,
        }
    }
    pub(crate) fn needs_attribution(self) -> bool {
        if matches!(
            self,
            Self::MedianUsageDays
                | Self::MedianDaysPerWeek
                | Self::MeanDailyActive
                | Self::DailyUsageShare
                | Self::MedianTurns
                | Self::FailureRate
                | Self::SingleTurnRate
        ) {
            return true;
        }
        matches!(
            self,
            Self::ActiveUsers
                | Self::ObservedConversations
                | Self::FailedTurns
                | Self::SingleTurnConversations
        )
    }
    pub(crate) fn needs_days(self) -> bool {
        matches!(
            self,
            Self::MedianUsageDays
                | Self::MedianDaysPerWeek
                | Self::MeanDailyActive
                | Self::DailyUsageShare
        )
    }
    pub(crate) fn decimal(self) -> bool {
        self.estimated()
            || matches!(
                self,
                Self::MedianUsageDays
                    | Self::MedianDaysPerWeek
                    | Self::MeanDailyActive
                    | Self::DailyUsageShare
                    | Self::MedianTurns
                    | Self::FailureRate
                    | Self::SingleTurnRate
                    | Self::ConversationMedian
                    | Self::ConversationConcentration
                    | Self::ToolFailureRate
            )
    }
    pub(crate) fn rounded(self) -> bool {
        matches!(
            self,
            Self::MedianDaysPerWeek
                | Self::MeanDailyActive
                | Self::DailyUsageShare
                | Self::FailureRate
                | Self::SingleTurnRate
                | Self::ConversationConcentration
                | Self::ToolFailureRate
        )
    }
    pub(crate) fn estimated(self) -> bool {
        matches!(self, Self::CostEur | Self::Co2eGrams | Self::EnergyKwh)
    }
    pub(crate) fn metadata(self) -> AnalyticsMeasure {
        AnalyticsMeasure {
            id: self,
            calculation: if self.rounded() {
                CalculationPrecision::Rounded
            } else if self.estimated() {
                CalculationPrecision::Estimated
            } else {
                CalculationPrecision::Exact
            },
            unit: match self {
                Self::MedianUsageDays | Self::MedianDaysPerWeek => AnalyticsUnit::Day,
                Self::DailyUsageShare
                | Self::FailureRate
                | Self::SingleTurnRate
                | Self::ConversationConcentration
                | Self::ToolFailureRate => AnalyticsUnit::Ratio,
                Self::MeanDailyActive
                | Self::CreatorsOne
                | Self::CreatorsTwoThree
                | Self::CreatorsFourTen
                | Self::CreatorsElevenThirty
                | Self::CreatorsThirtyPlus => AnalyticsUnit::User,
                Self::MedianTurns => AnalyticsUnit::Turn,
                Self::ConversationMedian => AnalyticsUnit::Conversation,
                Self::AgentsAvailable | Self::AgentsCreated | Self::AgentsPublished => {
                    AnalyticsUnit::Agent
                }
                Self::DocumentsAdded => AnalyticsUnit::Document,
                Self::ToolAttempts
                | Self::ToolSuccesses
                | Self::ToolFailures
                | Self::ToolCancelled
                | Self::ToolWaiting => AnalyticsUnit::Attempt,
                Self::CostEur => AnalyticsUnit::Eur,
                Self::Co2eGrams => AnalyticsUnit::GramCo2e,
                Self::EnergyKwh => AnalyticsUnit::Kwh,
                Self::RecordedExchanges => AnalyticsUnit::Exchange,
                Self::RetainedConversations
                | Self::ObservedConversations
                | Self::SingleTurnConversations => AnalyticsUnit::Conversation,
                Self::CompletedTurns | Self::FailedTurns => AnalyticsUnit::Turn,
                Self::ActiveUsers => AnalyticsUnit::User,
                Self::AgentsUsed => AnalyticsUnit::Agent,
                Self::UserSkillLoads | Self::AgentSkillLoads | Self::TotalSkillLoads => {
                    AnalyticsUnit::Load
                }
                _ => AnalyticsUnit::Token,
            },
            value_type: if self.decimal() {
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

#[derive(Clone, Copy, PartialEq, Eq, Serialize, ToSchema)]
#[serde(rename_all = "lowercase")]
pub enum CalculationPrecision {
    Exact,
    /// Deterministic division truncated to at most six fractional digits.
    Rounded,
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
    /// UTC dates, French national holidays (metropole, excluding local additions).
    #[serde(default)]
    pub calendar: AnalyticsCalendar,
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
    Day,
    Ratio,
    Document,
    Attempt,
    Token,
    Exchange,
    Eur,
    GramCo2e,
    Kwh,
    Load,
    Conversation,
    Turn,
    Agent,
    User,
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
    /// Decimal strings for matching facts; per-measure metadata distinguishes exact integers/medians
    /// from ratios truncated to six fractional digits. Collection completeness is separate.
    /// A requested attribution counter is absent when erased/missing identities or outcomes prevent an exact count.
    /// Absence is unavailable, never zero. No user or conversation identities are returned.
    pub values: BTreeMap<ConsumptionMeasure, String>,
    /// Estimated decimal values are separate from exact counters. Null is never zero.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub estimates: BTreeMap<ConsumptionMeasure, AnalyticsEstimate>,
}

#[derive(Serialize, ToSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum AnalyticsDimensions {
    Total,
    Tool {
        name: String,
    },
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
