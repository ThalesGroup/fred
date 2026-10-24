// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

//! Validated lifecycle configuration and pure, ordered policy resolution.
use crate::domain::SpaceKind;
use anyhow::{Context, Result, ensure};
use chrono::{DateTime, TimeDelta, Utc};
use serde::{Deserialize, Deserializer, Serialize};
use std::time::Duration;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Retention(u64);
impl Retention {
    pub fn duration(self) -> Duration {
        Duration::from_secs(self.0)
    }
    pub fn after(self, time: DateTime<Utc>) -> Result<DateTime<Utc>> {
        time.checked_add_signed(
            TimeDelta::try_seconds(self.0.try_into()?).context("retention overflow")?,
        )
        .context("retention timestamp overflow")
    }
}
impl<'de> Deserialize<'de> for Retention {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        let input = String::deserialize(d)?;
        parse_duration(&input).map_err(serde::de::Error::custom)
    }
}
fn parse_duration(input: &str) -> Result<Retention> {
    let text = input.trim().to_ascii_uppercase();
    let rest = text
        .strip_prefix('P')
        .context("duration must start with P")?;
    let (mut total, mut digits, mut seen, mut time, mut rank) =
        (0u64, String::new(), false, false, 0);
    for c in rest.chars() {
        if c.is_ascii_digit() {
            digits.push(c);
            continue;
        }
        if c == 'T' && !time && digits.is_empty() {
            time = true;
            ensure!(!rest.ends_with('T'), "empty duration time");
            continue;
        }
        let (order, factor) = match (time, c) {
            (false, 'W') => (1, 604800),
            (false, 'D') => (2, 86400),
            (true, 'H') => (3, 3600),
            (true, 'M') => (4, 60),
            (true, 'S') => (5, 1),
            _ => anyhow::bail!("unsupported duration unit"),
        };
        ensure!(
            order > rank && !digits.is_empty(),
            "invalid duration order or amount"
        );
        let value: u64 = digits.parse()?;
        total = value
            .checked_mul(factor)
            .and_then(|v| total.checked_add(v))
            .context("duration overflow")?;
        digits.clear();
        rank = order;
        seen = true;
    }
    ensure!(seen && digits.is_empty(), "empty or incomplete duration");
    // Bound against Chrono's timestamp domain before accepting the configuration.
    let retention = Retention(total);
    retention.after(Utc::now())?;
    Ok(retention)
}
fn week() -> Retention {
    Retention(604800)
}
fn interval() -> Retention {
    Retention(600)
}
fn batch() -> u32 {
    100
}
fn host() -> String {
    "localhost:7233".into()
}
fn namespace() -> String {
    "default".into()
}
fn queue() -> String {
    "control-plane-lifecycle".into()
}
fn prefix() -> String {
    "control-plane-lifecycle".into()
}
fn connect_timeout() -> u64 {
    5
}
fn rpc_timeout() -> u64 {
    10
}

#[derive(Debug, Clone, Default, Deserialize, utoipa::ToSchema)]
#[serde(default, deny_unknown_fields)]
pub struct Policies {
    pub purge_catalog_path: Option<String>,
}

#[derive(Debug, Clone, Deserialize, utoipa::ToSchema)]
#[serde(default, deny_unknown_fields)]
pub struct LifecycleConfig {
    pub enabled: bool,
    pub temporal: TemporalConfig,
    #[schema(value_type = String, default = "PT10M")]
    pub sweep_interval: Retention,
    pub batch_size: u32,
}
impl Default for LifecycleConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            temporal: TemporalConfig::default(),
            sweep_interval: interval(),
            batch_size: batch(),
        }
    }
}
#[derive(Debug, Clone, Deserialize, utoipa::ToSchema, Serialize)]
#[serde(default, deny_unknown_fields)]
pub struct TemporalConfig {
    pub host: String,
    pub namespace: String,
    pub task_queue: String,
    pub workflow_id_prefix: String,
    pub connect_timeout_seconds: u64,
    pub rpc_timeout_seconds: u64,
}
impl Default for TemporalConfig {
    fn default() -> Self {
        Self {
            host: host(),
            namespace: namespace(),
            task_queue: queue(),
            workflow_id_prefix: prefix(),
            connect_timeout_seconds: connect_timeout(),
            rpc_timeout_seconds: rpc_timeout(),
        }
    }
}
impl LifecycleConfig {
    pub fn validate(&self) -> Result<()> {
        ensure!(self.sweep_interval.0 > 0, "sweep interval must be positive");
        ensure!(
            (1..=5000).contains(&self.batch_size),
            "batch size must be 1..5000"
        );
        let t = &self.temporal;
        ensure!(
            [&t.host, &t.namespace, &t.task_queue, &t.workflow_id_prefix]
                .iter()
                .all(|s| !s.trim().is_empty() && s.trim() == s.as_str()),
            "blank lifecycle connection field"
        );
        ensure!(
            t.task_queue.starts_with("control-plane-")
                && t.workflow_id_prefix.starts_with("control-plane-"),
            "lifecycle queue and workflow prefix must be manager-owned"
        );
        ensure!(
            t.connect_timeout_seconds > 0 && t.rpc_timeout_seconds > 0,
            "Temporal timeouts must be positive"
        );
        Ok(())
    }
}
#[derive(Debug, Clone, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Action {
    pub retention: Retention,
}
impl Default for Action {
    fn default() -> Self {
        Self { retention: week() }
    }
}
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Override {
    pub retention: Option<Retention>,
}
#[derive(Debug, Clone, Deserialize)]
#[serde(untagged)]
pub enum Values<T> {
    One(T),
    Many(Vec<T>),
}
impl<T: PartialEq> Values<T> {
    fn contains(&self, target: &T) -> bool {
        match self {
            Self::One(v) => v == target,
            Self::Many(v) => v.contains(target),
        }
    }
    fn valid(&self) -> bool {
        !matches!(self, Self::Many(v) if v.is_empty())
    }
}
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Match {
    pub space_id: Option<Values<Uuid>>,
    pub space_kind: Option<Values<SpaceKind>>,
}
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Rule {
    pub rule_id: String,
    pub r#match: Match,
    pub action: Override,
}
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Purge {
    pub default: Action,
    pub rules: Vec<Rule>,
}
#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct SpacePolicies {
    pub purge: Purge,
}
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Catalog {
    pub version: String,
    pub space_policies: SpacePolicies,
}
impl Default for Catalog {
    fn default() -> Self {
        Self {
            version: "v1".into(),
            space_policies: SpacePolicies::default(),
        }
    }
}
impl Catalog {
    pub fn load(path: Option<&str>) -> Result<Self> {
        let value: Self = match path {
            Some(path) => serde_yaml_ng::from_str(
                &std::fs::read_to_string(path).context("cannot read lifecycle policy catalog")?,
            )
            .context("invalid lifecycle policy catalog")?,
            None => Self::default(),
        };
        value.validate()?;
        Ok(value)
    }
    pub fn validate(&self) -> Result<()> {
        ensure!(self.version == "v1", "unsupported lifecycle policy version");
        let mut ids = std::collections::BTreeSet::new();
        for r in &self.space_policies.purge.rules {
            ensure!(
                !r.rule_id.trim().is_empty() && ids.insert(&r.rule_id),
                "blank or duplicate policy rule id"
            );
            ensure!(
                r.r#match.space_id.as_ref().is_none_or(Values::valid)
                    && r.r#match.space_kind.as_ref().is_none_or(Values::valid),
                "empty policy match values"
            );
        }
        Ok(())
    }
    pub fn resolve(&self, id: Uuid, kind: SpaceKind) -> (Action, Option<&str>) {
        let purge = &self.space_policies.purge;
        let mut chosen = None;
        let mut best = None;
        for rule in &purge.rules {
            let m = &rule.r#match;
            let score = usize::from(m.space_id.is_some()) + usize::from(m.space_kind.is_some());
            if m.space_id.as_ref().is_none_or(|v| v.contains(&id))
                && m.space_kind.as_ref().is_none_or(|v| v.contains(&kind))
                && best.is_none_or(|b| score > b)
            {
                chosen = Some(rule);
                best = Some(score);
            }
        }
        let mut action = purge.default.clone();
        if let Some(r) = chosen
            && let Some(v) = r.action.retention
        {
            action.retention = v;
        }
        (action, chosen.map(|r| r.rule_id.as_str()))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn duration_subset_is_checked_without_panics() {
        for text in ["P0D", "PT0S", " p1w2dt3h4m5s ", "PT30S"] {
            assert!(parse_duration(text).is_ok(), "{text}");
        }
        for text in [
            "P",
            "PT",
            "P1DT",
            "P-1D",
            "P1Y",
            "P1M",
            "PT1.5S",
            "P1D2W",
            "PT1S1S",
            "P18446744073709551615D",
            "PT9223372036854775807S",
            "PT18446744073709551616S",
            "P2",
        ] {
            assert!(parse_duration(text).is_err(), "{text}");
        }
    }
    #[test]
    fn matching_uses_specificity_then_file_order_and_rejects_unknown_fields() {
        let id = Uuid::new_v4();
        let text = format!(
            "version: v1\nspace_policies:\n  purge:\n    rules:\n    - rule_id: broad\n      match: {{}}\n      action: {{retention: P1D}}\n    - rule_id: kind\n      match: {{space_kind: [team]}}\n      action: {{retention: PT30S}}\n    - rule_id: id\n      match: {{space_id: '{id}'}}\n      action: {{retention: PT40S}}\n    - rule_id: exact\n      match: {{space_id: '{id}', space_kind: team}}\n      action: {{retention: PT0S}}\n"
        );
        let catalog: Catalog = serde_yaml_ng::from_str(&text).unwrap();
        catalog.validate().unwrap();
        let (action, rule) = catalog.resolve(id, SpaceKind::Team);
        assert_eq!(rule, Some("exact"));
        assert_eq!(action.retention.0, 0);
        let (action, rule) = catalog.resolve(Uuid::new_v4(), SpaceKind::Team);
        assert_eq!(rule, Some("kind"));
        assert_eq!(action.retention.0, 30);
        let (action, rule) = catalog.resolve(Uuid::new_v4(), SpaceKind::Personal);
        assert_eq!(rule, Some("broad"));
        assert_eq!(action.retention.0, 86400);
        let personal: Catalog =
            serde_yaml_ng::from_str(&text.replace("space_kind: [team]", "space_kind: [personal]"))
                .unwrap();
        assert_eq!(
            personal.resolve(Uuid::new_v4(), SpaceKind::Personal).1,
            Some("kind")
        );
        assert_eq!(
            personal.resolve(Uuid::new_v4(), SpaceKind::Team).1,
            Some("broad")
        );
        let mut tied = catalog.clone();
        tied.space_policies.purge.rules.pop();
        assert_eq!(tied.resolve(id, SpaceKind::Team).1, Some("kind"));
        assert!(
            serde_yaml_ng::from_str::<Catalog>(
                &text.replace("retention: PT0S", "cancel_on_rejoin: true")
            )
            .is_err()
        );
        let invalid: Catalog =
            serde_yaml_ng::from_str(&text.replace("space_kind: [team]", "space_kind: []")).unwrap();
        assert!(invalid.validate().is_err());
        assert_eq!(
            Catalog::default()
                .resolve(id, SpaceKind::Project)
                .0
                .retention
                .0,
            7 * 86400
        );
    }
    #[test]
    fn lifecycle_defaults_disable_requests_and_validate_bounds() {
        let config = LifecycleConfig::default();
        assert!(!config.enabled);
        config.validate().unwrap();
        for yaml in [
            "sweep_interval: PT0S",
            "batch_size: 0",
            "batch_size: 5001",
            "temporal: {connect_timeout_seconds: 0}",
            "temporal: {task_queue: fred-ingestion}",
        ] {
            let c: LifecycleConfig = serde_yaml_ng::from_str(yaml).unwrap();
            assert!(c.validate().is_err());
        }
        assert!(serde_yaml_ng::from_str::<LifecycleConfig>("unknown: true").is_err());
    }
}
